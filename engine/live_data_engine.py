from __future__ import annotations

import asyncio
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, Iterable, List, Optional, Protocol


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ConnectionState(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    STOPPED = "STOPPED"


@dataclass(slots=True)
class MarketTick:
    symbol: str
    price: float
    quantity: float
    timestamp: datetime
    source: str = "UNKNOWN"

    def __post_init__(self) -> None:
        self.symbol = self.symbol.strip().upper()
        if not self.symbol:
            raise ValueError("symbol boş olamaz.")
        if self.price <= 0 or not math.isfinite(self.price):
            raise ValueError("price pozitif ve sonlu olmalıdır.")
        if self.quantity < 0 or not math.isfinite(self.quantity):
            raise ValueError("quantity negatif olamaz.")
        if self.timestamp.tzinfo is None:
            self.timestamp = self.timestamp.replace(tzinfo=timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "price": self.price,
            "quantity": self.quantity,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
        }


@dataclass(slots=True)
class OhlcBar:
    symbol: str
    interval_seconds: int
    open_time: datetime
    close_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    tick_count: int
    is_closed: bool = False

    def update(self, tick: MarketTick) -> None:
        self.high = max(self.high, tick.price)
        self.low = min(self.low, tick.price)
        self.close = tick.price
        self.volume += tick.quantity
        self.tick_count += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "interval_seconds": self.interval_seconds,
            "open_time": self.open_time.isoformat(),
            "close_time": self.close_time.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "tick_count": self.tick_count,
            "is_closed": self.is_closed,
        }


@dataclass(slots=True)
class ReconnectPolicy:
    initial_delay: float = 1.0
    max_delay: float = 30.0
    multiplier: float = 2.0
    max_attempts: Optional[int] = None

    def __post_init__(self) -> None:
        if self.initial_delay < 0:
            raise ValueError("initial_delay negatif olamaz.")
        if self.max_delay < self.initial_delay:
            raise ValueError("max_delay initial_delay değerinden küçük olamaz.")
        if self.multiplier < 1:
            raise ValueError("multiplier en az 1 olmalıdır.")
        if self.max_attempts is not None and self.max_attempts < 1:
            raise ValueError("max_attempts en az 1 olmalıdır.")

    def delay_for_attempt(self, attempt: int) -> float:
        if attempt < 1:
            raise ValueError("attempt en az 1 olmalıdır.")
        return min(
            self.initial_delay * (self.multiplier ** (attempt - 1)),
            self.max_delay,
        )


@dataclass(slots=True)
class LiveDataHealth:
    state: ConnectionState = ConnectionState.DISCONNECTED
    connected_at: Optional[datetime] = None
    disconnected_at: Optional[datetime] = None
    last_message_at: Optional[datetime] = None
    last_tick_at: Optional[datetime] = None
    reconnect_attempts: int = 0
    received_messages: int = 0
    received_ticks: int = 0
    parse_errors: int = 0
    connection_errors: int = 0
    last_error: str = ""

    def is_stale(self, *, now: Optional[datetime] = None, stale_after: float = 30.0) -> bool:
        reference = self.last_tick_at or self.last_message_at
        if reference is None:
            return True
        current = now or utc_now()
        return (current - reference).total_seconds() > stale_after

    def to_dict(self, *, stale_after: float = 30.0) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "connected_at": self.connected_at.isoformat() if self.connected_at else None,
            "disconnected_at": self.disconnected_at.isoformat() if self.disconnected_at else None,
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
            "last_tick_at": self.last_tick_at.isoformat() if self.last_tick_at else None,
            "reconnect_attempts": self.reconnect_attempts,
            "received_messages": self.received_messages,
            "received_ticks": self.received_ticks,
            "parse_errors": self.parse_errors,
            "connection_errors": self.connection_errors,
            "last_error": self.last_error,
            "stale": self.is_stale(stale_after=stale_after),
        }


class AsyncMarketTransport(Protocol):
    async def connect(self, symbols: List[str]) -> None:
        ...

    async def messages(self) -> AsyncIterator[str | Dict[str, Any]]:
        ...

    async def close(self) -> None:
        ...


class BinanceTradeParser:
    @staticmethod
    def parse(payload: str | Dict[str, Any]) -> MarketTick:
        data = json.loads(payload) if isinstance(payload, str) else dict(payload)
        if "data" in data and isinstance(data["data"], dict):
            data = data["data"]

        symbol = data.get("s") or data.get("symbol")
        price = data.get("p") or data.get("price")
        quantity = data.get("q") or data.get("quantity") or 0
        event_time = data.get("T") or data.get("E") or data.get("timestamp")

        if symbol is None or price is None:
            raise ValueError("Binance mesajında symbol veya price eksik.")

        if event_time is None:
            timestamp = utc_now()
        elif isinstance(event_time, (int, float)):
            timestamp = datetime.fromtimestamp(float(event_time) / 1000.0, tz=timezone.utc)
        elif isinstance(event_time, str):
            timestamp = datetime.fromisoformat(event_time)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
        else:
            raise ValueError("Desteklenmeyen timestamp biçimi.")

        return MarketTick(
            symbol=str(symbol),
            price=float(price),
            quantity=float(quantity),
            timestamp=timestamp,
            source="BINANCE",
        )


class OhlcAggregator:
    def __init__(self, interval_seconds: int = 60) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds pozitif olmalıdır.")
        self.interval_seconds = int(interval_seconds)
        self._active: Dict[str, OhlcBar] = {}
        self._closed: List[OhlcBar] = []

    def _bucket_start(self, timestamp: datetime) -> datetime:
        epoch = int(timestamp.timestamp())
        bucket = epoch - (epoch % self.interval_seconds)
        return datetime.fromtimestamp(bucket, tz=timezone.utc)

    def add_tick(self, tick: MarketTick) -> List[OhlcBar]:
        symbol = tick.symbol
        bucket_start = self._bucket_start(tick.timestamp)
        bucket_end = bucket_start + timedelta(seconds=self.interval_seconds)
        current = self._active.get(symbol)
        closed_now: List[OhlcBar] = []

        if current is None or current.open_time != bucket_start:
            if current is not None:
                current.is_closed = True
                self._closed.append(current)
                closed_now.append(current)

            current = OhlcBar(
                symbol=symbol,
                interval_seconds=self.interval_seconds,
                open_time=bucket_start,
                close_time=bucket_end,
                open=tick.price,
                high=tick.price,
                low=tick.price,
                close=tick.price,
                volume=tick.quantity,
                tick_count=1,
                is_closed=False,
            )
            self._active[symbol] = current
        else:
            current.update(tick)

        return closed_now

    def current_bar(self, symbol: str) -> Optional[OhlcBar]:
        return self._active.get(symbol.strip().upper())

    def closed_bars(self, symbol: Optional[str] = None) -> List[OhlcBar]:
        if symbol is None:
            return list(self._closed)
        normalized = symbol.strip().upper()
        return [bar for bar in self._closed if bar.symbol == normalized]

    def flush(self) -> List[OhlcBar]:
        output: List[OhlcBar] = []
        for symbol, bar in list(self._active.items()):
            bar.is_closed = True
            self._closed.append(bar)
            output.append(bar)
            self._active.pop(symbol, None)
        return output

    def snapshot(self) -> Dict[str, Any]:
        return {
            "interval_seconds": self.interval_seconds,
            "active": {
                symbol: bar.to_dict()
                for symbol, bar in sorted(self._active.items())
            },
            "closed_count": len(self._closed),
        }


class InMemoryMarketTransport:
    def __init__(
        self,
        messages: Iterable[str | Dict[str, Any]],
        *,
        connect_error: Optional[Exception] = None,
    ) -> None:
        self._messages = list(messages)
        self.connect_error = connect_error
        self.connected = False
        self.closed = False
        self.symbols: List[str] = []

    async def connect(self, symbols: List[str]) -> None:
        if self.connect_error is not None:
            raise self.connect_error
        self.symbols = list(symbols)
        self.connected = True
        self.closed = False

    async def messages(self) -> AsyncIterator[str | Dict[str, Any]]:
        for message in self._messages:
            yield message

    async def close(self) -> None:
        self.closed = True
        self.connected = False


class BinanceWebSocketTransport:
    def __init__(self, base_url: str = "wss://stream.binance.com:9443/stream") -> None:
        self.base_url = base_url
        self._connection: Any = None

    async def connect(self, symbols: List[str]) -> None:
        try:
            import websockets
        except ImportError as exc:
            raise RuntimeError(
                "Binance WebSocket için 'websockets' paketi gerekli. "
                "Kurulum: py -3.13 -m pip install websockets"
            ) from exc

        streams = "/".join(f"{symbol.lower()}@trade" for symbol in symbols)
        url = f"{self.base_url}?streams={streams}"
        self._connection = await websockets.connect(
            url,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=10,
        )

    async def messages(self) -> AsyncIterator[str]:
        if self._connection is None:
            raise RuntimeError("WebSocket bağlantısı kurulmadı.")
        async for message in self._connection:
            yield message

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None


TickHandler = Callable[[MarketTick], Optional[Awaitable[None]]]
BarHandler = Callable[[OhlcBar], Optional[Awaitable[None]]]


class LiveDataEngine:
    def __init__(
        self,
        *,
        symbols: Iterable[str],
        transport: AsyncMarketTransport,
        interval_seconds: int = 60,
        reconnect_policy: Optional[ReconnectPolicy] = None,
        stale_after: float = 30.0,
    ) -> None:
        normalized = sorted({symbol.strip().upper() for symbol in symbols if symbol.strip()})
        if not normalized:
            raise ValueError("En az bir sembol gereklidir.")
        if stale_after <= 0:
            raise ValueError("stale_after pozitif olmalıdır.")

        self.symbols = normalized
        self.transport = transport
        self.aggregator = OhlcAggregator(interval_seconds)
        self.reconnect_policy = reconnect_policy or ReconnectPolicy()
        self.stale_after = float(stale_after)
        self.health = LiveDataHealth()
        self.latest_ticks: Dict[str, MarketTick] = {}
        self._tick_handlers: List[TickHandler] = []
        self._bar_handlers: List[BarHandler] = []
        self._running = False
        self._stop_event = asyncio.Event()

    def add_tick_handler(self, handler: TickHandler) -> None:
        self._tick_handlers.append(handler)

    def add_bar_handler(self, handler: BarHandler) -> None:
        self._bar_handlers.append(handler)

    async def _call_handler(self, handler: Callable[[Any], Any], item: Any) -> None:
        result = handler(item)
        if result is not None and hasattr(result, "__await__"):
            await result

    async def _dispatch_tick(self, tick: MarketTick) -> None:
        for handler in list(self._tick_handlers):
            await self._call_handler(handler, tick)

    async def _dispatch_bar(self, bar: OhlcBar) -> None:
        for handler in list(self._bar_handlers):
            await self._call_handler(handler, bar)

    async def process_message(self, payload: str | Dict[str, Any]) -> Optional[MarketTick]:
        self.health.received_messages += 1
        self.health.last_message_at = utc_now()
        try:
            tick = BinanceTradeParser.parse(payload)
        except Exception as exc:
            self.health.parse_errors += 1
            self.health.last_error = str(exc)
            return None

        if tick.symbol not in self.symbols:
            return None

        self.latest_ticks[tick.symbol] = tick
        self.health.received_ticks += 1
        self.health.last_tick_at = tick.timestamp
        closed = self.aggregator.add_tick(tick)

        await self._dispatch_tick(tick)
        for bar in closed:
            await self._dispatch_bar(bar)
        return tick

    async def run_once(self) -> None:
        self.health.state = ConnectionState.CONNECTING
        await self.transport.connect(self.symbols)
        self.health.state = ConnectionState.CONNECTED
        self.health.connected_at = utc_now()
        self.health.last_error = ""

        try:
            async for payload in self.transport.messages():
                if self._stop_event.is_set():
                    break
                await self.process_message(payload)
        finally:
            await self.transport.close()
            self.health.disconnected_at = utc_now()
            if self.health.state != ConnectionState.STOPPED:
                self.health.state = ConnectionState.DISCONNECTED

    async def run_forever(self) -> None:
        self._running = True
        self._stop_event.clear()
        attempt = 0

        try:
            while not self._stop_event.is_set():
                try:
                    await self.run_once()
                    attempt = 0
                    if not self._stop_event.is_set():
                        await asyncio.sleep(0)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    attempt += 1
                    self.health.connection_errors += 1
                    self.health.reconnect_attempts = attempt
                    self.health.last_error = str(exc)
                    self.health.state = ConnectionState.DEGRADED

                    if (
                        self.reconnect_policy.max_attempts is not None
                        and attempt >= self.reconnect_policy.max_attempts
                    ):
                        break

                    delay = self.reconnect_policy.delay_for_attempt(attempt)
                    await asyncio.sleep(delay)
        finally:
            self._running = False
            await self.transport.close()
            self.health.state = ConnectionState.STOPPED
            self.health.disconnected_at = utc_now()

    async def stop(self) -> None:
        self._stop_event.set()
        self.health.state = ConnectionState.STOPPED
        await self.transport.close()

    def dashboard(self) -> Dict[str, Any]:
        return {
            "symbols": list(self.symbols),
            "running": self._running,
            "health": self.health.to_dict(stale_after=self.stale_after),
            "latest_ticks": {
                symbol: tick.to_dict()
                for symbol, tick in sorted(self.latest_ticks.items())
            },
            "ohlc": self.aggregator.snapshot(),
        }
