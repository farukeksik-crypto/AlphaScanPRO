from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable
import math
import time

from engine.robot_runtime import RuntimeAction, StrategyDecision


class PaperOrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class PaperOrderStatus(str, Enum):
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    SKIPPED = "SKIPPED"


@dataclass
class PaperTradingConfig:
    starting_cash: float = 1_000_000.0
    commission_rate: float = 0.001
    slippage_rate: float = 0.0005
    max_position_pct: float = 0.25
    default_order_value: float = 50_000.0
    allow_pyramiding: bool = False
    allow_partial_sell: bool = True
    min_order_value: float = 100.0
    max_trade_history: int = 10_000

    def validate(self) -> None:
        if self.starting_cash <= 0:
            raise ValueError("starting_cash pozitif olmalıdır.")
        if not 0 <= self.commission_rate < 1:
            raise ValueError("commission_rate 0-1 aralığında olmalıdır.")
        if not 0 <= self.slippage_rate < 1:
            raise ValueError("slippage_rate 0-1 aralığında olmalıdır.")
        if not 0 < self.max_position_pct <= 1:
            raise ValueError("max_position_pct 0-1 aralığında olmalıdır.")
        if self.default_order_value <= 0:
            raise ValueError("default_order_value pozitif olmalıdır.")
        if self.min_order_value <= 0:
            raise ValueError("min_order_value pozitif olmalıdır.")
        if self.max_trade_history <= 0:
            raise ValueError("max_trade_history pozitif olmalıdır.")


@dataclass
class PaperPosition:
    symbol: str
    quantity: float
    average_price: float
    invested_value: float
    opened_at: float
    updated_at: float
    last_price: float

    @property
    def market_value(self) -> float:
        return self.quantity * self.last_price

    @property
    def unrealized_pnl(self) -> float:
        return self.market_value - self.invested_value

    @property
    def unrealized_pnl_pct(self) -> float:
        if self.invested_value <= 0:
            return 0.0
        return (self.unrealized_pnl / self.invested_value) * 100.0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.update(
            {
                "market_value": self.market_value,
                "unrealized_pnl": self.unrealized_pnl,
                "unrealized_pnl_pct": self.unrealized_pnl_pct,
            }
        )
        return data


@dataclass
class PaperTrade:
    trade_id: int
    symbol: str
    side: PaperOrderSide
    status: PaperOrderStatus
    quantity: float
    requested_price: float
    fill_price: float
    gross_value: float
    commission: float
    net_cash_effect: float
    realized_pnl: float
    reason: str
    timestamp: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["side"] = self.side.value
        data["status"] = self.status.value
        return data


@dataclass
class PaperPortfolioSnapshot:
    cash: float
    invested_value: float
    market_value: float
    equity: float
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    total_pnl_pct: float
    open_positions: int
    trade_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PaperPortfolio:
    def __init__(
        self,
        config: PaperTradingConfig | None = None,
        *,
        time_fn: Callable[[], float] = time.time,
    ) -> None:
        self.config = config or PaperTradingConfig()
        self.config.validate()
        self.time_fn = time_fn
        self.cash = float(self.config.starting_cash)
        self.realized_pnl = 0.0
        self.positions: dict[str, PaperPosition] = {}
        self.trades: list[PaperTrade] = []
        self._trade_id = 0

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        return symbol.replace("/", "").replace("-", "").upper()

    def update_price(self, symbol: str, price: float) -> None:
        symbol = self.normalize_symbol(symbol)
        if price <= 0 or not math.isfinite(price):
            raise ValueError("Fiyat pozitif ve sonlu olmalıdır.")
        if symbol in self.positions:
            self.positions[symbol].last_price = float(price)
            self.positions[symbol].updated_at = self.time_fn()

    def execute_decision(
        self,
        decision: StrategyDecision,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}
        if decision.action == RuntimeAction.BUY:
            trade = self.buy(
                symbol=decision.symbol,
                price=self._resolve_price(decision, context),
                quantity=decision.quantity,
                order_value=decision.metadata.get("order_value"),
                reason=decision.reason,
                metadata=decision.metadata,
            )
            return trade.to_dict()

        if decision.action == RuntimeAction.SELL:
            trade = self.sell(
                symbol=decision.symbol,
                price=self._resolve_price(decision, context),
                quantity=decision.quantity,
                reason=decision.reason,
                metadata=decision.metadata,
            )
            return trade.to_dict()

        return {
            "status": PaperOrderStatus.SKIPPED.value,
            "symbol": self.normalize_symbol(decision.symbol),
            "action": decision.action.value,
            "reason": "HOLD/SKIP kararı için emir oluşturulmadı.",
        }

    def buy(
        self,
        *,
        symbol: str,
        price: float,
        quantity: float | None = None,
        order_value: float | None = None,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> PaperTrade:
        symbol = self.normalize_symbol(symbol)
        self._validate_price(price)

        existing = self.positions.get(symbol)
        if existing and not self.config.allow_pyramiding:
            return self._rejected_trade(
                symbol=symbol,
                side=PaperOrderSide.BUY,
                price=price,
                reason="Aynı sembolde açık pozisyon varken yeni alış yasak.",
                metadata=metadata,
            )

        equity = self.snapshot().equity
        max_position_value = equity * self.config.max_position_pct
        current_value = existing.market_value if existing else 0.0
        available_position_room = max(0.0, max_position_value - current_value)

        requested_value = (
            float(order_value)
            if order_value is not None
            else (
                float(quantity) * price
                if quantity is not None
                else self.config.default_order_value
            )
        )
        requested_value = min(requested_value, available_position_room)

        if requested_value < self.config.min_order_value:
            return self._rejected_trade(
                symbol=symbol,
                side=PaperOrderSide.BUY,
                price=price,
                reason="Emir değeri minimum tutarın veya pozisyon limitinin altında.",
                metadata=metadata,
            )

        fill_price = price * (1.0 + self.config.slippage_rate)
        if quantity is None:
            quantity = requested_value / fill_price
        else:
            quantity = min(float(quantity), requested_value / fill_price)

        gross = quantity * fill_price
        commission = gross * self.config.commission_rate
        total_cost = gross + commission

        if total_cost > self.cash:
            affordable_gross = self.cash / (1.0 + self.config.commission_rate)
            quantity = affordable_gross / fill_price
            gross = quantity * fill_price
            commission = gross * self.config.commission_rate
            total_cost = gross + commission

        if gross < self.config.min_order_value or quantity <= 0:
            return self._rejected_trade(
                symbol=symbol,
                side=PaperOrderSide.BUY,
                price=price,
                reason="Yetersiz nakit.",
                metadata=metadata,
            )

        now = self.time_fn()
        self.cash -= total_cost

        if existing:
            new_quantity = existing.quantity + quantity
            new_invested = existing.invested_value + gross + commission
            existing.quantity = new_quantity
            existing.invested_value = new_invested
            existing.average_price = new_invested / new_quantity
            existing.last_price = fill_price
            existing.updated_at = now
        else:
            self.positions[symbol] = PaperPosition(
                symbol=symbol,
                quantity=quantity,
                average_price=(gross + commission) / quantity,
                invested_value=gross + commission,
                opened_at=now,
                updated_at=now,
                last_price=fill_price,
            )

        trade = self._new_trade(
            symbol=symbol,
            side=PaperOrderSide.BUY,
            status=PaperOrderStatus.FILLED,
            quantity=quantity,
            requested_price=price,
            fill_price=fill_price,
            gross_value=gross,
            commission=commission,
            net_cash_effect=-total_cost,
            realized_pnl=0.0,
            reason=reason or "Sanal alış gerçekleşti.",
            metadata=metadata,
        )
        return trade

    def sell(
        self,
        *,
        symbol: str,
        price: float,
        quantity: float | None = None,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> PaperTrade:
        symbol = self.normalize_symbol(symbol)
        self._validate_price(price)

        position = self.positions.get(symbol)
        if not position:
            return self._rejected_trade(
                symbol=symbol,
                side=PaperOrderSide.SELL,
                price=price,
                reason="Satılacak açık pozisyon yok.",
                metadata=metadata,
            )

        sell_quantity = position.quantity if quantity is None else float(quantity)
        if sell_quantity <= 0:
            return self._rejected_trade(
                symbol=symbol,
                side=PaperOrderSide.SELL,
                price=price,
                reason="Satış miktarı pozitif olmalıdır.",
                metadata=metadata,
            )

        if sell_quantity > position.quantity:
            sell_quantity = position.quantity

        if not self.config.allow_partial_sell and sell_quantity < position.quantity:
            sell_quantity = position.quantity

        fill_price = price * (1.0 - self.config.slippage_rate)
        gross = sell_quantity * fill_price
        commission = gross * self.config.commission_rate
        net_proceeds = gross - commission

        cost_basis = position.invested_value * (
            sell_quantity / position.quantity
        )
        realized_pnl = net_proceeds - cost_basis

        self.cash += net_proceeds
        self.realized_pnl += realized_pnl

        remaining_quantity = position.quantity - sell_quantity
        remaining_invested = position.invested_value - cost_basis

        if remaining_quantity <= 1e-12:
            del self.positions[symbol]
        else:
            position.quantity = remaining_quantity
            position.invested_value = remaining_invested
            position.average_price = remaining_invested / remaining_quantity
            position.last_price = fill_price
            position.updated_at = self.time_fn()

        return self._new_trade(
            symbol=symbol,
            side=PaperOrderSide.SELL,
            status=PaperOrderStatus.FILLED,
            quantity=sell_quantity,
            requested_price=price,
            fill_price=fill_price,
            gross_value=gross,
            commission=commission,
            net_cash_effect=net_proceeds,
            realized_pnl=realized_pnl,
            reason=reason or "Sanal satış gerçekleşti.",
            metadata=metadata,
        )

    def close_all(
        self,
        prices: dict[str, float],
        reason: str = "Tüm pozisyonları kapat.",
    ) -> list[PaperTrade]:
        results: list[PaperTrade] = []
        for symbol in list(self.positions):
            price = prices.get(symbol)
            if price is None:
                continue
            results.append(
                self.sell(
                    symbol=symbol,
                    price=price,
                    quantity=None,
                    reason=reason,
                )
            )
        return results

    def snapshot(self) -> PaperPortfolioSnapshot:
        invested_value = sum(
            position.invested_value for position in self.positions.values()
        )
        market_value = sum(
            position.market_value for position in self.positions.values()
        )
        unrealized_pnl = market_value - invested_value
        equity = self.cash + market_value
        total_pnl = equity - self.config.starting_cash
        total_pnl_pct = (
            total_pnl / self.config.starting_cash * 100.0
            if self.config.starting_cash
            else 0.0
        )
        return PaperPortfolioSnapshot(
            cash=self.cash,
            invested_value=invested_value,
            market_value=market_value,
            equity=equity,
            realized_pnl=self.realized_pnl,
            unrealized_pnl=unrealized_pnl,
            total_pnl=total_pnl,
            total_pnl_pct=total_pnl_pct,
            open_positions=len(self.positions),
            trade_count=len(self.trades),
        )

    def positions_report(self) -> list[dict[str, Any]]:
        return [
            self.positions[symbol].to_dict()
            for symbol in sorted(self.positions)
        ]

    def trades_report(self, limit: int = 100) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        return [trade.to_dict() for trade in self.trades[-limit:]]

    def _resolve_price(
        self,
        decision: StrategyDecision,
        context: dict[str, Any],
    ) -> float:
        if decision.price is not None:
            return float(decision.price)

        kline = context.get("kline") or {}
        if isinstance(kline, dict) and kline.get("close") is not None:
            return float(kline["close"])

        snapshot = context.get("market_snapshot") or {}
        last_prices = snapshot.get("last_prices") or {}
        symbol = self.normalize_symbol(decision.symbol)
        if symbol in last_prices:
            return float(last_prices[symbol])

        raise ValueError("Emir için fiyat bulunamadı.")

    @staticmethod
    def _validate_price(price: float) -> None:
        if price <= 0 or not math.isfinite(price):
            raise ValueError("Fiyat pozitif ve sonlu olmalıdır.")

    def _rejected_trade(
        self,
        *,
        symbol: str,
        side: PaperOrderSide,
        price: float,
        reason: str,
        metadata: dict[str, Any] | None,
    ) -> PaperTrade:
        return self._new_trade(
            symbol=symbol,
            side=side,
            status=PaperOrderStatus.REJECTED,
            quantity=0.0,
            requested_price=price,
            fill_price=0.0,
            gross_value=0.0,
            commission=0.0,
            net_cash_effect=0.0,
            realized_pnl=0.0,
            reason=reason,
            metadata=metadata,
        )

    def _new_trade(
        self,
        *,
        symbol: str,
        side: PaperOrderSide,
        status: PaperOrderStatus,
        quantity: float,
        requested_price: float,
        fill_price: float,
        gross_value: float,
        commission: float,
        net_cash_effect: float,
        realized_pnl: float,
        reason: str,
        metadata: dict[str, Any] | None,
    ) -> PaperTrade:
        self._trade_id += 1
        trade = PaperTrade(
            trade_id=self._trade_id,
            symbol=symbol,
            side=side,
            status=status,
            quantity=quantity,
            requested_price=requested_price,
            fill_price=fill_price,
            gross_value=gross_value,
            commission=commission,
            net_cash_effect=net_cash_effect,
            realized_pnl=realized_pnl,
            reason=reason,
            timestamp=self.time_fn(),
            metadata=dict(metadata or {}),
        )
        self.trades.append(trade)
        if len(self.trades) > self.config.max_trade_history:
            del self.trades[: len(self.trades) - self.config.max_trade_history]
        return trade


class PaperTradingExecutionAdapter:
    def __init__(self, portfolio: PaperPortfolio) -> None:
        self.portfolio = portfolio

    def execute(
        self,
        decision: StrategyDecision,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return self.portfolio.execute_decision(decision, context)

    def update_market_price(self, symbol: str, price: float) -> None:
        self.portfolio.update_price(symbol, price)

    def health_report(self) -> dict[str, Any]:
        snapshot = self.portfolio.snapshot()
        return {
            "cash": snapshot.cash,
            "equity": snapshot.equity,
            "open_positions": snapshot.open_positions,
            "trade_count": snapshot.trade_count,
            "total_pnl": snapshot.total_pnl,
            "total_pnl_pct": snapshot.total_pnl_pct,
        }


class PaperTradingRobotBridge:
    def __init__(
        self,
        *,
        runtime: Any,
        portfolio: PaperPortfolio | None = None,
        execution_adapter: PaperTradingExecutionAdapter | None = None,
    ) -> None:
        self.runtime = runtime
        self.portfolio = portfolio or PaperPortfolio()
        self.execution_adapter = execution_adapter or PaperTradingExecutionAdapter(
            self.portfolio
        )
        self.bound = False

    def bind(self) -> None:
        if self.bound:
            return
        self.runtime.execution = self.execution_adapter
        self.runtime.market_data_engine.add_callback(self._on_market_event)
        self.bound = True

    def _on_market_event(self, event: Any) -> None:
        symbol = getattr(event, "symbol", "")
        payload = getattr(event, "payload", None)
        price = None
        if payload is not None:
            if hasattr(payload, "close"):
                price = getattr(payload, "close")
            elif hasattr(payload, "price"):
                price = getattr(payload, "price")
            elif hasattr(payload, "last_price"):
                price = getattr(payload, "last_price")
        if symbol and price is not None:
            self.portfolio.update_price(symbol, float(price))

    def dashboard(self) -> dict[str, Any]:
        return {
            "bound": self.bound,
            "portfolio": self.portfolio.snapshot().to_dict(),
            "positions": self.portfolio.positions_report(),
            "recent_trades": self.portfolio.trades_report(limit=20),
        }
