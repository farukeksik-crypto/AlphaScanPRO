from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Protocol
import time


class SyncState(str, Enum):
    IDLE = "IDLE"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    DISCONNECTED = "DISCONNECTED"
    ERROR = "ERROR"


class SyncEventType(str, Enum):
    ACCOUNT = "ACCOUNT"
    OPEN_ORDERS = "OPEN_ORDERS"
    TRADES = "TRADES"
    ORDER_UPDATE = "ORDER_UPDATE"
    HEARTBEAT = "HEARTBEAT"
    ERROR = "ERROR"


class BinanceSyncClientProtocol(Protocol):
    def get_account(self, **kwargs: Any) -> dict[str, Any]:
        ...

    def get_open_orders(self, **kwargs: Any) -> list[dict[str, Any]]:
        ...

    def get_my_trades(self, **kwargs: Any) -> list[dict[str, Any]]:
        ...

    def ping(self) -> Any:
        ...

    def get_server_time(self) -> dict[str, Any]:
        ...


@dataclass
class BinanceTestnetSyncConfig:
    enabled: bool = False
    poll_interval_seconds: float = 5.0
    heartbeat_interval_seconds: float = 30.0
    reconnect_delay_seconds: float = 5.0
    max_reconnect_attempts: int = 5
    recv_window: int = 5000
    trade_limit: int = 100
    stale_after_seconds: float = 60.0
    max_events: int = 5000
    sync_account: bool = True
    sync_open_orders: bool = True
    sync_trades: bool = True

    def validate(self) -> None:
        if self.poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds pozitif olmalıdır.")
        if self.heartbeat_interval_seconds <= 0:
            raise ValueError("heartbeat_interval_seconds pozitif olmalıdır.")
        if self.reconnect_delay_seconds < 0:
            raise ValueError("reconnect_delay_seconds negatif olamaz.")
        if self.max_reconnect_attempts <= 0:
            raise ValueError("max_reconnect_attempts pozitif olmalıdır.")
        if self.recv_window <= 0:
            raise ValueError("recv_window pozitif olmalıdır.")
        if self.trade_limit <= 0:
            raise ValueError("trade_limit pozitif olmalıdır.")
        if self.stale_after_seconds <= 0:
            raise ValueError("stale_after_seconds pozitif olmalıdır.")
        if self.max_events <= 0:
            raise ValueError("max_events pozitif olmalıdır.")


@dataclass
class BalanceSnapshot:
    asset: str
    free: float
    locked: float

    @property
    def total(self) -> float:
        return self.free + self.locked

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["total"] = self.total
        return data


@dataclass
class OpenOrderSnapshot:
    symbol: str
    order_id: str
    client_order_id: str | None
    side: str
    order_type: str
    status: str
    price: float
    original_quantity: float
    executed_quantity: float
    update_time: int | None = None

    @property
    def remaining_quantity(self) -> float:
        return max(self.original_quantity - self.executed_quantity, 0.0)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["remaining_quantity"] = self.remaining_quantity
        return data


@dataclass
class TradeSnapshot:
    symbol: str
    trade_id: str
    order_id: str
    price: float
    quantity: float
    quote_quantity: float
    commission: float
    commission_asset: str | None
    is_buyer: bool
    timestamp: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SyncEvent:
    event_type: SyncEventType
    timestamp: float
    success: bool
    message: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["event_type"] = self.event_type.value
        return data


class BinanceTestnetSyncManager:
    def __init__(
        self,
        *,
        client: BinanceSyncClientProtocol,
        config: BinanceTestnetSyncConfig | None = None,
        time_fn: Callable[[], float] = time.time,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client = client
        self.config = config or BinanceTestnetSyncConfig()
        self.config.validate()
        self.time_fn = time_fn
        self.sleep_fn = sleep_fn

        self.state = SyncState.IDLE
        self.last_error: str | None = None
        self.last_sync_at: float | None = None
        self.last_heartbeat_at: float | None = None
        self.reconnect_attempts = 0

        self.balances: dict[str, BalanceSnapshot] = {}
        self.open_orders: dict[str, OpenOrderSnapshot] = {}
        self.trades: dict[str, TradeSnapshot] = {}
        self.events: list[SyncEvent] = []
        self._callbacks: list[Callable[[SyncEvent], None]] = []

    def enable(self) -> None:
        self.config.enabled = True

    def disable(self) -> None:
        self.config.enabled = False
        self.state = SyncState.DISCONNECTED

    def connect(self) -> bool:
        if not self.config.enabled:
            self.state = SyncState.DISCONNECTED
            self._emit(
                SyncEventType.ERROR,
                False,
                "Senkronizasyon etkin değil.",
            )
            return False

        self.state = SyncState.CONNECTING
        try:
            self.client.ping()
            self.client.get_server_time()
            self.state = SyncState.CONNECTED
            self.last_error = None
            self.reconnect_attempts = 0
            self.last_heartbeat_at = self.time_fn()
            self._emit(
                SyncEventType.HEARTBEAT,
                True,
                "Binance Testnet bağlantısı kuruldu.",
            )
            return True
        except Exception as exc:
            self.state = SyncState.ERROR
            self.last_error = str(exc)
            self._emit(
                SyncEventType.ERROR,
                False,
                f"Bağlantı hatası: {exc}",
            )
            return False

    def reconnect(self) -> bool:
        if not self.config.enabled:
            return False

        while self.reconnect_attempts < self.config.max_reconnect_attempts:
            self.reconnect_attempts += 1
            if self.config.reconnect_delay_seconds > 0:
                self.sleep_fn(self.config.reconnect_delay_seconds)
            if self.connect():
                return True

        self.state = SyncState.ERROR
        self._emit(
            SyncEventType.ERROR,
            False,
            "Maksimum yeniden bağlanma denemesi aşıldı.",
            {"attempts": self.reconnect_attempts},
        )
        return False

    def heartbeat(self, *, force: bool = False) -> bool:
        now = self.time_fn()
        if (
            not force
            and self.last_heartbeat_at is not None
            and now - self.last_heartbeat_at < self.config.heartbeat_interval_seconds
        ):
            return True

        try:
            self.client.ping()
            server_time = self.client.get_server_time()
            self.last_heartbeat_at = now
            self.state = SyncState.CONNECTED
            self.last_error = None
            self._emit(
                SyncEventType.HEARTBEAT,
                True,
                "Heartbeat başarılı.",
                {"server_time": server_time.get("serverTime")},
            )
            return True
        except Exception as exc:
            self.state = SyncState.DEGRADED
            self.last_error = str(exc)
            self._emit(
                SyncEventType.ERROR,
                False,
                f"Heartbeat hatası: {exc}",
            )
            return False

    def sync_all(self, symbol: str | None = None) -> dict[str, Any]:
        if not self.config.enabled:
            raise RuntimeError("Senkronizasyon etkin değil.")

        if self.state not in {SyncState.CONNECTED, SyncState.DEGRADED}:
            if not self.connect():
                raise ConnectionError(self.last_error or "Bağlantı kurulamadı.")

        result: dict[str, Any] = {}
        failures = 0

        if self.config.sync_account:
            try:
                result["balances"] = self.sync_account()
            except Exception as exc:
                failures += 1
                result["balances_error"] = str(exc)

        if self.config.sync_open_orders:
            try:
                result["open_orders"] = self.sync_open_orders(symbol=symbol)
            except Exception as exc:
                failures += 1
                result["open_orders_error"] = str(exc)

        if self.config.sync_trades and symbol:
            try:
                result["trades"] = self.sync_trades(symbol=symbol)
            except Exception as exc:
                failures += 1
                result["trades_error"] = str(exc)

        self.last_sync_at = self.time_fn()
        if failures == 0:
            self.state = SyncState.CONNECTED
        elif failures >= 2:
            self.state = SyncState.ERROR
        else:
            self.state = SyncState.DEGRADED

        result["state"] = self.state.value
        result["failures"] = failures
        return result

    def sync_account(self) -> list[dict[str, Any]]:
        response = self.client.get_account(recvWindow=self.config.recv_window)
        new_balances: dict[str, BalanceSnapshot] = {}

        for item in response.get("balances", []):
            asset = str(item.get("asset", "")).upper()
            if not asset:
                continue
            snapshot = BalanceSnapshot(
                asset=asset,
                free=float(item.get("free", 0) or 0),
                locked=float(item.get("locked", 0) or 0),
            )
            if snapshot.total > 0:
                new_balances[asset] = snapshot

        self.balances = new_balances
        payload = {"count": len(new_balances)}
        self._emit(
            SyncEventType.ACCOUNT,
            True,
            "Hesap bakiyeleri senkronize edildi.",
            payload,
        )
        return [item.to_dict() for item in new_balances.values()]

    def sync_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"recvWindow": self.config.recv_window}
        if symbol:
            params["symbol"] = self.normalize_symbol(symbol)

        response = self.client.get_open_orders(**params)
        new_orders: dict[str, OpenOrderSnapshot] = {}

        for item in response:
            snapshot = OpenOrderSnapshot(
                symbol=self.normalize_symbol(str(item.get("symbol", ""))),
                order_id=str(item.get("orderId")),
                client_order_id=(
                    str(item.get("clientOrderId"))
                    if item.get("clientOrderId") is not None
                    else None
                ),
                side=str(item.get("side", "")).upper(),
                order_type=str(item.get("type", "")).upper(),
                status=str(item.get("status", "UNKNOWN")).upper(),
                price=float(item.get("price", 0) or 0),
                original_quantity=float(item.get("origQty", 0) or 0),
                executed_quantity=float(item.get("executedQty", 0) or 0),
                update_time=(
                    int(item.get("updateTime"))
                    if item.get("updateTime") is not None
                    else None
                ),
            )
            key = self.order_key(snapshot.symbol, snapshot.order_id)
            new_orders[key] = snapshot

        self.open_orders = new_orders
        self._emit(
            SyncEventType.OPEN_ORDERS,
            True,
            "Açık emirler senkronize edildi.",
            {"count": len(new_orders)},
        )
        return [item.to_dict() for item in new_orders.values()]

    def sync_trades(self, *, symbol: str) -> list[dict[str, Any]]:
        normalized_symbol = self.normalize_symbol(symbol)
        response = self.client.get_my_trades(
            symbol=normalized_symbol,
            limit=self.config.trade_limit,
            recvWindow=self.config.recv_window,
        )

        added = 0
        for item in response:
            snapshot = TradeSnapshot(
                symbol=normalized_symbol,
                trade_id=str(item.get("id")),
                order_id=str(item.get("orderId")),
                price=float(item.get("price", 0) or 0),
                quantity=float(item.get("qty", 0) or 0),
                quote_quantity=float(item.get("quoteQty", 0) or 0),
                commission=float(item.get("commission", 0) or 0),
                commission_asset=(
                    str(item.get("commissionAsset"))
                    if item.get("commissionAsset") is not None
                    else None
                ),
                is_buyer=bool(item.get("isBuyer", False)),
                timestamp=(
                    int(item.get("time"))
                    if item.get("time") is not None
                    else None
                ),
            )
            key = self.trade_key(snapshot.symbol, snapshot.trade_id)
            if key not in self.trades:
                added += 1
            self.trades[key] = snapshot

        self._emit(
            SyncEventType.TRADES,
            True,
            "İşlem geçmişi senkronize edildi.",
            {"symbol": normalized_symbol, "count": len(response), "added": added},
        )
        return [
            item.to_dict()
            for key, item in self.trades.items()
            if key.startswith(f"{normalized_symbol}:")
        ]

    def apply_order_update(self, payload: dict[str, Any]) -> dict[str, Any]:
        symbol = self.normalize_symbol(str(payload.get("symbol", "")))
        order_id = str(payload.get("orderId"))
        key = self.order_key(symbol, order_id)
        status = str(payload.get("status", "UNKNOWN")).upper()

        snapshot = OpenOrderSnapshot(
            symbol=symbol,
            order_id=order_id,
            client_order_id=(
                str(payload.get("clientOrderId"))
                if payload.get("clientOrderId") is not None
                else None
            ),
            side=str(payload.get("side", "")).upper(),
            order_type=str(payload.get("type", "")).upper(),
            status=status,
            price=float(payload.get("price", 0) or 0),
            original_quantity=float(payload.get("origQty", 0) or 0),
            executed_quantity=float(payload.get("executedQty", 0) or 0),
            update_time=(
                int(payload.get("updateTime"))
                if payload.get("updateTime") is not None
                else None
            ),
        )

        if status in {"FILLED", "CANCELED", "REJECTED", "EXPIRED"}:
            self.open_orders.pop(key, None)
        else:
            self.open_orders[key] = snapshot

        self._emit(
            SyncEventType.ORDER_UPDATE,
            True,
            f"Emir güncellemesi işlendi: {status}",
            snapshot.to_dict(),
        )
        return snapshot.to_dict()

    def register_callback(self, callback: Callable[[SyncEvent], None]) -> None:
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def unregister_callback(self, callback: Callable[[SyncEvent], None]) -> None:
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def is_stale(self) -> bool:
        if self.last_sync_at is None:
            return True
        return self.time_fn() - self.last_sync_at > self.config.stale_after_seconds

    def health_report(self) -> dict[str, Any]:
        return {
            "enabled": self.config.enabled,
            "state": self.state.value,
            "last_error": self.last_error,
            "last_sync_at": self.last_sync_at,
            "last_heartbeat_at": self.last_heartbeat_at,
            "reconnect_attempts": self.reconnect_attempts,
            "balance_count": len(self.balances),
            "open_order_count": len(self.open_orders),
            "trade_count": len(self.trades),
            "event_count": len(self.events),
            "stale": self.is_stale(),
        }

    def dashboard_payload(self) -> dict[str, Any]:
        return {
            "health": self.health_report(),
            "balances": [item.to_dict() for item in self.balances.values()],
            "open_orders": [item.to_dict() for item in self.open_orders.values()],
            "recent_trades": [
                item.to_dict() for item in list(self.trades.values())[-50:]
            ],
            "recent_events": [
                item.to_dict() for item in self.events[-50:]
            ],
        }

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        return symbol.replace("/", "").replace("-", "").upper()

    @staticmethod
    def order_key(symbol: str, order_id: str) -> str:
        return f"{symbol}:{order_id}"

    @staticmethod
    def trade_key(symbol: str, trade_id: str) -> str:
        return f"{symbol}:{trade_id}"

    def _emit(
        self,
        event_type: SyncEventType,
        success: bool,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> SyncEvent:
        event = SyncEvent(
            event_type=event_type,
            timestamp=self.time_fn(),
            success=success,
            message=message,
            payload=payload or {},
        )
        self.events.append(event)
        if len(self.events) > self.config.max_events:
            del self.events[: len(self.events) - self.config.max_events]

        for callback in tuple(self._callbacks):
            try:
                callback(event)
            except Exception:
                continue
        return event
