from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from engine.paper_broker import (
    PaperBroker,
    PaperBrokerConfig,
    PaperFill,
    PaperOrder,
    PaperOrderRequest,
    PaperOrderSide,
    PaperOrderStatus,
    PaperOrderType,
)
from engine.paper_portfolio import PaperPortfolio
from engine.trade_journal import TradeJournal, TradeRecord


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class PaperTradingConfig:
    starting_cash: float = 1_000_000.0
    commission_rate: float = 0.001
    slippage_rate: float = 0.0005
    allow_partial_fills: bool = True
    max_fill_ratio: float = 1.0
    allow_short_selling: bool = False
    default_order_type: PaperOrderType = PaperOrderType.MARKET

    def broker_config(self) -> PaperBrokerConfig:
        return PaperBrokerConfig(
            starting_cash=self.starting_cash,
            commission_rate=self.commission_rate,
            slippage_rate=self.slippage_rate,
            allow_partial_fills=self.allow_partial_fills,
            max_fill_ratio=self.max_fill_ratio,
            allow_short_selling=self.allow_short_selling,
        )


@dataclass(slots=True)
class OpenTrade:
    symbol: str
    side: str
    quantity: float
    entry_price: float
    opened_at: datetime
    entry_reason: str = ""
    strategy: str = ""
    entry_commission: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "opened_at": self.opened_at.isoformat(),
            "entry_reason": self.entry_reason,
            "strategy": self.strategy,
            "entry_commission": self.entry_commission,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class PaperTradingResult:
    order: PaperOrder
    fills: List[PaperFill]
    portfolio_snapshot: Dict[str, Any]
    journal_trade: Optional[TradeRecord] = None

    @property
    def success(self) -> bool:
        return self.order.status in {
            PaperOrderStatus.FILLED,
            PaperOrderStatus.PARTIALLY_FILLED,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "order": self.order.to_dict(),
            "fills": [fill.to_dict() for fill in self.fills],
            "portfolio": self.portfolio_snapshot,
            "journal_trade": (
                self.journal_trade.to_dict()
                if self.journal_trade is not None
                else None
            ),
        }


class PaperTradingEngine:
    def __init__(
        self,
        config: Optional[PaperTradingConfig] = None,
        *,
        broker: Optional[PaperBroker] = None,
        portfolio: Optional[PaperPortfolio] = None,
        journal: Optional[TradeJournal] = None,
    ) -> None:
        self.config = config or PaperTradingConfig()
        self.broker = broker or PaperBroker(self.config.broker_config())
        self.portfolio = portfolio or PaperPortfolio(self.config.starting_cash)
        self.journal = journal or TradeJournal()
        self.open_trades: Dict[str, OpenTrade] = {}
        self._processed_fill_ids: set[str] = set()

    def submit_signal(
        self,
        *,
        symbol: str,
        action: str,
        quantity: float,
        market_price: float,
        reason: str = "",
        strategy: str = "",
        order_type: Optional[PaperOrderType] = None,
        limit_price: Optional[float] = None,
        available_liquidity: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
        timestamp: Optional[datetime] = None,
    ) -> PaperTradingResult:
        normalized_action = action.strip().upper()
        if normalized_action not in {"BUY", "SELL"}:
            raise ValueError("action BUY veya SELL olmalıdır.")

        side = (
            PaperOrderSide.BUY
            if normalized_action == "BUY"
            else PaperOrderSide.SELL
        )
        selected_type = order_type or self.config.default_order_type
        request = PaperOrderRequest(
            symbol=symbol,
            side=side,
            order_type=selected_type,
            quantity=quantity,
            limit_price=limit_price,
            client_order_id=uuid4().hex,
            metadata=metadata or {},
        )
        before_fill_ids = {fill.fill_id for fill in self.broker.fills()}
        order = self.broker.submit_order(
            request,
            market_price=market_price,
            available_liquidity=available_liquidity,
        )
        new_fills = [
            fill
            for fill in self.broker.fills()
            if fill.fill_id not in before_fill_ids
        ]
        journal_trade = self._process_fills(
            new_fills,
            reason=reason,
            strategy=strategy,
            metadata=metadata or {},
            timestamp=timestamp or utc_now(),
        )
        self.portfolio.update_market_price(symbol, market_price, timestamp=timestamp)
        self.portfolio.record_equity(timestamp=timestamp)

        return PaperTradingResult(
            order=order,
            fills=new_fills,
            portfolio_snapshot=self.portfolio.snapshot(),
            journal_trade=journal_trade,
        )

    def process_open_order(
        self,
        order_id: str,
        *,
        market_price: float,
        available_liquidity: Optional[float] = None,
        reason: str = "",
        strategy: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        timestamp: Optional[datetime] = None,
    ) -> PaperTradingResult:
        before_fill_ids = {fill.fill_id for fill in self.broker.fills()}
        order = self.broker.process_order(
            order_id,
            market_price=market_price,
            available_liquidity=available_liquidity,
        )
        new_fills = [
            fill
            for fill in self.broker.fills()
            if fill.fill_id not in before_fill_ids
        ]
        journal_trade = self._process_fills(
            new_fills,
            reason=reason,
            strategy=strategy,
            metadata=metadata or {},
            timestamp=timestamp or utc_now(),
        )
        self.portfolio.update_market_price(order.symbol, market_price, timestamp=timestamp)
        self.portfolio.record_equity(timestamp=timestamp)
        return PaperTradingResult(
            order=order,
            fills=new_fills,
            portfolio_snapshot=self.portfolio.snapshot(),
            journal_trade=journal_trade,
        )

    def _process_fills(
        self,
        fills: List[PaperFill],
        *,
        reason: str,
        strategy: str,
        metadata: Dict[str, Any],
        timestamp: datetime,
    ) -> Optional[TradeRecord]:
        last_trade: Optional[TradeRecord] = None
        for fill in fills:
            if fill.fill_id in self._processed_fill_ids:
                continue
            self.portfolio.apply_fill(fill)
            self._processed_fill_ids.add(fill.fill_id)
            last_trade = self._update_trade_state(
                fill,
                reason=reason,
                strategy=strategy,
                metadata=metadata,
                timestamp=timestamp,
            )
        return last_trade

    def _update_trade_state(
        self,
        fill: PaperFill,
        *,
        reason: str,
        strategy: str,
        metadata: Dict[str, Any],
        timestamp: datetime,
    ) -> Optional[TradeRecord]:
        symbol = fill.symbol
        current = self.open_trades.get(symbol)

        if fill.side == PaperOrderSide.BUY:
            if current is None:
                self.open_trades[symbol] = OpenTrade(
                    symbol=symbol,
                    side="LONG",
                    quantity=fill.quantity,
                    entry_price=fill.price,
                    opened_at=timestamp,
                    entry_reason=reason,
                    strategy=strategy,
                    entry_commission=fill.commission,
                    metadata=dict(metadata),
                )
                return None

            if current.side == "LONG":
                total_qty = current.quantity + fill.quantity
                current.entry_price = (
                    current.entry_price * current.quantity
                    + fill.price * fill.quantity
                ) / total_qty
                current.quantity = total_qty
                current.entry_commission += fill.commission
                return None

            return self._close_or_reverse(
                current,
                fill=fill,
                exit_reason=reason,
                strategy=strategy,
                metadata=metadata,
                timestamp=timestamp,
            )

        if current is None:
            if not self.config.allow_short_selling:
                return None
            self.open_trades[symbol] = OpenTrade(
                symbol=symbol,
                side="SHORT",
                quantity=fill.quantity,
                entry_price=fill.price,
                opened_at=timestamp,
                entry_reason=reason,
                strategy=strategy,
                entry_commission=fill.commission,
                metadata=dict(metadata),
            )
            return None

        if current.side == "SHORT":
            total_qty = current.quantity + fill.quantity
            current.entry_price = (
                current.entry_price * current.quantity
                + fill.price * fill.quantity
            ) / total_qty
            current.quantity = total_qty
            current.entry_commission += fill.commission
            return None

        return self._close_or_reverse(
            current,
            fill=fill,
            exit_reason=reason,
            strategy=strategy,
            metadata=metadata,
            timestamp=timestamp,
        )

    def _close_or_reverse(
        self,
        current: OpenTrade,
        *,
        fill: PaperFill,
        exit_reason: str,
        strategy: str,
        metadata: Dict[str, Any],
        timestamp: datetime,
    ) -> TradeRecord:
        closing_quantity = min(current.quantity, fill.quantity)
        allocated_entry_commission = (
            current.entry_commission
            * closing_quantity
            / current.quantity
            if current.quantity > 0
            else 0.0
        )
        allocated_exit_commission = (
            fill.commission
            * closing_quantity
            / fill.quantity
            if fill.quantity > 0
            else 0.0
        )

        trade = self.journal.create_trade(
            symbol=current.symbol,
            side=current.side,
            quantity=closing_quantity,
            entry_price=current.entry_price,
            exit_price=fill.price,
            opened_at=current.opened_at,
            closed_at=timestamp,
            commission=allocated_entry_commission + allocated_exit_commission,
            slippage_cost=0.0,
            entry_reason=current.entry_reason,
            exit_reason=exit_reason,
            strategy=strategy or current.strategy,
            metadata={**current.metadata, **metadata},
        )

        remaining_current = current.quantity - closing_quantity
        remaining_fill = fill.quantity - closing_quantity

        if remaining_current > 1e-12:
            current.quantity = remaining_current
            current.entry_commission -= allocated_entry_commission
            return trade

        self.open_trades.pop(current.symbol, None)

        if remaining_fill > 1e-12:
            new_side = "LONG" if fill.side == PaperOrderSide.BUY else "SHORT"
            self.open_trades[current.symbol] = OpenTrade(
                symbol=current.symbol,
                side=new_side,
                quantity=remaining_fill,
                entry_price=fill.price,
                opened_at=timestamp,
                entry_reason=exit_reason,
                strategy=strategy,
                entry_commission=fill.commission - allocated_exit_commission,
                metadata=dict(metadata),
            )

        return trade

    def mark_to_market(
        self,
        prices: Dict[str, float],
        *,
        timestamp: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        self.portfolio.update_market_prices(prices, timestamp=timestamp)
        self.portfolio.record_equity(timestamp=timestamp)
        return self.portfolio.snapshot()

    def cancel_order(self, order_id: str) -> PaperOrder:
        return self.broker.cancel_order(order_id)

    def dashboard(self) -> Dict[str, Any]:
        return {
            "broker": self.broker.dashboard(),
            "portfolio": self.portfolio.snapshot(),
            "journal": self.journal.dashboard(),
            "open_trades": {
                symbol: trade.to_dict()
                for symbol, trade in sorted(self.open_trades.items())
            },
            "open_orders": [
                order.to_dict()
                for order in self.broker.open_orders()
            ],
        }
