from __future__ import annotations

import pytest

from engine.live_event_engine import (
    EventBus,
    EventPriority,
    EventType,
    LiveDataLoop,
    LiveLoopConfig,
    PriorityEventQueue,
    RuntimeEvent,
)


class FakeProvider:
    def __init__(self):
        self.counter = 0

    def fetch(self, symbol, timeframe):
        self.counter += 1
        return {
            "timestamp": self.counter,
            "close": 100 + self.counter,
            "symbol": symbol,
            "timeframe": timeframe,
        }


class DuplicateProvider:
    def fetch(self, symbol, timeframe):
        return {"timestamp": 1, "close": 100}


class ErrorProvider:
    def fetch(self, symbol, timeframe):
        raise RuntimeError("provider failed")


def test_runtime_event_normalizes_symbol():
    event = RuntimeEvent(EventType.NEW_CANDLE, symbol=" btcusdt ")
    assert event.symbol == "BTCUSDT"


def test_runtime_event_payload_validation():
    with pytest.raises(TypeError):
        RuntimeEvent(EventType.NEW_CANDLE, payload=[])


def test_runtime_event_to_dict():
    event = RuntimeEvent(EventType.SIGNAL, payload={"score": 80})
    data = event.to_dict()
    assert data["event_type"] == "SIGNAL"
    assert data["payload"]["score"] == 80


def test_event_bus_subscribe_and_dispatch():
    bus = EventBus()
    seen = []

    def handler(event):
        seen.append(event.symbol)
        return "ok"

    bus.subscribe(EventType.NEW_CANDLE, handler)
    report = bus.dispatch(RuntimeEvent(EventType.NEW_CANDLE, symbol="BTCUSDT"))
    assert report.success
    assert report.handled == 1
    assert seen == ["BTCUSDT"]


def test_event_bus_wildcard():
    bus = EventBus()
    seen = []
    bus.subscribe(None, lambda event: seen.append(event.event_type))
    bus.dispatch(RuntimeEvent(EventType.HEARTBEAT))
    assert seen == [EventType.HEARTBEAT]


def test_event_bus_duplicate_subscription_blocked():
    bus = EventBus()

    def handler(event):
        return None

    bus.subscribe(EventType.SIGNAL, handler)
    bus.subscribe(EventType.SIGNAL, handler)
    assert bus.subscriber_count(EventType.SIGNAL) == 1


def test_event_bus_unsubscribe():
    bus = EventBus()

    def handler(event):
        return None

    bus.subscribe(EventType.SIGNAL, handler)
    assert bus.unsubscribe(EventType.SIGNAL, handler)
    assert not bus.unsubscribe(EventType.SIGNAL, handler)


def test_event_bus_error_continue():
    bus = EventBus()

    def bad(event):
        raise ValueError("bad")

    bus.subscribe(EventType.SIGNAL, bad)
    bus.subscribe(EventType.SIGNAL, lambda event: "ok")
    report = bus.dispatch(RuntimeEvent(EventType.SIGNAL))
    assert report.failed == 1
    assert report.successful == 1


def test_event_bus_error_stop():
    bus = EventBus()

    def bad(event):
        raise ValueError("bad")

    bus.subscribe(EventType.SIGNAL, bad)
    bus.subscribe(EventType.SIGNAL, lambda event: "ok")
    report = bus.dispatch(
        RuntimeEvent(EventType.SIGNAL),
        continue_on_error=False,
    )
    assert report.handled == 1
    assert report.failed == 1


def test_event_bus_history():
    bus = EventBus(history_limit=2)
    for _ in range(3):
        bus.dispatch(RuntimeEvent(EventType.HEARTBEAT))
    assert len(bus.history()) == 2
    assert len(bus.history(1)) == 1


def test_event_bus_clear_history():
    bus = EventBus()
    bus.dispatch(RuntimeEvent(EventType.HEARTBEAT))
    bus.clear_history()
    assert bus.history() == []


def test_queue_priority():
    queue = PriorityEventQueue()
    queue.put(RuntimeEvent(EventType.HEARTBEAT, priority=EventPriority.LOW))
    queue.put(RuntimeEvent(EventType.ERROR, priority=EventPriority.CRITICAL))
    assert queue.get().event_type == EventType.ERROR


def test_queue_fifo_same_priority():
    queue = PriorityEventQueue()
    first = queue.put(RuntimeEvent(EventType.SIGNAL))
    second = queue.put(RuntimeEvent(EventType.ORDER_REQUEST))
    assert queue.get().sequence == first.sequence
    assert queue.get().sequence == second.sequence


def test_queue_overflow():
    queue = PriorityEventQueue(max_size=1)
    queue.put(RuntimeEvent(EventType.SIGNAL))
    with pytest.raises(OverflowError):
        queue.put(RuntimeEvent(EventType.SIGNAL))


def test_queue_peek_and_clear():
    queue = PriorityEventQueue()
    queue.put(RuntimeEvent(EventType.SIGNAL))
    assert queue.peek().event_type == EventType.SIGNAL
    queue.clear()
    assert len(queue) == 0


def test_live_config_symbol_cleanup():
    config = LiveLoopConfig(symbols=[" btcusdt ", "BTCUSDT", "ethusdt"])
    assert config.symbols == ["BTCUSDT", "ETHUSDT"]


def test_live_config_requires_symbol():
    with pytest.raises(ValueError):
        LiveLoopConfig(symbols=[])


def test_live_loop_run_once_emits():
    bus = EventBus()
    captured = []
    bus.subscribe(EventType.NEW_CANDLE, captured.append)
    loop = LiveDataLoop(
        FakeProvider(),
        bus,
        LiveLoopConfig(symbols=["BTCUSDT", "ETHUSDT"]),
    )
    reports = loop.run_once()
    assert len(reports) == 2
    assert len(captured) == 2
    assert loop.stats.emitted == 2


def test_live_loop_skips_duplicate():
    bus = EventBus()
    loop = LiveDataLoop(
        DuplicateProvider(),
        bus,
        LiveLoopConfig(symbols=["BTCUSDT"]),
    )
    loop.run_once()
    loop.run_once()
    assert loop.stats.emitted == 1
    assert loop.stats.duplicates_skipped == 1


def test_live_loop_can_emit_duplicate():
    bus = EventBus()
    loop = LiveDataLoop(
        DuplicateProvider(),
        bus,
        LiveLoopConfig(
            symbols=["BTCUSDT"],
            emit_duplicate_data=True,
        ),
    )
    loop.run_once()
    loop.run_once()
    assert loop.stats.emitted == 2


def test_live_loop_error_event():
    bus = EventBus()
    errors = []
    bus.subscribe(EventType.ERROR, errors.append)
    loop = LiveDataLoop(
        ErrorProvider(),
        bus,
        LiveLoopConfig(symbols=["BTCUSDT"]),
    )
    loop.run_once()
    assert loop.stats.errors == 1
    assert len(errors) == 1


def test_live_loop_error_raise():
    bus = EventBus()
    loop = LiveDataLoop(
        ErrorProvider(),
        bus,
        LiveLoopConfig(
            symbols=["BTCUSDT"],
            continue_on_provider_error=False,
        ),
    )
    with pytest.raises(RuntimeError):
        loop.run_once()


def test_live_loop_run_max_cycles():
    bus = EventBus()
    shutdown = []
    bus.subscribe(EventType.SHUTDOWN, shutdown.append)
    loop = LiveDataLoop(
        FakeProvider(),
        bus,
        LiveLoopConfig(
            symbols=["BTCUSDT"],
            poll_interval_seconds=0.001,
        ),
    )
    stats = loop.run(max_cycles=2)
    assert stats.cycles == 2
    assert len(shutdown) == 1
    assert not loop.running


def test_live_loop_stop():
    bus = EventBus()
    loop = LiveDataLoop(
        FakeProvider(),
        bus,
        LiveLoopConfig(symbols=["BTCUSDT"]),
    )
    loop.stop()
    assert not loop.running


def test_live_loop_dashboard():
    bus = EventBus()
    loop = LiveDataLoop(
        FakeProvider(),
        bus,
        LiveLoopConfig(symbols=["BTCUSDT"], timeframe="1h"),
    )
    loop.run_once()
    dashboard = loop.dashboard()
    assert dashboard["timeframe"] == "1h"
    assert dashboard["stats"]["emitted"] == 1


def test_live_loop_reset():
    bus = EventBus()
    loop = LiveDataLoop(
        FakeProvider(),
        bus,
        LiveLoopConfig(symbols=["BTCUSDT"]),
    )
    loop.run_once()
    loop.reset()
    assert loop.stats.cycles == 0
    assert loop.dashboard()["last_fingerprints"] == {}


def test_dispatch_report_to_dict():
    bus = EventBus()
    bus.subscribe(EventType.SIGNAL, lambda event: {"ok": True})
    report = bus.dispatch(RuntimeEvent(EventType.SIGNAL))
    data = report.to_dict()
    assert data["success"] is True
    assert data["results"][0]["output"] == {"ok": True}


def test_invalid_history_limit():
    with pytest.raises(ValueError):
        EventBus(history_limit=0)


def test_invalid_queue_size():
    with pytest.raises(ValueError):
        PriorityEventQueue(max_size=0)


def test_invalid_run_limits():
    bus = EventBus()
    loop = LiveDataLoop(
        FakeProvider(),
        bus,
        LiveLoopConfig(symbols=["BTCUSDT"]),
    )
    with pytest.raises(ValueError):
        loop.run(max_cycles=0)
    with pytest.raises(ValueError):
        loop.run(max_runtime_seconds=0)
