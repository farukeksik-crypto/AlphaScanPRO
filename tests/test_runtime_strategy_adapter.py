from __future__ import annotations

from dataclasses import dataclass

import pytest

from engine.live_market_data import (
    KlineUpdate,
    MarketDataEvent,
    MarketDataEventType,
)
from engine.robot_runtime import RuntimeAction
from engine.runtime_strategy_adapter import (
    AlphaScanRuntimeStrategyAdapter,
    AlphaScanSignal,
    Candle,
    CandleHistoryStore,
    RuleBasedAlphaScanDecisionEngine,
    RuntimeStrategyBridge,
    SignalLabel,
    StrategyIntegrationConfig,
)


def make_kline(
    *,
    symbol: str = "BTCUSDT",
    interval: str = "1h",
    open_time: int = 1,
    close: float = 100.0,
    closed: bool = True,
) -> KlineUpdate:
    return KlineUpdate(
        symbol=symbol,
        interval=interval,
        open_time=open_time,
        close_time=open_time + 3_600,
        open=close - 1,
        high=close + 2,
        low=close - 2,
        close=close,
        volume=100.0 + open_time,
        trade_count=20,
        closed=closed,
    )


def make_event(**kwargs) -> MarketDataEvent:
    kline = make_kline(**kwargs)
    return MarketDataEvent(
        event_type=MarketDataEventType.KLINE,
        symbol=kline.symbol,
        payload=kline,
        raw={},
    )


class BuyEngine:
    def evaluate(self, **kwargs):
        return {
            "symbol": kwargs["symbol"],
            "label": "NET AL",
            "score": 88,
            "reason": "Test sinyali",
            "price": kwargs["candles"][-1]["close"],
            "stop": 90,
            "target": 120,
        }


class TurkishEngine:
    def analyze(self, **kwargs):
        return {
            "kod": kwargs["symbol"],
            "karar": "SAT",
            "puan": 20,
            "neden": "Çıkış koşulu",
            "fiyat": 99,
        }


@dataclass
class ObjectSignal:
    decision: str = "AL ADAY"
    score: float = 70
    reason: str = "Nesne sonucu"
    price: float = 101


class ObjectEngine:
    def decide(self, **kwargs):
        return ObjectSignal()


class FakeMarket:
    def __init__(self):
        self.callbacks = []

    def add_callback(self, callback):
        self.callbacks.append(callback)


class FakeRuntime:
    def __init__(self):
        self.strategy = None
        self.market_data_engine = FakeMarket()


def seed(adapter, count=3, symbol="BTCUSDT", interval="1h"):
    rows = []
    for index in range(count):
        rows.append(
            {
                "open_time": index + 1,
                "close_time": index + 2,
                "open": 100 + index,
                "high": 102 + index,
                "low": 99 + index,
                "close": 101 + index,
                "volume": 1000 + index,
            }
        )
    return adapter.seed_history(symbol, interval, rows)


def test_config_validation() -> None:
    with pytest.raises(ValueError):
        StrategyIntegrationConfig(min_bars=1).validate()


def test_score_threshold_validation() -> None:
    with pytest.raises(ValueError):
        StrategyIntegrationConfig(buy_score=40, sell_score=50).validate()


def test_candle_from_kline() -> None:
    candle = Candle.from_kline("BTCUSDT", make_kline())
    assert candle.symbol == "BTCUSDT"
    assert candle.close == 100.0


def test_history_append() -> None:
    store = CandleHistoryStore(10)
    assert store.append(Candle.from_kline("BTCUSDT", make_kline())) is True
    assert store.count("BTCUSDT", "1h") == 1


def test_history_duplicate_ignored() -> None:
    store = CandleHistoryStore(10)
    candle = Candle.from_kline("BTCUSDT", make_kline())
    assert store.append(candle) is True
    assert store.append(candle) is False


def test_history_sorted() -> None:
    store = CandleHistoryStore(10)
    store.append(Candle.from_kline("BTCUSDT", make_kline(open_time=2)))
    store.append(Candle.from_kline("BTCUSDT", make_kline(open_time=1)))
    assert [c.open_time for c in store.get("BTCUSDT", "1h")] == [1, 2]


def test_history_bounded() -> None:
    store = CandleHistoryStore(2)
    for index in range(3):
        store.append(Candle.from_kline("BTCUSDT", make_kline(open_time=index)))
    assert store.count("BTCUSDT", "1h") == 2


def test_ingest_closed_kline() -> None:
    adapter = AlphaScanRuntimeStrategyAdapter(
        config=StrategyIntegrationConfig(min_bars=2)
    )
    assert adapter.ingest_event(make_event()) is True


def test_ingest_open_kline_rejected() -> None:
    adapter = AlphaScanRuntimeStrategyAdapter(
        config=StrategyIntegrationConfig(min_bars=2)
    )
    assert adapter.ingest_event(make_event(closed=False)) is False


def test_ingest_non_kline_rejected() -> None:
    adapter = AlphaScanRuntimeStrategyAdapter(
        config=StrategyIntegrationConfig(min_bars=2)
    )
    event = MarketDataEvent(MarketDataEventType.TRADE, "BTCUSDT", {}, {})
    assert adapter.ingest_event(event) is False


def test_seed_history() -> None:
    adapter = AlphaScanRuntimeStrategyAdapter(
        config=StrategyIntegrationConfig(min_bars=2)
    )
    assert seed(adapter, 3) == 3


def test_insufficient_data_returns_hold() -> None:
    adapter = AlphaScanRuntimeStrategyAdapter(
        decision_engine=BuyEngine(),
        config=StrategyIntegrationConfig(min_bars=3),
    )
    result = adapter.evaluate(
        symbol="BTCUSDT",
        interval="1h",
        kline=make_kline(),
        context={},
    )
    assert result.action == RuntimeAction.HOLD
    assert "Yetersiz veri" in result.reason


def test_buy_signal_mapping() -> None:
    adapter = AlphaScanRuntimeStrategyAdapter(
        decision_engine=BuyEngine(),
        config=StrategyIntegrationConfig(min_bars=3),
    )
    seed(adapter, 2)
    result = adapter.evaluate(
        symbol="BTCUSDT",
        interval="1h",
        kline=make_kline(open_time=3),
        context={},
    )
    assert result.action == RuntimeAction.BUY
    assert result.score == 88
    assert result.metadata["stop"] == 90


def test_sell_signal_mapping() -> None:
    adapter = AlphaScanRuntimeStrategyAdapter(
        decision_engine=TurkishEngine(),
        config=StrategyIntegrationConfig(min_bars=2),
    )
    seed(adapter, 1)
    result = adapter.evaluate(
        symbol="BTCUSDT",
        interval="1h",
        kline=make_kline(open_time=2),
        context={},
    )
    assert result.action == RuntimeAction.SELL
    assert result.reason == "Çıkış koşulu"


def test_al_aday_defaults_to_hold() -> None:
    adapter = AlphaScanRuntimeStrategyAdapter(
        decision_engine=ObjectEngine(),
        config=StrategyIntegrationConfig(min_bars=2),
    )
    seed(adapter, 1)
    result = adapter.evaluate(
        symbol="BTCUSDT",
        interval="1h",
        kline=make_kline(open_time=2),
        context={},
    )
    assert result.action == RuntimeAction.HOLD


def test_al_aday_can_buy() -> None:
    adapter = AlphaScanRuntimeStrategyAdapter(
        decision_engine=ObjectEngine(),
        config=StrategyIntegrationConfig(
            min_bars=2,
            allow_al_aday=True,
            buy_score=62,
        ),
    )
    seed(adapter, 1)
    result = adapter.evaluate(
        symbol="BTCUSDT",
        interval="1h",
        kline=make_kline(open_time=2),
        context={},
    )
    assert result.action == RuntimeAction.BUY


def test_callable_engine_supported() -> None:
    adapter = AlphaScanRuntimeStrategyAdapter(
        decision_engine=lambda **kwargs: {
            "label": "BEKLE",
            "score": 50,
            "reason": "Callable",
            "price": 100,
        },
        config=StrategyIntegrationConfig(min_bars=2),
    )
    seed(adapter, 1)
    result = adapter.evaluate(
        symbol="BTCUSDT",
        interval="1h",
        kline=make_kline(open_time=2),
        context={},
    )
    assert result.action == RuntimeAction.HOLD


def test_signal_object_supported() -> None:
    signal = AlphaScanSignal(
        symbol="BTCUSDT",
        label=SignalLabel.NET_AL,
        score=90,
        reason="Hazır signal",
        price=100,
    )
    adapter = AlphaScanRuntimeStrategyAdapter(
        decision_engine=lambda **kwargs: signal,
        config=StrategyIntegrationConfig(min_bars=2),
    )
    seed(adapter, 1)
    result = adapter.evaluate(
        symbol="BTCUSDT",
        interval="1h",
        kline=make_kline(open_time=2),
        context={},
    )
    assert result.action == RuntimeAction.BUY


def test_default_quantity_used() -> None:
    adapter = AlphaScanRuntimeStrategyAdapter(
        decision_engine=BuyEngine(),
        config=StrategyIntegrationConfig(
            min_bars=2,
            default_quantity=0.25,
        ),
    )
    seed(adapter, 1)
    result = adapter.evaluate(
        symbol="BTCUSDT",
        interval="1h",
        kline=make_kline(open_time=2),
        context={},
    )
    assert result.quantity == 0.25


def test_last_signal_saved() -> None:
    adapter = AlphaScanRuntimeStrategyAdapter(
        decision_engine=BuyEngine(),
        config=StrategyIntegrationConfig(min_bars=2),
    )
    seed(adapter, 1)
    adapter.evaluate(
        symbol="BTCUSDT",
        interval="1h",
        kline=make_kline(open_time=2),
        context={},
    )
    assert adapter.last_signal["BTCUSDT"].label == SignalLabel.NET_AL


def test_rule_engine_returns_mapping() -> None:
    engine = RuleBasedAlphaScanDecisionEngine()
    rows = [
        {
            "open": 100,
            "high": 101,
            "low": 99,
            "close": 100 + index,
            "volume": 1000 + index,
        }
        for index in range(5)
    ]
    result = engine.evaluate(symbol="BTCUSDT", candles=rows, context={})
    assert 0 <= result["score"] <= 100
    assert result["label"] in {label.value for label in SignalLabel}


def test_bridge_binds_strategy() -> None:
    runtime = FakeRuntime()
    adapter = AlphaScanRuntimeStrategyAdapter(
        config=StrategyIntegrationConfig(min_bars=2)
    )
    bridge = RuntimeStrategyBridge(
        runtime=runtime,
        strategy_adapter=adapter,
    )
    bridge.bind()
    assert runtime.strategy is adapter
    assert len(runtime.market_data_engine.callbacks) == 1


def test_bridge_binds_once() -> None:
    runtime = FakeRuntime()
    adapter = AlphaScanRuntimeStrategyAdapter(
        config=StrategyIntegrationConfig(min_bars=2)
    )
    bridge = RuntimeStrategyBridge(
        runtime=runtime,
        strategy_adapter=adapter,
    )
    bridge.bind()
    bridge.bind()
    assert len(runtime.market_data_engine.callbacks) == 1


def test_bridge_status() -> None:
    runtime = FakeRuntime()
    adapter = AlphaScanRuntimeStrategyAdapter(
        config=StrategyIntegrationConfig(min_bars=2)
    )
    bridge = RuntimeStrategyBridge(runtime=runtime, strategy_adapter=adapter)
    assert bridge.status()["bound"] is False
    bridge.bind()
    assert bridge.status()["bound"] is True


def test_metadata_contains_bar_count() -> None:
    adapter = AlphaScanRuntimeStrategyAdapter(
        decision_engine=BuyEngine(),
        config=StrategyIntegrationConfig(min_bars=2),
    )
    seed(adapter, 1)
    result = adapter.evaluate(
        symbol="BTCUSDT",
        interval="1h",
        kline=make_kline(open_time=2),
        context={},
    )
    assert result.metadata["bars"] == 2
