from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PaperOrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class PaperOrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class PaperOrderStatus(str, Enum):
    NEW = "NEW"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


@dataclass(slots=True)
class PaperBrokerConfig:
    starting_cash: float = 1_000_000.0
    commission_rate: float = 0.001
    slippage_rate: float = 0.0005
    allow_partial_fills: bool = True
    max_fill_ratio: float = 1.0
    allow_short_selling: bool = False

    def __post_init__(self) -> None:
        if self.starting_cash < 0:
            raise ValueError("starting_cash negatif olamaz.")
        if not 0 <= self.commission_rate < 1:
            raise ValueError("commission_rate 0 ile 1 arasında olmalıdır.")
        if not 0 <= self.slippage_rate < 1:
            raise ValueError("slippage_rate 0 ile 1 arasında olmalıdır.")
        if not 0 < self.max_fill_ratio <= 1:
            raise ValueError("max_fill_ratio 0'dan büyük ve 1'den küçük/eşit olmalıdır.")


@dataclass(slots=True)
class PaperOrderRequest:
    symbol: str
    side: PaperOrderSide
    order_type: PaperOrderType
    quantity: float
    limit_price: Optional[float] = None
    client_order_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.symbol = self.symbol.strip().upper()
        self.side = PaperOrderSide(self.side)
        self.order_type = PaperOrderType(self.order_type)

        if not self.symbol:
            raise ValueError("symbol boş olamaz.")
        if self.quantity <= 0:
            raise ValueError("quantity pozitif olmalıdır.")
        if self.order_type == PaperOrderType.LIMIT:
            if self.limit_price is None or self.limit_price <= 0:
                raise ValueError("Limit emirlerinde geçerli limit_price gereklidir.")
        if self.client_order_id is not None:
            self.client_order_id = self.client_order_id.strip() or None
        if not isinstance(self.metadata, dict):
            raise TypeError("metadata sözlük olmalıdır.")


@dataclass(slots=True)
class PaperFill:
    fill_id: str
    order_id: str
    symbol: str
    side: PaperOrderSide
    quantity: float
    price: float
    commission: float
    created_at: datetime = field(default_factory=utc_now)

    @property
    def gross_value(self) -> float:
        return self.quantity * self.price

    @property
    def net_cash_effect(self) -> float:
        if self.side == PaperOrderSide.BUY:
            return -(self.gross_value + self.commission)
        return self.gross_value - self.commission

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fill_id": self.fill_id,
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "price": self.price,
            "commission": self.commission,
            "gross_value": self.gross_value,
            "net_cash_effect": self.net_cash_effect,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(slots=True)
class PaperOrder:
    order_id: str
    request: PaperOrderRequest
    status: PaperOrderStatus = PaperOrderStatus.NEW
    filled_quantity: float = 0.0
    average_fill_price: float = 0.0
    fills: List[PaperFill] = field(default_factory=list)
    reject_reason: Optional[str] = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    @property
    def remaining_quantity(self) -> float:
        return max(self.request.quantity - self.filled_quantity, 0.0)

    @property
    def total_commission(self) -> float:
        return sum(fill.commission for fill in self.fills)

    @property
    def symbol(self) -> str:
        return self.request.symbol

    def add_fill(self, fill: PaperFill) -> None:
        previous_value = self.average_fill_price * self.filled_quantity
        new_value = fill.price * fill.quantity
        self.filled_quantity += fill.quantity
        self.average_fill_price = (
            (previous_value + new_value) / self.filled_quantity
            if self.filled_quantity > 0
            else 0.0
        )
        self.fills.append(fill)
        self.updated_at = utc_now()

        if self.remaining_quantity <= 1e-12:
            self.status = PaperOrderStatus.FILLED
        else:
            self.status = PaperOrderStatus.PARTIALLY_FILLED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "order_id": self.order_id,
            "client_order_id": self.request.client_order_id,
            "symbol": self.request.symbol,
            "side": self.request.side.value,
            "order_type": self.request.order_type.value,
            "quantity": self.request.quantity,
            "limit_price": self.request.limit_price,
            "status": self.status.value,
            "filled_quantity": self.filled_quantity,
            "remaining_quantity": self.remaining_quantity,
            "average_fill_price": self.average_fill_price,
            "total_commission": self.total_commission,
            "reject_reason": self.reject_reason,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": dict(self.request.metadata),
            "fills": [fill.to_dict() for fill in self.fills],
        }


class PaperBroker:
    def __init__(self, config: Optional[PaperBrokerConfig] = None) -> None:
        self.config = config or PaperBrokerConfig()
        self.cash = float(self.config.starting_cash)
        self.positions: Dict[str, float] = {}
        self._orders: Dict[str, PaperOrder] = {}
        self._client_order_ids: Dict[str, str] = {}
        self._fills: List[PaperFill] = []

    def submit_order(
        self,
        request: PaperOrderRequest,
        *,
        market_price: Optional[float] = None,
        available_liquidity: Optional[float] = None,
    ) -> PaperOrder:
        if request.client_order_id:
            existing_id = self._client_order_ids.get(request.client_order_id)
            if existing_id is not None:
                return self._orders[existing_id]

        order = PaperOrder(order_id=uuid4().hex, request=request)
        self._orders[order.order_id] = order
        if request.client_order_id:
            self._client_order_ids[request.client_order_id] = order.order_id

        if request.order_type == PaperOrderType.MARKET:
            if market_price is None or market_price <= 0:
                return self._reject(order, "Market emirlerinde geçerli market_price gereklidir.")
            return self._attempt_fill(
                order,
                market_price=market_price,
                available_liquidity=available_liquidity,
            )

        order.status = PaperOrderStatus.OPEN
        order.updated_at = utc_now()
        if market_price is not None:
            return self.process_order(
                order.order_id,
                market_price=market_price,
                available_liquidity=available_liquidity,
            )
        return order

    def process_order(
        self,
        order_id: str,
        *,
        market_price: float,
        available_liquidity: Optional[float] = None,
    ) -> PaperOrder:
        order = self.get_order(order_id)
        if order.status in {
            PaperOrderStatus.FILLED,
            PaperOrderStatus.CANCELLED,
            PaperOrderStatus.REJECTED,
        }:
            return order
        if market_price <= 0:
            raise ValueError("market_price pozitif olmalıdır.")

        if order.request.order_type == PaperOrderType.LIMIT:
            if not self._limit_is_marketable(order.request, market_price):
                order.status = PaperOrderStatus.OPEN
                order.updated_at = utc_now()
                return order

        return self._attempt_fill(
            order,
            market_price=market_price,
            available_liquidity=available_liquidity,
        )

    def _attempt_fill(
        self,
        order: PaperOrder,
        *,
        market_price: float,
        available_liquidity: Optional[float],
    ) -> PaperOrder:
        fill_quantity = self._determine_fill_quantity(
            order.remaining_quantity,
            available_liquidity=available_liquidity,
        )
        if fill_quantity <= 0:
            order.status = PaperOrderStatus.OPEN
            order.updated_at = utc_now()
            return order

        fill_price = self._execution_price(order.request, market_price)
        commission = fill_quantity * fill_price * self.config.commission_rate

        if order.request.side == PaperOrderSide.BUY:
            total_cost = fill_quantity * fill_price + commission
            if total_cost > self.cash + 1e-9:
                affordable_qty = self._max_affordable_quantity(fill_price)
                if affordable_qty <= 0:
                    return self._reject(order, "Yetersiz nakit bakiye.")
                if not self.config.allow_partial_fills:
                    return self._reject(order, "Yetersiz nakit bakiye.")
                fill_quantity = min(fill_quantity, affordable_qty)
                commission = fill_quantity * fill_price * self.config.commission_rate
        else:
            current_position = self.positions.get(order.symbol, 0.0)
            if not self.config.allow_short_selling and fill_quantity > current_position + 1e-9:
                if current_position <= 0:
                    return self._reject(order, "Yetersiz pozisyon miktarı.")
                if not self.config.allow_partial_fills:
                    return self._reject(order, "Yetersiz pozisyon miktarı.")
                fill_quantity = current_position
                commission = fill_quantity * fill_price * self.config.commission_rate

        if fill_quantity <= 0:
            return self._reject(order, "Gerçekleşebilir miktar bulunamadı.")

        fill = PaperFill(
            fill_id=uuid4().hex,
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.request.side,
            quantity=fill_quantity,
            price=fill_price,
            commission=commission,
        )
        self._apply_fill(fill)
        order.add_fill(fill)
        self._fills.append(fill)
        return order

    def _determine_fill_quantity(
        self,
        remaining_quantity: float,
        *,
        available_liquidity: Optional[float],
    ) -> float:
        fill_quantity = remaining_quantity * self.config.max_fill_ratio
        if available_liquidity is not None:
            if available_liquidity < 0:
                raise ValueError("available_liquidity negatif olamaz.")
            fill_quantity = min(fill_quantity, available_liquidity)

        if not self.config.allow_partial_fills and fill_quantity + 1e-12 < remaining_quantity:
            return 0.0
        return min(fill_quantity, remaining_quantity)

    def _execution_price(
        self,
        request: PaperOrderRequest,
        market_price: float,
    ) -> float:
        if request.order_type == PaperOrderType.LIMIT:
            assert request.limit_price is not None
            if request.side == PaperOrderSide.BUY:
                base_price = min(market_price, request.limit_price)
            else:
                base_price = max(market_price, request.limit_price)
        else:
            base_price = market_price

        if request.side == PaperOrderSide.BUY:
            return base_price * (1 + self.config.slippage_rate)
        return base_price * (1 - self.config.slippage_rate)

    @staticmethod
    def _limit_is_marketable(
        request: PaperOrderRequest,
        market_price: float,
    ) -> bool:
        assert request.limit_price is not None
        if request.side == PaperOrderSide.BUY:
            return market_price <= request.limit_price
        return market_price >= request.limit_price

    def _max_affordable_quantity(self, fill_price: float) -> float:
        divisor = fill_price * (1 + self.config.commission_rate)
        return self.cash / divisor if divisor > 0 else 0.0

    def _apply_fill(self, fill: PaperFill) -> None:
        self.cash += fill.net_cash_effect
        current = self.positions.get(fill.symbol, 0.0)
        if fill.side == PaperOrderSide.BUY:
            current += fill.quantity
        else:
            current -= fill.quantity
        if abs(current) <= 1e-12:
            self.positions.pop(fill.symbol, None)
        else:
            self.positions[fill.symbol] = current

    @staticmethod
    def _reject(order: PaperOrder, reason: str) -> PaperOrder:
        order.status = PaperOrderStatus.REJECTED
        order.reject_reason = reason
        order.updated_at = utc_now()
        return order

    def cancel_order(self, order_id: str) -> PaperOrder:
        order = self.get_order(order_id)
        if order.status in {
            PaperOrderStatus.FILLED,
            PaperOrderStatus.CANCELLED,
            PaperOrderStatus.REJECTED,
        }:
            return order
        order.status = PaperOrderStatus.CANCELLED
        order.updated_at = utc_now()
        return order

    def get_order(self, order_id: str) -> PaperOrder:
        return self._orders[order_id]

    def orders(self) -> List[PaperOrder]:
        return list(self._orders.values())

    def open_orders(self) -> List[PaperOrder]:
        return [
            order
            for order in self._orders.values()
            if order.status in {
                PaperOrderStatus.OPEN,
                PaperOrderStatus.PARTIALLY_FILLED,
            }
        ]

    def fills(self) -> List[PaperFill]:
        return list(self._fills)

    def position(self, symbol: str) -> float:
        return self.positions.get(symbol.strip().upper(), 0.0)

    def equity(self, market_prices: Optional[Dict[str, float]] = None) -> float:
        market_prices = market_prices or {}
        total = self.cash
        for symbol, quantity in self.positions.items():
            price = market_prices.get(symbol)
            if price is None:
                continue
            total += quantity * price
        return total

    def dashboard(self, market_prices: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        status_counts: Dict[str, int] = {}
        for order in self._orders.values():
            status_counts[order.status.value] = status_counts.get(order.status.value, 0) + 1

        return {
            "cash": self.cash,
            "equity": self.equity(market_prices),
            "positions": dict(self.positions),
            "order_count": len(self._orders),
            "open_order_count": len(self.open_orders()),
            "fill_count": len(self._fills),
            "status_counts": status_counts,
            "total_commission": sum(fill.commission for fill in self._fills),
        }
