from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from threading import Lock
from typing import Any, Deque, Dict, List, Optional, Protocol
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderStatus(str, Enum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


class ExecutionDecision(str, Enum):
    ACCEPTED = "ACCEPTED"
    RETRY = "RETRY"
    FINAL = "FINAL"


@dataclass(slots=True)
class OrderRequest:
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    client_order_id: str = field(default_factory=lambda: uuid4().hex)
    created_at: datetime = field(default_factory=utc_now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.symbol = self.symbol.strip().upper()
        self.side = OrderSide(self.side)
        self.order_type = OrderType(self.order_type)
        if not self.symbol:
            raise ValueError("symbol boş olamaz.")
        if self.quantity <= 0:
            raise ValueError("quantity pozitif olmalıdır.")
        if self.order_type == OrderType.LIMIT:
            if self.limit_price is None or self.limit_price <= 0:
                raise ValueError("LIMIT emir için geçerli limit_price gereklidir.")
        if self.order_type == OrderType.MARKET and self.limit_price is not None:
            if self.limit_price <= 0:
                raise ValueError("limit_price pozitif olmalıdır.")
        if not isinstance(self.metadata, dict):
            raise TypeError("metadata sözlük olmalıdır.")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "side": self.side.value,
            "quantity": self.quantity,
            "order_type": self.order_type.value,
            "limit_price": self.limit_price,
            "client_order_id": self.client_order_id,
            "created_at": self.created_at.isoformat(),
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class Fill:
    quantity: float
    price: float
    commission: float = 0.0
    timestamp: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("fill quantity pozitif olmalıdır.")
        if self.price <= 0:
            raise ValueError("fill price pozitif olmalıdır.")
        if self.commission < 0:
            raise ValueError("commission negatif olamaz.")

    @property
    def gross_value(self) -> float:
        return self.quantity * self.price


@dataclass(slots=True)
class OrderRecord:
    request: OrderRequest
    status: OrderStatus = OrderStatus.CREATED
    fills: List[Fill] = field(default_factory=list)
    submitted_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    broker_order_id: Optional[str] = None
    retry_count: int = 0
    last_error: Optional[str] = None
    status_history: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._record_status(self.status, "order created")

    @property
    def client_order_id(self) -> str:
        return self.request.client_order_id

    @property
    def filled_quantity(self) -> float:
        return sum(item.quantity for item in self.fills)

    @property
    def remaining_quantity(self) -> float:
        return max(0.0, self.request.quantity - self.filled_quantity)

    @property
    def average_fill_price(self) -> Optional[float]:
        if not self.fills:
            return None
        total_value = sum(item.gross_value for item in self.fills)
        return total_value / self.filled_quantity

    @property
    def total_commission(self) -> float:
        return sum(item.commission for item in self.fills)

    @property
    def gross_value(self) -> float:
        return sum(item.gross_value for item in self.fills)

    @property
    def is_terminal(self) -> bool:
        return self.status in {
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
            OrderStatus.FAILED,
        }

    def _record_status(self, status: OrderStatus, reason: Optional[str]) -> None:
        self.status_history.append(
            {
                "status": status.value,
                "timestamp": utc_now().isoformat(),
                "reason": reason,
            }
        )

    def set_status(self, status: OrderStatus, reason: Optional[str] = None) -> None:
        status = OrderStatus(status)
        if self.is_terminal and status != self.status:
            raise RuntimeError("Terminal durumdaki emir değiştirilemez.")
        self.status = status
        if status == OrderStatus.SUBMITTED and self.submitted_at is None:
            self.submitted_at = utc_now()
        if status in {
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
            OrderStatus.FAILED,
        }:
            self.completed_at = utc_now()
        self._record_status(status, reason)

    def add_fill(self, fill: Fill) -> None:
        if self.is_terminal:
            raise RuntimeError("Terminal emre fill eklenemez.")
        if fill.quantity > self.remaining_quantity + 1e-12:
            raise ValueError("Fill miktarı kalan miktarı aşamaz.")
        self.fills.append(fill)
        if self.remaining_quantity <= 1e-12:
            self.set_status(OrderStatus.FILLED, "fully filled")
        else:
            self.set_status(OrderStatus.PARTIALLY_FILLED, "partial fill")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request": self.request.to_dict(),
            "status": self.status.value,
            "filled_quantity": self.filled_quantity,
            "remaining_quantity": self.remaining_quantity,
            "average_fill_price": self.average_fill_price,
            "total_commission": self.total_commission,
            "gross_value": self.gross_value,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "broker_order_id": self.broker_order_id,
            "retry_count": self.retry_count,
            "last_error": self.last_error,
            "status_history": list(self.status_history),
        }


@dataclass(slots=True)
class BrokerResponse:
    decision: ExecutionDecision
    broker_order_id: Optional[str] = None
    fills: List[Fill] = field(default_factory=list)
    error: Optional[str] = None


class BrokerAdapter(Protocol):
    def submit(self, order: OrderRecord, market_price: Optional[float] = None) -> BrokerResponse:
        ...

    def cancel(self, order: OrderRecord) -> bool:
        ...


@dataclass(slots=True)
class SimulatedBrokerConfig:
    commission_rate: float = 0.001
    slippage_pct: float = 0.0
    partial_fill_ratio: float = 1.0
    reject_symbols: List[str] = field(default_factory=list)
    retry_failures: int = 0

    def __post_init__(self) -> None:
        if self.commission_rate < 0:
            raise ValueError("commission_rate negatif olamaz.")
        if self.slippage_pct < 0:
            raise ValueError("slippage_pct negatif olamaz.")
        if not 0 < self.partial_fill_ratio <= 1:
            raise ValueError("partial_fill_ratio 0-1 aralığında olmalıdır.")
        if self.retry_failures < 0:
            raise ValueError("retry_failures negatif olamaz.")
        self.reject_symbols = [item.strip().upper() for item in self.reject_symbols]


class SimulatedBroker:
    def __init__(self, config: Optional[SimulatedBrokerConfig] = None) -> None:
        self.config = config or SimulatedBrokerConfig()
        self._attempts: Dict[str, int] = {}

    def submit(self, order: OrderRecord, market_price: Optional[float] = None) -> BrokerResponse:
        request = order.request
        if request.symbol in self.config.reject_symbols:
            return BrokerResponse(
                decision=ExecutionDecision.FINAL,
                error="symbol rejected",
            )

        attempts = self._attempts.get(order.client_order_id, 0)
        self._attempts[order.client_order_id] = attempts + 1
        if attempts < self.config.retry_failures:
            return BrokerResponse(
                decision=ExecutionDecision.RETRY,
                error="temporary broker failure",
            )

        if request.order_type == OrderType.LIMIT:
            execution_price = request.limit_price
        else:
            if market_price is None or market_price <= 0:
                return BrokerResponse(
                    decision=ExecutionDecision.RETRY,
                    error="market price unavailable",
                )
            direction = 1 if request.side == OrderSide.BUY else -1
            execution_price = market_price * (
                1 + direction * self.config.slippage_pct / 100
            )

        fill_quantity = min(
            order.remaining_quantity,
            request.quantity * self.config.partial_fill_ratio,
        )
        if fill_quantity <= 0:
            return BrokerResponse(
                decision=ExecutionDecision.FINAL,
                broker_order_id=order.broker_order_id,
            )

        gross = fill_quantity * execution_price
        fill = Fill(
            quantity=fill_quantity,
            price=execution_price,
            commission=gross * self.config.commission_rate,
        )
        return BrokerResponse(
            decision=ExecutionDecision.ACCEPTED,
            broker_order_id=order.broker_order_id or f"SIM-{uuid4().hex[:12]}",
            fills=[fill],
        )

    def cancel(self, order: OrderRecord) -> bool:
        return not order.is_terminal


@dataclass(slots=True)
class OrderManagerConfig:
    max_retries: int = 3
    order_timeout_seconds: float = 60.0
    block_duplicate_active_orders: bool = True
    history_limit: int = 1000

    def __post_init__(self) -> None:
        if self.max_retries < 0:
            raise ValueError("max_retries negatif olamaz.")
        if self.order_timeout_seconds <= 0:
            raise ValueError("order_timeout_seconds pozitif olmalıdır.")
        if self.history_limit <= 0:
            raise ValueError("history_limit pozitif olmalıdır.")


class OrderManager:
    def __init__(
        self,
        broker: BrokerAdapter,
        config: Optional[OrderManagerConfig] = None,
    ) -> None:
        if broker is None:
            raise TypeError("broker gereklidir.")
        self.broker = broker
        self.config = config or OrderManagerConfig()
        self._orders: Dict[str, OrderRecord] = {}
        self._queue: Deque[str] = deque()
        self._history: Deque[str] = deque(maxlen=self.config.history_limit)
        self._lock = Lock()

    def _active_duplicate_exists(self, request: OrderRequest) -> bool:
        return any(
            not order.is_terminal
            and order.request.symbol == request.symbol
            and order.request.side == request.side
            and order.request.order_type == request.order_type
            for order in self._orders.values()
        )

    def create_order(self, request: OrderRequest) -> OrderRecord:
        if not isinstance(request, OrderRequest):
            raise TypeError("request OrderRequest olmalıdır.")
        with self._lock:
            if request.client_order_id in self._orders:
                raise ValueError("client_order_id zaten mevcut.")
            if (
                self.config.block_duplicate_active_orders
                and self._active_duplicate_exists(request)
            ):
                raise ValueError("Aktif duplicate emir engellendi.")
            record = OrderRecord(request=request)
            self._orders[request.client_order_id] = record
            self._history.append(request.client_order_id)
            return record

    def queue_order(self, client_order_id: str) -> OrderRecord:
        with self._lock:
            order = self._orders[client_order_id]
            if order.is_terminal:
                raise RuntimeError("Terminal emir kuyruğa alınamaz.")
            if client_order_id not in self._queue:
                self._queue.append(client_order_id)
            order.set_status(OrderStatus.QUEUED, "queued")
            return order

    def submit_order(
        self,
        client_order_id: str,
        *,
        market_price: Optional[float] = None,
    ) -> OrderRecord:
        with self._lock:
            order = self._orders[client_order_id]

        if order.is_terminal:
            return order

        order.set_status(OrderStatus.SUBMITTED, "submitted")
        response = self.broker.submit(order, market_price)

        if response.broker_order_id:
            order.broker_order_id = response.broker_order_id

        if response.decision == ExecutionDecision.RETRY:
            order.retry_count += 1
            order.last_error = response.error
            if order.retry_count > self.config.max_retries:
                order.set_status(OrderStatus.FAILED, response.error or "retry limit exceeded")
            else:
                order.set_status(OrderStatus.QUEUED, response.error or "retry requested")
                with self._lock:
                    if client_order_id not in self._queue:
                        self._queue.append(client_order_id)
            return order

        if response.error and response.decision == ExecutionDecision.FINAL:
            order.last_error = response.error
            order.set_status(OrderStatus.REJECTED, response.error)
            return order

        for fill in response.fills:
            order.add_fill(fill)

        if not response.fills and response.decision == ExecutionDecision.FINAL:
            order.set_status(OrderStatus.CANCELLED, "final without fill")

        return order

    def process_next(self, *, market_prices: Optional[Dict[str, float]] = None) -> Optional[OrderRecord]:
        with self._lock:
            if not self._queue:
                return None
            client_order_id = self._queue.popleft()
            order = self._orders[client_order_id]

        price = None
        if market_prices is not None:
            price = market_prices.get(order.request.symbol)
        return self.submit_order(client_order_id, market_price=price)

    def process_all(
        self,
        *,
        market_prices: Optional[Dict[str, float]] = None,
        max_items: Optional[int] = None,
    ) -> List[OrderRecord]:
        if max_items is not None and max_items <= 0:
            raise ValueError("max_items pozitif olmalıdır.")
        processed: List[OrderRecord] = []
        count = 0
        while True:
            with self._lock:
                has_items = bool(self._queue)
            if not has_items:
                break
            if max_items is not None and count >= max_items:
                break
            item = self.process_next(market_prices=market_prices)
            if item is not None:
                processed.append(item)
            count += 1
        return processed

    def cancel_order(self, client_order_id: str) -> OrderRecord:
        with self._lock:
            order = self._orders[client_order_id]
        if order.is_terminal:
            return order
        if self.broker.cancel(order):
            order.set_status(OrderStatus.CANCELLED, "cancelled by user")
            with self._lock:
                self._queue = deque(
                    item for item in self._queue if item != client_order_id
                )
        return order

    def expire_orders(self, now: Optional[datetime] = None) -> List[OrderRecord]:
        now = now or utc_now()
        expired: List[OrderRecord] = []
        threshold = timedelta(seconds=self.config.order_timeout_seconds)
        for order in list(self._orders.values()):
            if order.is_terminal:
                continue
            reference = order.submitted_at or order.request.created_at
            if now - reference >= threshold:
                order.set_status(OrderStatus.EXPIRED, "order timeout")
                expired.append(order)
        if expired:
            expired_ids = {item.client_order_id for item in expired}
            with self._lock:
                self._queue = deque(
                    item for item in self._queue if item not in expired_ids
                )
        return expired

    def get_order(self, client_order_id: str) -> OrderRecord:
        return self._orders[client_order_id]

    def active_orders(self) -> List[OrderRecord]:
        return [item for item in self._orders.values() if not item.is_terminal]

    def terminal_orders(self) -> List[OrderRecord]:
        return [item for item in self._orders.values() if item.is_terminal]

    def history(self, limit: Optional[int] = None) -> List[OrderRecord]:
        ids = list(self._history)
        if limit is not None:
            if limit < 0:
                raise ValueError("limit negatif olamaz.")
            ids = ids[-limit:] if limit else []
        return [self._orders[item] for item in ids]

    def dashboard(self) -> Dict[str, Any]:
        orders = list(self._orders.values())
        status_counts: Dict[str, int] = {}
        for order in orders:
            status_counts[order.status.value] = status_counts.get(order.status.value, 0) + 1
        return {
            "total_orders": len(orders),
            "active_orders": len(self.active_orders()),
            "terminal_orders": len(self.terminal_orders()),
            "queued_orders": len(self._queue),
            "status_counts": status_counts,
            "filled_value": sum(item.gross_value for item in orders),
            "total_commission": sum(item.total_commission for item in orders),
        }


class OrderRuntimeBridge:
    def __init__(self, manager: OrderManager) -> None:
        self.manager = manager

    def submit_decision(
        self,
        decision: Any,
        *,
        market_price: Optional[float] = None,
    ) -> OrderRecord:
        action = getattr(decision, "action", None)
        action_value = getattr(action, "value", action)
        side = OrderSide(str(action_value).upper())
        request = OrderRequest(
            symbol=getattr(decision, "symbol"),
            side=side,
            quantity=float(getattr(decision, "quantity")),
            order_type=OrderType.MARKET,
            metadata={
                "score": getattr(decision, "score", None),
                "reason": getattr(decision, "reason", None),
            },
        )
        order = self.manager.create_order(request)
        self.manager.queue_order(order.client_order_id)
        return self.manager.submit_order(
            order.client_order_id,
            market_price=market_price,
        )
