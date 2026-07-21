from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable
import json
import time


BINANCE_SPOT_TESTNET_WS_BASE = "wss://stream.testnet.binance.vision"
BINANCE_SPOT_LIVE_WS_BASE = "wss://stream.binance.com:9443"


class MarketDataEventType(str, Enum):
    TRADE = "TRADE"
    TICKER = "TICKER"
    KLINE = "KLINE"
    DEPTH = "DEPTH"
    HEARTBEAT = "HEARTBEAT"
    UNKNOWN = "UNKNOWN"


@dataclass
class MarketDataConfig:
    testnet: bool = True
    reconnect_attempts: int = 5
    reconnect_delay_seconds: float = 0.0
    heartbeat_timeout_seconds: float = 60.0
    max_events: int = 10_000

    def validate(self) -> None:
        if self.reconnect_attempts < 0:
            raise ValueError("reconnect_attempts negatif olamaz.")
        if self.reconnect_delay_seconds < 0:
            raise ValueError("reconnect_delay_seconds negatif olamaz.")
        if self.heartbeat_timeout_seconds <= 0:
            raise ValueError("heartbeat_timeout_seconds 0'dan büyük olmalıdır.")
        if self.max_events <= 0:
            raise ValueError("max_events 0'dan büyük olmalıdır.")


@dataclass
class StreamSubscription:
    symbol: str
    stream: str
    interval: str | None = None

    def stream_name(self) -> str:
        symbol = self.symbol.replace("/", "").replace("-", "").lower()
        stream = self.stream.strip().lower()
        if stream == "kline":
            if not self.interval:
                raise ValueError("Kline stream için interval gereklidir.")
            return f"{symbol}@kline_{self.interval}"
        return f"{symbol}@{stream}"


@dataclass
class TradeTick:
    symbol: str
    price: float
    quantity: float
    trade_time: int
    is_buyer_maker: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class KlineUpdate:
    symbol: str
    interval: str
    open_time: int
    close_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_count: int
    closed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TickerUpdate:
    symbol: str
    event_time: int
    price_change_pct: float
    last_price: float
    open_price: float
    high_price: float
    low_price: float
    volume: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DepthUpdate:
    symbol: str
    event_time: int
    first_update_id: int
    final_update_id: int
    bids: list[tuple[float, float]]
    asks: list[tuple[float, float]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MarketDataEvent:
    event_type: MarketDataEventType
    symbol: str
    payload: Any
    raw: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = (
            self.payload.to_dict()
            if hasattr(self.payload, "to_dict")
            else self.payload
        )
        return {
            "event_type": self.event_type.value,
            "symbol": self.symbol,
            "payload": payload,
            "raw": dict(self.raw),
        }


class BinanceMarketDataParser:
    def parse(self, message: str | bytes | dict[str, Any]) -> MarketDataEvent:
        if isinstance(message, bytes):
            data = json.loads(message.decode("utf-8"))
        elif isinstance(message, str):
            data = json.loads(message)
        else:
            data = dict(message)

        raw = dict(data)
        if "stream" in data and "data" in data:
            data = dict(data["data"])

        event_name = str(data.get("e", "")).lower()
        symbol = str(data.get("s", "")).upper()

        if event_name in {"trade", "aggtrade"}:
            payload = TradeTick(
                symbol=symbol,
                price=float(data["p"]),
                quantity=float(data["q"]),
                trade_time=int(data.get("T", data.get("E", 0))),
                is_buyer_maker=bool(data.get("m", False)),
            )
            return MarketDataEvent(
                MarketDataEventType.TRADE,
                symbol,
                payload,
                raw,
            )

        if event_name == "kline":
            kline = data["k"]
            payload = KlineUpdate(
                symbol=symbol,
                interval=str(kline["i"]),
                open_time=int(kline["t"]),
                close_time=int(kline["T"]),
                open=float(kline["o"]),
                high=float(kline["h"]),
                low=float(kline["l"]),
                close=float(kline["c"]),
                volume=float(kline["v"]),
                trade_count=int(kline["n"]),
                closed=bool(kline["x"]),
            )
            return MarketDataEvent(
                MarketDataEventType.KLINE,
                symbol,
                payload,
                raw,
            )

        if event_name in {"24hrticker", "24hrminiticker"}:
            payload = TickerUpdate(
                symbol=symbol,
                event_time=int(data.get("E", 0)),
                price_change_pct=float(data.get("P", 0.0)),
                last_price=float(data.get("c", 0.0)),
                open_price=float(data.get("o", 0.0)),
                high_price=float(data.get("h", 0.0)),
                low_price=float(data.get("l", 0.0)),
                volume=float(data.get("v", 0.0)),
            )
            return MarketDataEvent(
                MarketDataEventType.TICKER,
                symbol,
                payload,
                raw,
            )

        if event_name == "depthupdate":
            payload = DepthUpdate(
                symbol=symbol,
                event_time=int(data.get("E", 0)),
                first_update_id=int(data.get("U", 0)),
                final_update_id=int(data.get("u", 0)),
                bids=[(float(p), float(q)) for p, q in data.get("b", [])],
                asks=[(float(p), float(q)) for p, q in data.get("a", [])],
            )
            return MarketDataEvent(
                MarketDataEventType.DEPTH,
                symbol,
                payload,
                raw,
            )

        if data.get("type") == "heartbeat":
            return MarketDataEvent(
                MarketDataEventType.HEARTBEAT,
                symbol,
                data,
                raw,
            )

        return MarketDataEvent(
            MarketDataEventType.UNKNOWN,
            symbol,
            data,
            raw,
        )


class MarketDataState:
    def __init__(self, max_events: int = 10_000) -> None:
        self.max_events = max_events
        self.last_prices: dict[str, float] = {}
        self.klines: dict[str, KlineUpdate] = {}
        self.tickers: dict[str, TickerUpdate] = {}
        self.depth: dict[str, DepthUpdate] = {}
        self.events: list[MarketDataEvent] = []

    def apply(self, event: MarketDataEvent) -> None:
        if event.event_type == MarketDataEventType.TRADE:
            self.last_prices[event.symbol] = event.payload.price
        elif event.event_type == MarketDataEventType.KLINE:
            key = f"{event.symbol}:{event.payload.interval}"
            self.klines[key] = event.payload
            self.last_prices[event.symbol] = event.payload.close
        elif event.event_type == MarketDataEventType.TICKER:
            self.tickers[event.symbol] = event.payload
            self.last_prices[event.symbol] = event.payload.last_price
        elif event.event_type == MarketDataEventType.DEPTH:
            self.depth[event.symbol] = event.payload

        self.events.append(event)
        if len(self.events) > self.max_events:
            del self.events[: len(self.events) - self.max_events]

    def snapshot(self) -> dict[str, Any]:
        return {
            "last_prices": dict(self.last_prices),
            "klines": {
                key: value.to_dict()
                for key, value in self.klines.items()
            },
            "tickers": {
                key: value.to_dict()
                for key, value in self.tickers.items()
            },
            "depth": {
                key: value.to_dict()
                for key, value in self.depth.items()
            },
            "event_count": len(self.events),
        }


class MarketDataTransport:
    def connect(self, url: str) -> None:
        raise NotImplementedError

    def receive(self) -> str | bytes | dict[str, Any] | None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def pong(self, payload: bytes = b"") -> None:
        return None


class BinanceLiveMarketDataEngine:
    def __init__(
        self,
        *,
        config: MarketDataConfig | None = None,
        transport: MarketDataTransport,
        parser: BinanceMarketDataParser | None = None,
        time_fn: Callable[[], float] = time.time,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config or MarketDataConfig()
        self.config.validate()
        self.transport = transport
        self.parser = parser or BinanceMarketDataParser()
        self.time_fn = time_fn
        self.sleep_fn = sleep_fn
        self.state = MarketDataState(self.config.max_events)
        self.subscriptions: list[StreamSubscription] = []
        self.connected = False
        self.last_message_at: float | None = None
        self.connection_count = 0
        self.reconnect_count = 0
        self.callbacks: list[Callable[[MarketDataEvent], None]] = []

    @property
    def base_url(self) -> str:
        return (
            BINANCE_SPOT_TESTNET_WS_BASE
            if self.config.testnet
            else BINANCE_SPOT_LIVE_WS_BASE
        )

    def subscribe(self, subscription: StreamSubscription) -> None:
        name = subscription.stream_name()
        if name not in {item.stream_name() for item in self.subscriptions}:
            self.subscriptions.append(subscription)

    def subscribe_many(
        self,
        subscriptions: Iterable[StreamSubscription],
    ) -> None:
        for subscription in subscriptions:
            self.subscribe(subscription)

    def add_callback(
        self,
        callback: Callable[[MarketDataEvent], None],
    ) -> None:
        self.callbacks.append(callback)

    def stream_url(self) -> str:
        if not self.subscriptions:
            raise ValueError("En az bir market data aboneliği gereklidir.")
        names = "/".join(item.stream_name() for item in self.subscriptions)
        if len(self.subscriptions) == 1:
            return f"{self.base_url}/ws/{names}"
        return f"{self.base_url}/stream?streams={names}"

    def connect(self) -> None:
        self.transport.connect(self.stream_url())
        self.connected = True
        self.connection_count += 1
        self.last_message_at = self.time_fn()

    def disconnect(self) -> None:
        self.transport.close()
        self.connected = False

    def process_message(
        self,
        message: str | bytes | dict[str, Any],
    ) -> MarketDataEvent:
        event = self.parser.parse(message)
        self.state.apply(event)
        self.last_message_at = self.time_fn()
        for callback in list(self.callbacks):
            callback(event)
        return event

    def run_once(self) -> MarketDataEvent | None:
        if not self.connected:
            self.connect()
        message = self.transport.receive()
        if message is None:
            return None
        return self.process_message(message)

    def run(self, *, max_messages: int | None = None) -> int:
        processed = 0
        while max_messages is None or processed < max_messages:
            try:
                event = self.run_once()
                if event is not None:
                    processed += 1
            except (ConnectionError, OSError, TimeoutError):
                self._reconnect()
        return processed

    def heartbeat_ok(self) -> bool:
        if self.last_message_at is None:
            return False
        return (
            self.time_fn() - self.last_message_at
            <= self.config.heartbeat_timeout_seconds
        )

    def health_report(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "testnet": self.config.testnet,
            "subscription_count": len(self.subscriptions),
            "connection_count": self.connection_count,
            "reconnect_count": self.reconnect_count,
            "heartbeat_ok": self.heartbeat_ok(),
            "last_message_at": self.last_message_at,
            "event_count": len(self.state.events),
        }

    def _reconnect(self) -> None:
        self.connected = False
        try:
            self.transport.close()
        except Exception:
            pass

        last_error: BaseException | None = None
        for attempt in range(self.config.reconnect_attempts + 1):
            try:
                if attempt > 0 and self.config.reconnect_delay_seconds > 0:
                    self.sleep_fn(self.config.reconnect_delay_seconds)
                self.transport.connect(self.stream_url())
                self.connected = True
                self.connection_count += 1
                self.reconnect_count += 1
                self.last_message_at = self.time_fn()
                return
            except (ConnectionError, OSError, TimeoutError) as exc:
                last_error = exc

        raise ConnectionError(
            "Market data yeniden bağlantısı başarısız."
        ) from last_error
