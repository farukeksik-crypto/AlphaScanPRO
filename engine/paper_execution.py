from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(str, Enum):
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


@dataclass
class PaperBrokerConfig:
    starting_cash: float = 100_000.0
    commission_rate: float = 0.001
    slippage_rate: float = 0.0005
    allow_partial_fills: bool = True
    default_liquidity_fraction: float = 1.0


@dataclass
class PaperOrder:
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    limit_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    order_id: str = field(default_factory=lambda: uuid4().hex)
    status: OrderStatus = OrderStatus.NEW
    filled_quantity: float = 0.0
    average_fill_price: float = 0.0
    commission_paid: float = 0.0
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    reject_reason: str = ""

    @property
    def remaining_quantity(self) -> float:
        return max(0.0, self.quantity - self.filled_quantity)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["side"] = self.side.value
        data["order_type"] = self.order_type.value
        data["status"] = self.status.value
        data["remaining_quantity"] = self.remaining_quantity
        return data


@dataclass
class PaperFill:
    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    commission: float
    fill_id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["side"] = self.side.value
        return data


@dataclass
class PaperPosition:
    symbol: str
    quantity: float = 0.0
    average_price: float = 0.0
    realized_pnl: float = 0.0
    stop_loss: float | None = None
    take_profit: float | None = None
    updated_at: str = field(default_factory=utc_now_iso)

    def market_value(self, market_price: float) -> float:
        return self.quantity * market_price

    def unrealized_pnl(self, market_price: float) -> float:
        return (market_price - self.average_price) * self.quantity

    def to_dict(self, market_price: float | None = None) -> dict[str, Any]:
        data = asdict(self)
        if market_price is not None:
            data["market_price"] = market_price
            data["market_value"] = self.market_value(market_price)
            data["unrealized_pnl"] = self.unrealized_pnl(market_price)
        return data


class PaperExecutionEngine:
    def __init__(self, config: PaperBrokerConfig | None = None) -> None:
        self.config = config or PaperBrokerConfig()
        if self.config.starting_cash <= 0:
            raise ValueError("starting_cash 0'dan büyük olmalıdır.")
        self.cash = float(self.config.starting_cash)
        self.orders: dict[str, PaperOrder] = {}
        self.fills: list[PaperFill] = []
        self.positions: dict[str, PaperPosition] = {}
        self.last_prices: dict[str, float] = {}
        self.logs: list[dict[str, Any]] = []

    def submit_order(
        self,
        *,
        symbol: str,
        side: OrderSide | str,
        order_type: OrderType | str,
        quantity: float,
        limit_price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> PaperOrder:
        side_enum = side if isinstance(side, OrderSide) else OrderSide(side.upper())
        type_enum = (
            order_type
            if isinstance(order_type, OrderType)
            else OrderType(order_type.upper())
        )

        if quantity <= 0:
            raise ValueError("quantity 0'dan büyük olmalıdır.")
        if type_enum == OrderType.LIMIT and (limit_price is None or limit_price <= 0):
            raise ValueError("LIMIT emir için geçerli limit_price gereklidir.")

        order = PaperOrder(
            symbol=symbol,
            side=side_enum,
            order_type=type_enum,
            quantity=float(quantity),
            limit_price=limit_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        self.orders[order.order_id] = order
        self._log("ORDER_SUBMITTED", order.to_dict())
        return order

    def process_order(
        self,
        order_id: str,
        *,
        market_price: float,
        available_liquidity: float | None = None,
    ) -> PaperOrder:
        order = self._get_order(order_id)
        if order.status in {
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
        }:
            return order
        if market_price <= 0:
            raise ValueError("market_price 0'dan büyük olmalıdır.")

        self.last_prices[order.symbol] = float(market_price)

        if not self._is_executable(order, market_price):
            return order

        liquidity = (
            available_liquidity
            if available_liquidity is not None
            else order.remaining_quantity * self.config.default_liquidity_fraction
        )
        if liquidity <= 0:
            return order

        fill_quantity = min(order.remaining_quantity, float(liquidity))
        if (
            not self.config.allow_partial_fills
            and fill_quantity < order.remaining_quantity
        ):
            return order

        fill_price = self._apply_slippage(
            market_price=market_price,
            side=order.side,
        )
        notional = fill_quantity * fill_price
        commission = notional * self.config.commission_rate

        if order.side == OrderSide.BUY:
            total_cost = notional + commission
            if total_cost > self.cash:
                affordable_qty = self.cash / (
                    fill_price * (1 + self.config.commission_rate)
                )
                if affordable_qty <= 0:
                    return self._reject(order, "Yetersiz sanal bakiye.")
                if not self.config.allow_partial_fills:
                    return self._reject(order, "Yetersiz sanal bakiye.")
                fill_quantity = min(fill_quantity, affordable_qty)
                notional = fill_quantity * fill_price
                commission = notional * self.config.commission_rate
                total_cost = notional + commission
            self.cash -= total_cost
            self._apply_buy_fill(
                order=order,
                quantity=fill_quantity,
                price=fill_price,
            )
        else:
            position = self.positions.get(order.symbol)
            available_qty = 0.0 if position is None else position.quantity
            if fill_quantity > available_qty:
                if available_qty <= 0:
                    return self._reject(order, "Satılabilir pozisyon bulunamadı.")
                if not self.config.allow_partial_fills:
                    return self._reject(order, "Yetersiz pozisyon miktarı.")
                fill_quantity = available_qty
                notional = fill_quantity * fill_price
                commission = notional * self.config.commission_rate
            self.cash += notional - commission
            self._apply_sell_fill(
                order=order,
                quantity=fill_quantity,
                price=fill_price,
                commission=commission,
            )

        fill = PaperFill(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=fill_quantity,
            price=fill_price,
            commission=commission,
        )
        self.fills.append(fill)

        previous_filled = order.filled_quantity
        new_filled = previous_filled + fill_quantity
        if new_filled > 0:
            order.average_fill_price = (
                (order.average_fill_price * previous_filled)
                + (fill_price * fill_quantity)
            ) / new_filled
        order.filled_quantity = new_filled
        order.commission_paid += commission
        order.updated_at = utc_now_iso()
        order.status = (
            OrderStatus.FILLED
            if order.remaining_quantity <= 1e-12
            else OrderStatus.PARTIALLY_FILLED
        )
        self._log("ORDER_PROCESSED", order.to_dict())
        return order

    def process_price_update(
        self,
        *,
        symbol: str,
        market_price: float,
        available_liquidity: float | None = None,
    ) -> list[PaperOrder]:
        if market_price <= 0:
            raise ValueError("market_price 0'dan büyük olmalıdır.")
        self.last_prices[symbol] = float(market_price)

        processed: list[PaperOrder] = []
        for order in self.orders.values():
            if order.symbol != symbol:
                continue
            if order.status not in {OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED}:
                continue
            processed.append(
                self.process_order(
                    order.order_id,
                    market_price=market_price,
                    available_liquidity=available_liquidity,
                )
            )

        position = self.positions.get(symbol)
        if position is not None and position.quantity > 0:
            trigger_side: OrderSide | None = None
            trigger_reason = ""
            if position.stop_loss is not None and market_price <= position.stop_loss:
                trigger_side = OrderSide.SELL
                trigger_reason = "STOP_LOSS"
            elif (
                position.take_profit is not None
                and market_price >= position.take_profit
            ):
                trigger_side = OrderSide.SELL
                trigger_reason = "TAKE_PROFIT"

            if trigger_side is not None:
                exit_order = self.submit_order(
                    symbol=symbol,
                    side=trigger_side,
                    order_type=OrderType.MARKET,
                    quantity=position.quantity,
                )
                self._log(
                    "AUTO_EXIT_TRIGGERED",
                    {
                        "symbol": symbol,
                        "reason": trigger_reason,
                        "market_price": market_price,
                        "order_id": exit_order.order_id,
                    },
                )
                processed.append(
                    self.process_order(
                        exit_order.order_id,
                        market_price=market_price,
                        available_liquidity=available_liquidity,
                    )
                )

        return processed

    def cancel_order(self, order_id: str) -> PaperOrder:
        order = self._get_order(order_id)
        if order.status in {OrderStatus.FILLED, OrderStatus.REJECTED}:
            raise ValueError("Tamamlanmış veya reddedilmiş emir iptal edilemez.")
        order.status = OrderStatus.CANCELLED
        order.updated_at = utc_now_iso()
        self._log("ORDER_CANCELLED", order.to_dict())
        return order

    def account_report(self) -> dict[str, Any]:
        total_market_value = 0.0
        total_unrealized_pnl = 0.0
        position_rows = []

        for symbol, position in self.positions.items():
            market_price = self.last_prices.get(symbol, position.average_price)
            total_market_value += position.market_value(market_price)
            total_unrealized_pnl += position.unrealized_pnl(market_price)
            position_rows.append(position.to_dict(market_price))

        equity = self.cash + total_market_value
        total_realized_pnl = sum(
            position.realized_pnl
            for position in self.positions.values()
        )

        return {
            "starting_cash": self.config.starting_cash,
            "cash": round(self.cash, 8),
            "market_value": round(total_market_value, 8),
            "equity": round(equity, 8),
            "realized_pnl": round(total_realized_pnl, 8),
            "unrealized_pnl": round(total_unrealized_pnl, 8),
            "commission_paid": round(
                sum(fill.commission for fill in self.fills),
                8,
            ),
            "open_order_count": sum(
                order.status in {OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED}
                for order in self.orders.values()
            ),
            "positions": position_rows,
            "orders": [order.to_dict() for order in self.orders.values()],
            "fills": [fill.to_dict() for fill in self.fills],
            "log_count": len(self.logs),
        }

    def _apply_buy_fill(
        self,
        *,
        order: PaperOrder,
        quantity: float,
        price: float,
    ) -> None:
        position = self.positions.get(order.symbol)
        if position is None:
            position = PaperPosition(symbol=order.symbol)
            self.positions[order.symbol] = position

        old_quantity = position.quantity
        new_quantity = old_quantity + quantity
        position.average_price = (
            (position.average_price * old_quantity)
            + (price * quantity)
        ) / new_quantity
        position.quantity = new_quantity
        position.stop_loss = (
            order.stop_loss
            if order.stop_loss is not None
            else position.stop_loss
        )
        position.take_profit = (
            order.take_profit
            if order.take_profit is not None
            else position.take_profit
        )
        position.updated_at = utc_now_iso()

    def _apply_sell_fill(
        self,
        *,
        order: PaperOrder,
        quantity: float,
        price: float,
        commission: float,
    ) -> None:
        position = self.positions[order.symbol]
        gross_pnl = (price - position.average_price) * quantity
        position.realized_pnl += gross_pnl - commission
        position.quantity -= quantity
        if position.quantity <= 1e-12:
            position.quantity = 0.0
            position.average_price = 0.0
            position.stop_loss = None
            position.take_profit = None
        position.updated_at = utc_now_iso()

    def _is_executable(
        self,
        order: PaperOrder,
        market_price: float,
    ) -> bool:
        if order.order_type == OrderType.MARKET:
            return True
        if order.side == OrderSide.BUY:
            return market_price <= float(order.limit_price)
        return market_price >= float(order.limit_price)

    def _apply_slippage(
        self,
        *,
        market_price: float,
        side: OrderSide,
    ) -> float:
        direction = 1.0 if side == OrderSide.BUY else -1.0
        return market_price * (1 + direction * self.config.slippage_rate)

    def _reject(self, order: PaperOrder, reason: str) -> PaperOrder:
        order.status = OrderStatus.REJECTED
        order.reject_reason = reason
        order.updated_at = utc_now_iso()
        self._log("ORDER_REJECTED", order.to_dict())
        return order

    def _get_order(self, order_id: str) -> PaperOrder:
        order = self.orders.get(order_id)
        if order is None:
            raise KeyError(f"Emir bulunamadı: {order_id}")
        return order

    def _log(self, event: str, details: dict[str, Any]) -> None:
        self.logs.append(
            {
                "event": event,
                "details": details,
                "timestamp": utc_now_iso(),
            }
        )
