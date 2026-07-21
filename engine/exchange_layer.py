from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable
from uuid import uuid4
import time


class ExchangeMode(str, Enum):
    PAPER = "PAPER"
    TESTNET = "TESTNET"
    LIVE = "LIVE"


class ExchangeOrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class ExchangeOrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class ExchangeOrderStatus(str, Enum):
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


@dataclass
class ExchangeConfig:
    mode: ExchangeMode = ExchangeMode.TESTNET
    exchange_name: str = "BINANCE"
    api_key: str = ""
    api_secret: str = ""
    recv_window_ms: int = 5_000
    request_timeout_seconds: float = 20.0
    max_retries: int = 3
    retry_delay_seconds: float = 0.0
    rate_limit_per_minute: int = 1_200
    allow_live_trading: bool = False

    def validate(self) -> None:
        if self.recv_window_ms <= 0:
            raise ValueError("recv_window_ms 0'dan büyük olmalıdır.")
        if self.request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds 0'dan büyük olmalıdır.")
        if self.max_retries < 0:
            raise ValueError("max_retries negatif olamaz.")
        if self.rate_limit_per_minute <= 0:
            raise ValueError("rate_limit_per_minute 0'dan büyük olmalıdır.")
        if self.mode == ExchangeMode.LIVE and not self.allow_live_trading:
            raise ValueError(
                "Canlı işlem için allow_live_trading=True açıkça verilmelidir."
            )


@dataclass
class ExchangeOrderRequest:
    symbol: str
    side: ExchangeOrderSide
    order_type: ExchangeOrderType
    quantity: float
    price: float | None = None
    stop_price: float | None = None
    client_order_id: str = field(default_factory=lambda: uuid4().hex)

    def validate(self) -> None:
        if not self.symbol:
            raise ValueError("symbol boş olamaz.")
        if self.quantity <= 0:
            raise ValueError("quantity 0'dan büyük olmalıdır.")
        if self.order_type in {
            ExchangeOrderType.LIMIT,
            ExchangeOrderType.STOP_LIMIT,
        } and (self.price is None or self.price <= 0):
            raise ValueError("Bu emir tipi için geçerli price gereklidir.")
        if self.order_type in {
            ExchangeOrderType.STOP,
            ExchangeOrderType.STOP_LIMIT,
        } and (self.stop_price is None or self.stop_price <= 0):
            raise ValueError("Bu emir tipi için geçerli stop_price gereklidir.")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["side"] = self.side.value
        data["order_type"] = self.order_type.value
        return data


@dataclass
class ExchangeOrder:
    exchange_order_id: str
    client_order_id: str
    symbol: str
    side: ExchangeOrderSide
    order_type: ExchangeOrderType
    status: ExchangeOrderStatus
    quantity: float
    filled_quantity: float = 0.0
    average_price: float = 0.0
    commission: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)

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
class ExchangeBalance:
    asset: str
    free: float
    locked: float = 0.0

    @property
    def total(self) -> float:
        return self.free + self.locked

    def to_dict(self) -> dict[str, float | str]:
        return {
            "asset": self.asset,
            "free": self.free,
            "locked": self.locked,
            "total": self.total,
        }


@dataclass
class ExchangePosition:
    symbol: str
    quantity: float
    average_price: float
    current_price: float = 0.0

    @property
    def unrealized_pnl(self) -> float:
        return (self.current_price - self.average_price) * self.quantity

    def to_dict(self) -> dict[str, float | str]:
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "average_price": self.average_price,
            "current_price": self.current_price,
            "unrealized_pnl": self.unrealized_pnl,
        }


class ExchangeError(RuntimeError):
    pass


class ExchangeConnectionError(ExchangeError):
    pass


class ExchangeAuthenticationError(ExchangeError):
    pass


class ExchangeRateLimitError(ExchangeError):
    pass


class ExchangeOrderError(ExchangeError):
    pass


class RetryExecutor:
    def __init__(
        self,
        *,
        max_retries: int,
        delay_seconds: float = 0.0,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.max_retries = max_retries
        self.delay_seconds = delay_seconds
        self.sleep_fn = sleep_fn

    def run(
        self,
        operation: Callable[[], Any],
        *,
        retry_on: tuple[type[BaseException], ...] = (
            ExchangeConnectionError,
            ExchangeRateLimitError,
        ),
    ) -> Any:
        last_error: BaseException | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return operation()
            except retry_on as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise
                if self.delay_seconds > 0:
                    self.sleep_fn(self.delay_seconds)
        if last_error is not None:
            raise last_error
        raise ExchangeError("İşlem tamamlanamadı.")


class ExchangeAdapter(ABC):
    def __init__(self, config: ExchangeConfig) -> None:
        config.validate()
        self.config = config
        self.connected = False
        self.retry = RetryExecutor(
            max_retries=config.max_retries,
            delay_seconds=config.retry_delay_seconds,
        )

    @abstractmethod
    def connect(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def disconnect(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_balances(self) -> list[ExchangeBalance]:
        raise NotImplementedError

    @abstractmethod
    def get_positions(self) -> list[ExchangePosition]:
        raise NotImplementedError

    @abstractmethod
    def place_order(self, request: ExchangeOrderRequest) -> ExchangeOrder:
        raise NotImplementedError

    @abstractmethod
    def get_order(self, exchange_order_id: str) -> ExchangeOrder:
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, exchange_order_id: str) -> ExchangeOrder:
        raise NotImplementedError

    def health_report(self) -> dict[str, Any]:
        return {
            "exchange": self.config.exchange_name,
            "mode": self.config.mode.value,
            "connected": self.connected,
            "live_trading_allowed": self.config.allow_live_trading,
        }


class InMemoryExchangeAdapter(ExchangeAdapter):
    def __init__(
        self,
        config: ExchangeConfig | None = None,
        *,
        starting_balances: dict[str, float] | None = None,
        prices: dict[str, float] | None = None,
    ) -> None:
        super().__init__(config or ExchangeConfig())
        self.balances: dict[str, ExchangeBalance] = {
            asset: ExchangeBalance(asset=asset, free=float(amount))
            for asset, amount in (starting_balances or {"USDT": 100_000.0}).items()
        }
        self.prices = dict(prices or {})
        self.orders: dict[str, ExchangeOrder] = {}
        self.positions: dict[str, ExchangePosition] = {}

    def connect(self) -> bool:
        self.connected = True
        return True

    def disconnect(self) -> None:
        self.connected = False

    def get_balances(self) -> list[ExchangeBalance]:
        self._require_connection()
        return list(self.balances.values())

    def get_positions(self) -> list[ExchangePosition]:
        self._require_connection()
        return list(self.positions.values())

    def place_order(self, request: ExchangeOrderRequest) -> ExchangeOrder:
        self._require_connection()
        request.validate()

        market_price = self.prices.get(request.symbol)
        if request.order_type == ExchangeOrderType.MARKET:
            if market_price is None or market_price <= 0:
                raise ExchangeOrderError(
                    f"Market fiyatı bulunamadı: {request.symbol}"
                )
            execution_price = market_price
        else:
            execution_price = float(request.price or request.stop_price or 0)

        order = ExchangeOrder(
            exchange_order_id=uuid4().hex,
            client_order_id=request.client_order_id,
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            status=ExchangeOrderStatus.NEW,
            quantity=request.quantity,
        )

        if request.side == ExchangeOrderSide.BUY:
            cost = request.quantity * execution_price
            quote = self._quote_asset(request.symbol)
            balance = self.balances.setdefault(
                quote,
                ExchangeBalance(asset=quote, free=0.0),
            )
            if balance.free < cost:
                order.status = ExchangeOrderStatus.REJECTED
                order.raw["reject_reason"] = "Yetersiz bakiye."
                self.orders[order.exchange_order_id] = order
                return order

            balance.free -= cost
            base = self._base_asset(request.symbol)
            base_balance = self.balances.setdefault(
                base,
                ExchangeBalance(asset=base, free=0.0),
            )
            base_balance.free += request.quantity
            position = self.positions.get(request.symbol)
            if position is None:
                position = ExchangePosition(
                    symbol=request.symbol,
                    quantity=0.0,
                    average_price=0.0,
                    current_price=execution_price,
                )
                self.positions[request.symbol] = position
            new_qty = position.quantity + request.quantity
            position.average_price = (
                position.average_price * position.quantity
                + execution_price * request.quantity
            ) / new_qty
            position.quantity = new_qty
            position.current_price = execution_price
        else:
            position = self.positions.get(request.symbol)
            if position is None or position.quantity < request.quantity:
                order.status = ExchangeOrderStatus.REJECTED
                order.raw["reject_reason"] = "Yetersiz pozisyon."
                self.orders[order.exchange_order_id] = order
                return order

            position.quantity -= request.quantity
            position.current_price = execution_price
            base = self._base_asset(request.symbol)
            quote = self._quote_asset(request.symbol)
            self.balances[base].free -= request.quantity
            quote_balance = self.balances.setdefault(
                quote,
                ExchangeBalance(asset=quote, free=0.0),
            )
            quote_balance.free += request.quantity * execution_price
            if position.quantity <= 1e-12:
                position.quantity = 0.0
                position.average_price = 0.0

        order.status = ExchangeOrderStatus.FILLED
        order.filled_quantity = request.quantity
        order.average_price = execution_price
        self.orders[order.exchange_order_id] = order
        return order

    def get_order(self, exchange_order_id: str) -> ExchangeOrder:
        self._require_connection()
        try:
            return self.orders[exchange_order_id]
        except KeyError as exc:
            raise ExchangeOrderError(
                f"Emir bulunamadı: {exchange_order_id}"
            ) from exc

    def cancel_order(self, exchange_order_id: str) -> ExchangeOrder:
        order = self.get_order(exchange_order_id)
        if order.status in {
            ExchangeOrderStatus.FILLED,
            ExchangeOrderStatus.REJECTED,
        }:
            raise ExchangeOrderError(
                "Tamamlanmış veya reddedilmiş emir iptal edilemez."
            )
        order.status = ExchangeOrderStatus.CANCELLED
        return order

    def update_price(self, symbol: str, price: float) -> None:
        if price <= 0:
            raise ValueError("price 0'dan büyük olmalıdır.")
        self.prices[symbol] = float(price)
        if symbol in self.positions:
            self.positions[symbol].current_price = float(price)

    def _require_connection(self) -> None:
        if not self.connected:
            raise ExchangeConnectionError("Exchange bağlantısı kapalı.")

    @staticmethod
    def _base_asset(symbol: str) -> str:
        return symbol.replace("-", "/").split("/")[0]

    @staticmethod
    def _quote_asset(symbol: str) -> str:
        parts = symbol.replace("-", "/").split("/")
        return parts[1] if len(parts) > 1 else "USDT"


class BinanceExchangeAdapter(InMemoryExchangeAdapter):
    def __init__(
        self,
        config: ExchangeConfig | None = None,
        *,
        starting_balances: dict[str, float] | None = None,
        prices: dict[str, float] | None = None,
    ) -> None:
        resolved = config or ExchangeConfig(
            mode=ExchangeMode.TESTNET,
            exchange_name="BINANCE",
        )
        if resolved.mode == ExchangeMode.LIVE and not resolved.allow_live_trading:
            raise ValueError(
                "Binance LIVE adaptörü güvenlik nedeniyle açık izin ister."
            )
        super().__init__(
            resolved,
            starting_balances=starting_balances,
            prices=prices,
        )

    @property
    def environment_name(self) -> str:
        return (
            "BINANCE_TESTNET"
            if self.config.mode == ExchangeMode.TESTNET
            else "BINANCE_LIVE"
        )


class ExchangeRouter:
    def __init__(self) -> None:
        self.adapters: dict[str, ExchangeAdapter] = {}
        self.active_name: str | None = None

    def register(
        self,
        name: str,
        adapter: ExchangeAdapter,
        *,
        make_active: bool = False,
    ) -> None:
        normalized = name.strip().upper()
        if not normalized:
            raise ValueError("Adapter adı boş olamaz.")
        self.adapters[normalized] = adapter
        if make_active or self.active_name is None:
            self.active_name = normalized

    def set_active(self, name: str) -> ExchangeAdapter:
        normalized = name.strip().upper()
        if normalized not in self.adapters:
            raise KeyError(f"Exchange adaptörü bulunamadı: {name}")
        self.active_name = normalized
        return self.adapters[normalized]

    def active(self) -> ExchangeAdapter:
        if self.active_name is None:
            raise ExchangeError("Aktif exchange adaptörü seçilmedi.")
        return self.adapters[self.active_name]

    def report(self) -> dict[str, Any]:
        return {
            "active": self.active_name,
            "adapters": {
                name: adapter.health_report()
                for name, adapter in self.adapters.items()
            },
        }
