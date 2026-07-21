from __future__ import annotations

import pytest

from engine.live_market_data import (
    BinanceMarketDataParser,
    KlineUpdate,
    MarketDataEvent,
    MarketDataEventType,
    MarketDataState,
)
from engine.robot_runtime import (
    AllowAllRiskGate,
    HoldStrategy,
    NoopExecution,
    RobotRuntime,
    RuntimeAction,
    RuntimeConfig,
    RuntimeStatus,
    StrategyDecision,
)


class FakeMarketDataEngine:
    def __init__(self) -> None:
        self.callbacks = []
        self.events = []
        self.state = MarketDataState()
        self.disconnected = False
        self.failures = []

    def add_callback(self, callback):
        self.callbacks.append(callback)

    def run_once(self):
        if self.failures:
            failure = self.failures.pop(0)
            raise failure
        if not self.events:
            return None
        event = self.events.pop(0)
        self.state.apply(event)
        for callback in list(self.callbacks):
            callback(event)
        return event

    def disconnect(self):
        self.disconnected = True


class BuyStrategy:
    def evaluate(self, *, symbol, interval, kline, context):
        return StrategyDecision(
            symbol=symbol,
            action=RuntimeAction.BUY,
            score=88.0,
            reason="Test al sinyali",
            quantity=1.0,
            price=kline.close,
        )


class RejectRisk:
    def approve(self, decision, context):
        return False, "Risk reddetti"


class CaptureExecution:
    def __init__(self):
        self.calls = []

    def execute(self, decision, context):
        self.calls.append((decision, context))
        return {"status": "FILLED", "symbol": decision.symbol}


class BadStrategy:
    def evaluate(self, **kwargs):
        raise RuntimeError("strategy failed")


def make_kline(
    *,
    symbol: str = "BTCUSDT",
    interval: str = "1h",
    open_time: int = 1,
    closed: bool = True,
) -> MarketDataEvent:
    payload = KlineUpdate(
        symbol=symbol,
        interval=interval,
        open_time=open_time,
        close_time=open_time + 3600,
        open=100.0,
        high=110.0,
        low=90.0,
        close=105.0,
        volume=10.0,
        trade_count=20,
        closed=closed,
    )
    return MarketDataEvent(
        event_type=MarketDataEventType.KLINE,
        symbol=symbol,
        payload=payload,
        raw={},
    )


def make_runtime(**kwargs) -> RobotRuntime:
    market = kwargs.pop("market_data_engine", FakeMarketDataEngine())
    return RobotRuntime(
        config=kwargs.pop(
            "config",
            RuntimeConfig(symbols=["BTC/USDT"]),
        ),
        market_data_engine=market,
        **kwargs,
    )


def test_config_requires_symbol() -> None:
    with pytest.raises(ValueError):
        RuntimeConfig(symbols=[]).validate()


def test_defaults_are_safe() -> None:
    runtime = make_runtime()
    assert isinstance(runtime.strategy, HoldStrategy)
    assert isinstance(runtime.risk_gate, AllowAllRiskGate)
    assert isinstance(runtime.execution, NoopExecution)


def test_bind_callback_once() -> None:
    market = FakeMarketDataEngine()
    runtime = make_runtime(market_data_engine=market)
    runtime.bind_market_data()
    runtime.bind_market_data()
    assert len(market.callbacks) == 1


def test_non_kline_skipped() -> None:
    runtime = make_runtime()
    event = MarketDataEvent(
        MarketDataEventType.TRADE,
        "BTCUSDT",
        {},
        {},
    )
    assert runtime.on_market_event(event) is None
    assert runtime.skipped_event_count == 1


def test_open_kline_skipped() -> None:
    runtime = make_runtime()
    assert runtime.on_market_event(make_kline(closed=False)) is None
    assert runtime.skipped_event_count == 1


def test_wrong_symbol_skipped() -> None:
    runtime = make_runtime()
    assert runtime.on_market_event(make_kline(symbol="ETHUSDT")) is None


def test_wrong_interval_skipped() -> None:
    runtime = make_runtime()
    assert runtime.on_market_event(make_kline(interval="15m")) is None


def test_duplicate_kline_skipped() -> None:
    runtime = make_runtime()
    first = runtime.on_market_event(make_kline(open_time=10))
    second = runtime.on_market_event(make_kline(open_time=10))
    assert first is not None
    assert second is None


def test_hold_cycle_does_not_execute() -> None:
    execution = CaptureExecution()
    runtime = make_runtime(execution=execution)
    result = runtime.on_market_event(make_kline())
    assert result.action == RuntimeAction.HOLD
    assert execution.calls == []


def test_buy_cycle_executes() -> None:
    execution = CaptureExecution()
    runtime = make_runtime(
        strategy=BuyStrategy(),
        execution=execution,
    )
    result = runtime.on_market_event(make_kline())
    assert result.action == RuntimeAction.BUY
    assert result.accepted is True
    assert result.order_result["status"] == "FILLED"
    assert len(execution.calls) == 1


def test_rejected_trade_not_executed() -> None:
    execution = CaptureExecution()
    runtime = make_runtime(
        strategy=BuyStrategy(),
        risk_gate=RejectRisk(),
        execution=execution,
    )
    result = runtime.on_market_event(make_kline())
    assert result.accepted is False
    assert execution.calls == []


def test_strategy_exception_is_recorded() -> None:
    runtime = make_runtime(strategy=BadStrategy())
    result = runtime.on_market_event(make_kline())
    assert result.action == RuntimeAction.ERROR
    assert runtime.error_count == 1
    assert runtime.consecutive_errors == 1


def test_success_resets_consecutive_errors() -> None:
    runtime = make_runtime(strategy=BadStrategy())
    runtime.on_market_event(make_kline(open_time=1))
    runtime.strategy = HoldStrategy()
    runtime.on_market_event(make_kline(open_time=2))
    assert runtime.consecutive_errors == 0


def test_cycle_history_bounded() -> None:
    runtime = make_runtime(
        config=RuntimeConfig(
            symbols=["BTCUSDT"],
            max_cycle_history=2,
        )
    )
    runtime.on_market_event(make_kline(open_time=1))
    runtime.on_market_event(make_kline(open_time=2))
    runtime.on_market_event(make_kline(open_time=3))
    assert len(runtime.cycle_history) == 2


def test_recent_results() -> None:
    runtime = make_runtime()
    runtime.on_market_event(make_kline())
    rows = runtime.recent_results(limit=1)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "BTCUSDT"


def test_pause_resume() -> None:
    runtime = make_runtime()
    runtime.pause()
    assert runtime.status == RuntimeStatus.PAUSED
    runtime.resume()
    assert runtime.status == RuntimeStatus.RUNNING


def test_stop_disconnects_market_data() -> None:
    market = FakeMarketDataEngine()
    runtime = make_runtime(market_data_engine=market)
    runtime.stop()
    assert market.disconnected is True
    assert runtime.status == RuntimeStatus.STOPPED


def test_start_processes_messages() -> None:
    market = FakeMarketDataEngine()
    market.events.append(make_kline())
    runtime = make_runtime(market_data_engine=market)
    processed = runtime.start(max_messages=1)
    assert processed == 1
    assert runtime.processed_event_count == 1
    assert runtime.status == RuntimeStatus.STOPPED


def test_runtime_fails_after_max_errors() -> None:
    market = FakeMarketDataEngine()
    market.failures.extend(
        [RuntimeError("x"), RuntimeError("y")]
    )
    runtime = make_runtime(
        market_data_engine=market,
        config=RuntimeConfig(
            symbols=["BTCUSDT"],
            max_consecutive_errors=2,
        ),
    )
    runtime.start(max_messages=1)
    assert runtime.status == RuntimeStatus.FAILED
    assert runtime.error_count == 2


def test_health_watchdog() -> None:
    clock = {"value": 100.0}
    runtime = make_runtime(
        time_fn=lambda: clock["value"],
        config=RuntimeConfig(
            symbols=["BTCUSDT"],
            watchdog_timeout_seconds=10,
        ),
    )
    runtime.started_at = 100.0
    runtime.status = RuntimeStatus.RUNNING
    assert runtime.health_report().watchdog_ok is True
    clock["value"] = 111.0
    assert runtime.health_report().watchdog_ok is False


def test_health_report_counts() -> None:
    runtime = make_runtime()
    runtime.on_market_event(make_kline())
    report = runtime.health_report()
    assert report.cycle_count == 1
    assert report.processed_event_count == 1


def test_normalized_symbols() -> None:
    runtime = make_runtime(
        config=RuntimeConfig(
            symbols=["BTC/USDT", "eth-usdt"],
        )
    )
    assert runtime.normalized_symbols == {"BTCUSDT", "ETHUSDT"}


def test_callable_strategy_supported() -> None:
    def strategy(**kwargs):
        return StrategyDecision(
            symbol=kwargs["symbol"],
            action=RuntimeAction.HOLD,
            reason="callable",
        )

    runtime = make_runtime(strategy=strategy)
    result = runtime.on_market_event(make_kline())
    assert result.reason.startswith("callable")


def test_callable_risk_gate_supported() -> None:
    runtime = make_runtime(
        strategy=BuyStrategy(),
        risk_gate=lambda decision, context: (False, "blocked"),
    )
    result = runtime.on_market_event(make_kline())
    assert result.accepted is False


def test_callable_execution_supported() -> None:
    runtime = make_runtime(
        strategy=BuyStrategy(),
        execution=lambda decision, context: {"ok": True},
    )
    result = runtime.on_market_event(make_kline())
    assert result.order_result == {"ok": True}


def test_parser_event_can_flow_into_runtime() -> None:
    parser = BinanceMarketDataParser()
    event = parser.parse(
        {
            "e": "kline",
            "E": 1000,
            "s": "BTCUSDT",
            "k": {
                "t": 1,
                "T": 2,
                "i": "1h",
                "o": "1",
                "h": "2",
                "l": "0.5",
                "c": "1.5",
                "v": "100",
                "n": 5,
                "x": True,
            },
        }
    )
    runtime = make_runtime()
    result = runtime.on_market_event(event)
    assert result is not None
    assert result.symbol == "BTCUSDT"
