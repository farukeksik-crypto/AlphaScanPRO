from __future__ import annotations

import pytest

from engine.multi_timeframe_confirmation import (
    MultiTimeframeConfig,
    MultiTimeframeConfirmationEngine,
    MultiTimeframeRuntimeBridge,
    TimeframeRule,
    TimeframeSignal,
    TimeframeTrend,
    TimeframeVerdict,
)
from engine.robot_runtime import RuntimeAction, StrategyDecision


def decision(action=RuntimeAction.BUY, quantity=2.0):
    return StrategyDecision(
        symbol="BTC/USDT",
        action=action,
        score=80,
        reason="Test sinyali",
        quantity=quantity,
        price=100.0,
        metadata={},
    )


def bullish_signals():
    return {
        "15m": {"trend": "BULLISH", "score": 85},
        "1h": {"trend": "BULLISH", "score": 90},
        "4h": {"trend": "BULLISH", "score": 88},
        "1d": {"trend": "BULLISH", "score": 82},
    }


def bearish_signals():
    return {
        "15m": {"trend": "BEARISH", "score": 85},
        "1h": {"trend": "BEARISH", "score": 90},
        "4h": {"trend": "BEARISH", "score": 88},
        "1d": {"trend": "BEARISH", "score": 82},
    }


class FakeNextStage:
    def __init__(self):
        self.calls = []

    def process(self, decision, context):
        self.calls.append((decision, context))
        return {"status": "OK"}


def test_rule_validation() -> None:
    with pytest.raises(ValueError):
        TimeframeRule("1h", 0).validate()


def test_config_validation_score() -> None:
    with pytest.raises(ValueError):
        MultiTimeframeConfig(minimum_confirmation_score=101).validate()


def test_config_validation_order() -> None:
    with pytest.raises(ValueError):
        MultiTimeframeConfig(
            minimum_confirmation_score=80,
            full_confirmation_score=70,
        ).validate()


def test_hold_skipped() -> None:
    engine = MultiTimeframeConfirmationEngine()
    result = engine.evaluate(decision(RuntimeAction.HOLD), {})
    assert result.verdict == TimeframeVerdict.SKIPPED


def test_disabled_confirmed() -> None:
    engine = MultiTimeframeConfirmationEngine(
        MultiTimeframeConfig(enabled=False)
    )
    result = engine.evaluate(decision(), {})
    assert result.verdict == TimeframeVerdict.CONFIRMED


def test_buy_confirmed() -> None:
    result = MultiTimeframeConfirmationEngine().evaluate(
        decision(),
        bullish_signals(),
    )
    assert result.verdict == TimeframeVerdict.CONFIRMED
    assert result.final_action == RuntimeAction.BUY


def test_sell_confirmed() -> None:
    result = MultiTimeframeConfirmationEngine().evaluate(
        decision(RuntimeAction.SELL),
        bearish_signals(),
    )
    assert result.verdict == TimeframeVerdict.CONFIRMED
    assert result.final_action == RuntimeAction.SELL


def test_required_conflict_rejected() -> None:
    signals = bullish_signals()
    signals["4h"] = {"trend": "BEARISH", "score": 90}
    result = MultiTimeframeConfirmationEngine().evaluate(decision(), signals)
    assert result.verdict == TimeframeVerdict.REJECTED


def test_required_missing_rejected() -> None:
    signals = bullish_signals()
    del signals["1h"]
    result = MultiTimeframeConfirmationEngine().evaluate(decision(), signals)
    assert result.verdict == TimeframeVerdict.REJECTED


def test_daily_conflict_rejected() -> None:
    signals = bullish_signals()
    signals["1d"] = {"trend": "BEARISH", "score": 90}
    result = MultiTimeframeConfirmationEngine().evaluate(decision(), signals)
    assert result.verdict == TimeframeVerdict.REJECTED


def test_partial_confirmation() -> None:
    config = MultiTimeframeConfig(
        minimum_confirmation_score=50,
        full_confirmation_score=95,
        reject_on_daily_conflict=False,
    )
    signals = bullish_signals()
    signals["15m"] = {"trend": "NEUTRAL", "score": 40}
    signals["1d"] = {"trend": "NEUTRAL", "score": 40}
    result = MultiTimeframeConfirmationEngine(config).evaluate(
        decision(),
        signals,
    )
    assert result.verdict == TimeframeVerdict.PARTIAL
    assert result.filtered_decision.quantity == pytest.approx(1.0)


def test_rejected_quantity_zero() -> None:
    signals = bullish_signals()
    signals["1h"] = {"trend": "BEARISH", "score": 90}
    result = MultiTimeframeConfirmationEngine().evaluate(decision(), signals)
    assert result.filtered_decision.quantity == 0


def test_metadata_added() -> None:
    result = MultiTimeframeConfirmationEngine().evaluate(
        decision(),
        bullish_signals(),
    )
    assert "multi_timeframe_verdict" in result.filtered_decision.metadata


def test_reason_updated() -> None:
    result = MultiTimeframeConfirmationEngine().evaluate(
        decision(),
        bullish_signals(),
    )
    assert "MTF:" in result.filtered_decision.reason


def test_apply_returns_decision() -> None:
    filtered = MultiTimeframeConfirmationEngine().apply(
        decision(),
        bullish_signals(),
    )
    assert isinstance(filtered, StrategyDecision)


def test_summary() -> None:
    engine = MultiTimeframeConfirmationEngine()
    engine.evaluate(decision(), bullish_signals())
    summary = engine.summary()
    assert summary["total"] == 1
    assert summary["counts"]["CONFIRMED"] == 1


def test_clear_history() -> None:
    engine = MultiTimeframeConfirmationEngine()
    engine.evaluate(decision(), bullish_signals())
    engine.clear_history()
    assert engine.history == []


def test_infer_bullish() -> None:
    assert (
        MultiTimeframeConfirmationEngine.infer_trend(
            close=110,
            ema_fast=105,
            ema_slow=100,
        )
        == TimeframeTrend.BULLISH
    )


def test_infer_bearish() -> None:
    assert (
        MultiTimeframeConfirmationEngine.infer_trend(
            close=90,
            ema_fast=95,
            ema_slow=100,
        )
        == TimeframeTrend.BEARISH
    )


def test_infer_neutral() -> None:
    assert (
        MultiTimeframeConfirmationEngine.infer_trend(
            close=100,
            ema_fast=105,
            ema_slow=95,
        )
        == TimeframeTrend.NEUTRAL
    )


def test_infer_unknown() -> None:
    assert (
        MultiTimeframeConfirmationEngine.infer_trend(
            close=None,
            ema_fast=105,
            ema_slow=100,
        )
        == TimeframeTrend.UNKNOWN
    )


def test_signal_from_indicators() -> None:
    signal = MultiTimeframeConfirmationEngine.signal_from_indicators(
        "1h",
        {
            "close": 110,
            "ema20": 105,
            "ema50": 100,
            "score": 80,
            "rsi": 55,
        },
    )
    assert signal.trend == TimeframeTrend.BULLISH
    assert signal.rsi == 55


def test_timeframe_alias() -> None:
    assert MultiTimeframeConfirmationEngine.normalize_timeframe("60m") == "1h"


def test_trend_alias() -> None:
    signal = MultiTimeframeConfirmationEngine.signal_from_indicators(
        "1h",
        {"trend": "UP", "score": 80},
    )
    assert signal.trend == TimeframeTrend.BULLISH


def test_unknown_optional_allowed() -> None:
    signals = bullish_signals()
    signals["15m"] = {"trend": "UNKNOWN", "score": 50}
    result = MultiTimeframeConfirmationEngine().evaluate(decision(), signals)
    assert result.verdict in {
        TimeframeVerdict.CONFIRMED,
        TimeframeVerdict.PARTIAL,
    }


def test_bridge_calls_next_stage() -> None:
    next_stage = FakeNextStage()
    bridge = MultiTimeframeRuntimeBridge(
        confirmation_engine=MultiTimeframeConfirmationEngine(),
        next_stage=next_stage,
    )
    result = bridge.process(decision(), bullish_signals(), {"x": 1})
    assert result["next_stage"]["status"] == "OK"
    assert len(next_stage.calls) == 1


def test_bridge_blocks_rejected() -> None:
    next_stage = FakeNextStage()
    bridge = MultiTimeframeRuntimeBridge(
        confirmation_engine=MultiTimeframeConfirmationEngine(),
        next_stage=next_stage,
    )
    signals = bullish_signals()
    signals["4h"] = {"trend": "BEARISH", "score": 90}
    result = bridge.process(decision(), signals, {})
    assert result["next_stage"] is None
    assert next_stage.calls == []


def test_bridge_dashboard() -> None:
    bridge = MultiTimeframeRuntimeBridge(
        confirmation_engine=MultiTimeframeConfirmationEngine(),
    )
    data = bridge.dashboard()
    assert "counts" in data


def test_to_dict() -> None:
    result = MultiTimeframeConfirmationEngine().evaluate(
        decision(),
        bullish_signals(),
    )
    data = result.to_dict()
    assert data["symbol"] == "BTCUSDT"
    assert data["verdict"] == "CONFIRMED"


def test_signal_dataclass_to_dict() -> None:
    signal = TimeframeSignal(
        timeframe="1h",
        trend=TimeframeTrend.BULLISH,
        score=80,
    )
    assert signal.to_dict()["trend"] == "BULLISH"


def test_custom_rules() -> None:
    config = MultiTimeframeConfig(
        rules=[
            TimeframeRule("1h", 0.5, True),
            TimeframeRule("4h", 0.5, True),
        ]
    )
    result = MultiTimeframeConfirmationEngine(config).evaluate(
        decision(),
        {
            "1h": {"trend": "BULLISH", "score": 90},
            "4h": {"trend": "BULLISH", "score": 90},
        },
    )
    assert result.verdict == TimeframeVerdict.CONFIRMED
