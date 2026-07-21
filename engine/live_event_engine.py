from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from threading import Event as ThreadEvent, Lock
from time import monotonic, sleep
from typing import Any, Callable, Deque, Dict, Iterable, List, Optional, Protocol


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EventType(str, Enum):
    MARKET_TICK = "MARKET_TICK"
    NEW_CANDLE = "NEW_CANDLE"
    ANALYSIS_REQUEST = "ANALYSIS_REQUEST"
    SIGNAL = "SIGNAL"
    ORDER_REQUEST = "ORDER_REQUEST"
    ORDER_UPDATE = "ORDER_UPDATE"
    POSITION_UPDATE = "POSITION_UPDATE"
    RISK_UPDATE = "RISK_UPDATE"
    HEARTBEAT = "HEARTBEAT"
    ERROR = "ERROR"
    SHUTDOWN = "SHUTDOWN"


class EventPriority(int, Enum):
    CRITICAL = 0
    HIGH = 10
    NORMAL = 50
    LOW = 90


@dataclass(slots=True)
class RuntimeEvent:
    event_type: EventType
    payload: Dict[str, Any] = field(default_factory=dict)
    symbol: Optional[str] = None
    source: str = "system"
    priority: EventPriority = EventPriority.NORMAL
    created_at: datetime = field(default_factory=utc_now)
    sequence: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.event_type, EventType):
            self.event_type = EventType(str(self.event_type))
        if not isinstance(self.priority, EventPriority):
            self.priority = EventPriority(int(self.priority))
        if self.symbol is not None:
            self.symbol = self.symbol.strip().upper()
        self.source = str(self.source).strip() or "system"
        if not isinstance(self.payload, dict):
            raise TypeError("payload sözlük olmalıdır.")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "payload": dict(self.payload),
            "symbol": self.symbol,
            "source": self.source,
            "priority": int(self.priority),
            "created_at": self.created_at.isoformat(),
            "sequence": self.sequence,
        }


class EventHandler(Protocol):
    def __call__(self, event: RuntimeEvent) -> Any:
        ...


@dataclass(slots=True)
class HandlerResult:
    event_type: EventType
    handler_name: str
    success: bool
    output: Any = None
    error: Optional[str] = None


@dataclass(slots=True)
class EventDispatchReport:
    event: RuntimeEvent
    handled: int
    successful: int
    failed: int
    results: List[HandlerResult] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.failed == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event": self.event.to_dict(),
            "handled": self.handled,
            "successful": self.successful,
            "failed": self.failed,
            "success": self.success,
            "results": [
                {
                    "event_type": item.event_type.value,
                    "handler_name": item.handler_name,
                    "success": item.success,
                    "output": item.output,
                    "error": item.error,
                }
                for item in self.results
            ],
        }


class EventBus:
    def __init__(self, *, history_limit: int = 500) -> None:
        if history_limit <= 0:
            raise ValueError("history_limit pozitif olmalıdır.")
        self._handlers: Dict[EventType, List[EventHandler]] = {}
        self._wildcard_handlers: List[EventHandler] = []
        self._history: Deque[EventDispatchReport] = deque(maxlen=history_limit)
        self._lock = Lock()

    @staticmethod
    def _handler_name(handler: EventHandler) -> str:
        return getattr(handler, "__name__", handler.__class__.__name__)

    def subscribe(
        self,
        event_type: Optional[EventType],
        handler: EventHandler,
    ) -> None:
        if not callable(handler):
            raise TypeError("handler çağrılabilir olmalıdır.")
        with self._lock:
            if event_type is None:
                if handler not in self._wildcard_handlers:
                    self._wildcard_handlers.append(handler)
                return
            event_type = EventType(event_type)
            bucket = self._handlers.setdefault(event_type, [])
            if handler not in bucket:
                bucket.append(handler)

    def unsubscribe(
        self,
        event_type: Optional[EventType],
        handler: EventHandler,
    ) -> bool:
        with self._lock:
            bucket = (
                self._wildcard_handlers
                if event_type is None
                else self._handlers.get(EventType(event_type), [])
            )
            if handler not in bucket:
                return False
            bucket.remove(handler)
            return True

    def dispatch(
        self,
        event: RuntimeEvent,
        *,
        continue_on_error: bool = True,
    ) -> EventDispatchReport:
        if not isinstance(event, RuntimeEvent):
            raise TypeError("event RuntimeEvent olmalıdır.")

        with self._lock:
            handlers = list(self._handlers.get(event.event_type, []))
            handlers.extend(self._wildcard_handlers)

        results: List[HandlerResult] = []
        for handler in handlers:
            try:
                output = handler(event)
                results.append(
                    HandlerResult(
                        event_type=event.event_type,
                        handler_name=self._handler_name(handler),
                        success=True,
                        output=output,
                    )
                )
            except Exception as exc:
                results.append(
                    HandlerResult(
                        event_type=event.event_type,
                        handler_name=self._handler_name(handler),
                        success=False,
                        error=f"{exc.__class__.__name__}: {exc}",
                    )
                )
                if not continue_on_error:
                    break

        report = EventDispatchReport(
            event=event,
            handled=len(results),
            successful=sum(1 for item in results if item.success),
            failed=sum(1 for item in results if not item.success),
            results=results,
        )
        with self._lock:
            self._history.append(report)
        return report

    def history(self, limit: Optional[int] = None) -> List[EventDispatchReport]:
        with self._lock:
            items = list(self._history)
        if limit is None:
            return items
        if limit < 0:
            raise ValueError("limit negatif olamaz.")
        return items[-limit:] if limit else []

    def clear_history(self) -> None:
        with self._lock:
            self._history.clear()

    def subscriber_count(self, event_type: Optional[EventType] = None) -> int:
        with self._lock:
            if event_type is None:
                return len(self._wildcard_handlers)
            return len(self._handlers.get(EventType(event_type), []))


class PriorityEventQueue:
    def __init__(self, *, max_size: int = 10_000) -> None:
        if max_size <= 0:
            raise ValueError("max_size pozitif olmalıdır.")
        self.max_size = max_size
        self._events: List[RuntimeEvent] = []
        self._sequence = 0
        self._lock = Lock()

    def put(self, event: RuntimeEvent) -> RuntimeEvent:
        if not isinstance(event, RuntimeEvent):
            raise TypeError("event RuntimeEvent olmalıdır.")
        with self._lock:
            if len(self._events) >= self.max_size:
                raise OverflowError("Event kuyruğu dolu.")
            self._sequence += 1
            event.sequence = self._sequence
            self._events.append(event)
            self._events.sort(key=lambda item: (int(item.priority), item.sequence))
        return event

    def get(self) -> Optional[RuntimeEvent]:
        with self._lock:
            if not self._events:
                return None
            return self._events.pop(0)

    def peek(self) -> Optional[RuntimeEvent]:
        with self._lock:
            return self._events[0] if self._events else None

    def clear(self) -> None:
        with self._lock:
            self._events.clear()

    def snapshot(self) -> List[RuntimeEvent]:
        with self._lock:
            return list(self._events)

    def __len__(self) -> int:
        with self._lock:
            return len(self._events)


class MarketDataProvider(Protocol):
    def fetch(self, symbol: str, timeframe: str) -> Any:
        ...


@dataclass(slots=True)
class LiveLoopConfig:
    symbols: List[str]
    timeframe: str = "1m"
    poll_interval_seconds: float = 1.0
    heartbeat_interval_seconds: float = 30.0
    emit_duplicate_data: bool = False
    continue_on_provider_error: bool = True

    def __post_init__(self) -> None:
        cleaned = []
        for symbol in self.symbols:
            normalized = str(symbol).strip().upper()
            if normalized and normalized not in cleaned:
                cleaned.append(normalized)
        if not cleaned:
            raise ValueError("En az bir sembol gereklidir.")
        if not self.timeframe.strip():
            raise ValueError("timeframe boş olamaz.")
        if self.poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds pozitif olmalıdır.")
        if self.heartbeat_interval_seconds <= 0:
            raise ValueError("heartbeat_interval_seconds pozitif olmalıdır.")
        self.symbols = cleaned
        self.timeframe = self.timeframe.strip()


@dataclass(slots=True)
class LiveLoopStats:
    cycles: int = 0
    fetched: int = 0
    emitted: int = 0
    duplicates_skipped: int = 0
    errors: int = 0
    heartbeats: int = 0
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cycles": self.cycles,
            "fetched": self.fetched,
            "emitted": self.emitted,
            "duplicates_skipped": self.duplicates_skipped,
            "errors": self.errors,
            "heartbeats": self.heartbeats,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
        }


class LiveDataLoop:
    def __init__(
        self,
        provider: MarketDataProvider,
        event_bus: EventBus,
        config: LiveLoopConfig,
    ) -> None:
        if provider is None or not hasattr(provider, "fetch"):
            raise TypeError("provider fetch metoduna sahip olmalıdır.")
        self.provider = provider
        self.event_bus = event_bus
        self.config = config
        self.stats = LiveLoopStats()
        self._last_fingerprints: Dict[str, str] = {}
        self._stop = ThreadEvent()
        self._running = False
        self._last_heartbeat_monotonic = monotonic()

    @staticmethod
    def _fingerprint(data: Any) -> str:
        if isinstance(data, dict):
            preferred = (
                data.get("timestamp"),
                data.get("time"),
                data.get("datetime"),
                data.get("close"),
                data.get("price"),
            )
            return repr(preferred if any(item is not None for item in preferred) else data)
        return repr(data)

    @staticmethod
    def _event_payload(data: Any, timeframe: str) -> Dict[str, Any]:
        return {"timeframe": timeframe, "data": data}

    def stop(self) -> None:
        self._stop.set()

    @property
    def running(self) -> bool:
        return self._running

    def reset(self) -> None:
        if self._running:
            raise RuntimeError("Çalışan döngü sıfırlanamaz.")
        self._stop.clear()
        self._last_fingerprints.clear()
        self.stats = LiveLoopStats()

    def run_once(self) -> List[EventDispatchReport]:
        reports: List[EventDispatchReport] = []
        self.stats.cycles += 1

        for symbol in self.config.symbols:
            try:
                data = self.provider.fetch(symbol, self.config.timeframe)
                self.stats.fetched += 1
                fingerprint = self._fingerprint(data)
                previous = self._last_fingerprints.get(symbol)

                if (
                    previous == fingerprint
                    and not self.config.emit_duplicate_data
                ):
                    self.stats.duplicates_skipped += 1
                    continue

                self._last_fingerprints[symbol] = fingerprint
                report = self.event_bus.dispatch(
                    RuntimeEvent(
                        event_type=EventType.NEW_CANDLE,
                        symbol=symbol,
                        source=self.provider.__class__.__name__,
                        payload=self._event_payload(data, self.config.timeframe),
                        priority=EventPriority.HIGH,
                    )
                )
                reports.append(report)
                self.stats.emitted += 1
            except Exception as exc:
                self.stats.errors += 1
                report = self.event_bus.dispatch(
                    RuntimeEvent(
                        event_type=EventType.ERROR,
                        symbol=symbol,
                        source=self.provider.__class__.__name__,
                        payload={
                            "timeframe": self.config.timeframe,
                            "error": f"{exc.__class__.__name__}: {exc}",
                        },
                        priority=EventPriority.CRITICAL,
                    )
                )
                reports.append(report)
                if not self.config.continue_on_provider_error:
                    raise

        now = monotonic()
        if now - self._last_heartbeat_monotonic >= self.config.heartbeat_interval_seconds:
            reports.append(
                self.event_bus.dispatch(
                    RuntimeEvent(
                        event_type=EventType.HEARTBEAT,
                        source="LiveDataLoop",
                        payload=self.stats.to_dict(),
                        priority=EventPriority.LOW,
                    )
                )
            )
            self.stats.heartbeats += 1
            self._last_heartbeat_monotonic = now

        return reports

    def run(
        self,
        *,
        max_cycles: Optional[int] = None,
        max_runtime_seconds: Optional[float] = None,
    ) -> LiveLoopStats:
        if max_cycles is not None and max_cycles <= 0:
            raise ValueError("max_cycles pozitif olmalıdır.")
        if max_runtime_seconds is not None and max_runtime_seconds <= 0:
            raise ValueError("max_runtime_seconds pozitif olmalıdır.")
        if self._running:
            raise RuntimeError("LiveDataLoop zaten çalışıyor.")

        self._running = True
        self._stop.clear()
        self.stats.started_at = utc_now()
        start = monotonic()

        try:
            while not self._stop.is_set():
                self.run_once()

                if max_cycles is not None and self.stats.cycles >= max_cycles:
                    break
                if (
                    max_runtime_seconds is not None
                    and monotonic() - start >= max_runtime_seconds
                ):
                    break

                sleep(self.config.poll_interval_seconds)
        finally:
            self._running = False
            self.stats.stopped_at = utc_now()
            self.event_bus.dispatch(
                RuntimeEvent(
                    event_type=EventType.SHUTDOWN,
                    source="LiveDataLoop",
                    payload=self.stats.to_dict(),
                    priority=EventPriority.CRITICAL,
                )
            )
        return self.stats

    def dashboard(self) -> Dict[str, Any]:
        return {
            "running": self.running,
            "symbols": list(self.config.symbols),
            "timeframe": self.config.timeframe,
            "poll_interval_seconds": self.config.poll_interval_seconds,
            "stats": self.stats.to_dict(),
            "last_fingerprints": dict(self._last_fingerprints),
        }
