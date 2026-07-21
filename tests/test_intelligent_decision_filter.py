from __future__ import annotations

import pytest

from engine.intelligent_decision_filter import (
    DecisionFilterConfig,
    DecisionVerdict,
    IntelligentDecisionFilter,
    IntelligentDecisionRuntimeBridge,
)
from engine.robot_runtime import RuntimeAction, StrategyDecision


def make_decision(
    action=RuntimeAction.BUY,
    *,
    score=80,
    quantity=2.0,
    metadata=None,
):
    return StrategyDecision(
        symbol="BTC/USDT",
        action=action,
        score=score,
        reason="Test sinyali",
        quantity=quantity,
        price=100.0,
        metadata=metadata or {},
    )


def good_context(action=RuntimeAction.BUY):
    return {
        "trend": "UP" if action == RuntimeAction.BUY else "DOWN",
        "rsi": 55 if action == RuntimeAction.BUY else 45,
        "volume_ratio": 1.2,
        "volatility_pct": 2.0,
        "spread_pct": 0.05,
        "market_data_age_seconds": 5,
        "liquidity_score": 95,
    }


class FakeExecution:
    def __init__(self):
        self.calls = []

    def execute(self, decision, context):
        self.calls.append((decision, context))
        return {"status": "NEW"}


def test_config_validation_quality() -> None:
    with pytest.raises(ValueError):
        DecisionFilterConfig(minimum_quality_score=101).validate()


def test_config_validation_reduced() -> None:
    with pytest.raises(ValueError):
        DecisionFilterConfig(
            minimum_quality_score=70,
            reduced_quality_score=60,
        ).validate()


def test_hold_skipped() -> None:
    item = IntelligentDecisionFilter()
    result = item.evaluate(make_decision(RuntimeAction.HOLD))
    assert result.verdict == DecisionVerdict.SKIPPED


def test_filter_disabled_approves() -> None:
    item = IntelligentDecisionFilter(
        DecisionFilterConfig(enabled=False)
    )
    result = item.evaluate(make_decision(), {})
    assert result.verdict == DecisionVerdict.APPROVED


def test_good_buy_approved() -> None:
    item = IntelligentDecisionFilter()
    result = item.evaluate(make_decision(), good_context())
    assert result.verdict == DecisionVerdict.APPROVED
    assert result.final_action == RuntimeAction.BUY


def test_good_sell_approved() -> None:
    item = IntelligentDecisionFilter()
    result = item.evaluate(
        make_decision(RuntimeAction.SELL),
        good_context(RuntimeAction.SELL),
    )
    assert result.verdict == DecisionVerdict.APPROVED
    assert result.final_action == RuntimeAction.SELL


def test_low_strategy_score_rejected() -> None:
    item = IntelligentDecisionFilter()
    result = item.evaluate(
        make_decision(score=40),
        good_context(),
    )
    assert result.verdict == DecisionVerdict.REJECTED
    assert result.final_action == RuntimeAction.HOLD


def test_wrong_buy_trend_rejected() -> None:
    context = good_context()
    context["trend"] = "DOWN"
    result = IntelligentDecisionFilter().evaluate(make_decision(), context)
    assert result.verdict == DecisionVerdict.REJECTED


def test_wrong_sell_trend_rejected() -> None:
    context = good_context(RuntimeAction.SELL)
    context["trend"] = "UP"
    result = IntelligentDecisionFilter().evaluate(
        make_decision(RuntimeAction.SELL),
        context,
    )
    assert result.verdict == DecisionVerdict.REJECTED


def test_high_volatility_rejected() -> None:
    context = good_context()
    context["volatility_pct"] = 10
    result = IntelligentDecisionFilter().evaluate(make_decision(), context)
    assert result.verdict == DecisionVerdict.REJECTED


def test_high_spread_rejected() -> None:
    context = good_context()
    context["spread_pct"] = 0.5
    result = IntelligentDecisionFilter().evaluate(make_decision(), context)
    assert result.verdict == DecisionVerdict.REJECTED


def test_low_volume_rejected() -> None:
    context = good_context()
    context["volume_ratio"] = 0.4
    result = IntelligentDecisionFilter().evaluate(make_decision(), context)
    assert result.verdict == DecisionVerdict.REJECTED


def test_buy_rsi_rejected() -> None:
    context = good_context()
    context["rsi"] = 80
    result = IntelligentDecisionFilter().evaluate(make_decision(), context)
    assert result.verdict == DecisionVerdict.REJECTED


def test_sell_rsi_rejected() -> None:
    context = good_context(RuntimeAction.SELL)
    context["rsi"] = 20
    result = IntelligentDecisionFilter().evaluate(
        make_decision(RuntimeAction.SELL),
        context,
    )
    assert result.verdict == DecisionVerdict.REJECTED


def test_stale_data_rejected() -> None:
    context = good_context()
    context["market_data_age_seconds"] = 200
    result = IntelligentDecisionFilter().evaluate(make_decision(), context)
    assert result.verdict == DecisionVerdict.REJECTED


def test_zero_liquidity_rejected() -> None:
    context = good_context()
    context["liquidity_score"] = 0
    result = IntelligentDecisionFilter().evaluate(make_decision(), context)
    assert result.verdict == DecisionVerdict.REJECTED


def test_rejected_quantity_zero() -> None:
    context = good_context()
    context["trend"] = "DOWN"
    result = IntelligentDecisionFilter().evaluate(make_decision(), context)
    assert result.filtered_decision.quantity == 0


def test_reduced_position() -> None:
    config = DecisionFilterConfig(
        minimum_quality_score=50,
        reduced_quality_score=95,
        reduced_position_factor=0.5,
    )
    item = IntelligentDecisionFilter(config)
    result = item.evaluate(make_decision(), good_context())
    assert result.verdict == DecisionVerdict.REDUCED
    assert result.filtered_decision.quantity == pytest.approx(1.0)


def test_apply_returns_decision() -> None:
    result = IntelligentDecisionFilter().apply(
        make_decision(),
        good_context(),
    )
    assert isinstance(result, StrategyDecision)


def test_metadata_added() -> None:
    result = IntelligentDecisionFilter().evaluate(
        make_decision(),
        good_context(),
    )
    metadata = result.filtered_decision.metadata
    assert "decision_filter_verdict" in metadata
    assert "decision_quality_score" in metadata


def test_reason_updated() -> None:
    result = IntelligentDecisionFilter().evaluate(
        make_decision(),
        good_context(),
    )
    assert "Filtre:" in result.filtered_decision.reason


def test_factor_count() -> None:
    result = IntelligentDecisionFilter().evaluate(
        make_decision(),
        good_context(),
    )
    assert len(result.factors) == 8


def test_factor_weights_total() -> None:
    result = IntelligentDecisionFilter().evaluate(
        make_decision(),
        good_context(),
    )
    assert sum(item.weight for item in result.factors) == pytest.approx(1.0)


def test_warning_news_risk() -> None:
    context = good_context()
    context["news_risk"] = True
    result = IntelligentDecisionFilter().evaluate(make_decision(), context)
    assert "Haber riski işaretlendi." in result.warnings


def test_warning_market_regime() -> None:
    context = good_context()
    context["market_regime"] = "PANIC"
    result = IntelligentDecisionFilter().evaluate(make_decision(), context)
    assert "Olağan dışı piyasa rejimi." in result.warnings


def test_batch_evaluate() -> None:
    item = IntelligentDecisionFilter()
    decisions = [
        make_decision(),
        make_decision(RuntimeAction.SELL),
    ]
    contexts = {
        "BTCUSDT": good_context(),
    }
    results = item.batch_evaluate(decisions, contexts)
    assert len(results) == 2


def test_summary() -> None:
    item = IntelligentDecisionFilter()
    item.evaluate(make_decision(), good_context())
    summary = item.summary()
    assert summary["total"] == 1
    assert summary["counts"]["APPROVED"] == 1


def test_clear_history() -> None:
    item = IntelligentDecisionFilter()
    item.evaluate(make_decision(), good_context())
    item.clear_history()
    assert item.history == []


def test_to_dict() -> None:
    result = IntelligentDecisionFilter().evaluate(
        make_decision(),
        good_context(),
    )
    data = result.to_dict()
    assert data["symbol"] == "BTCUSDT"
    assert data["verdict"] == "APPROVED"


def test_bridge_executes_approved() -> None:
    execution = FakeExecution()
    bridge = IntelligentDecisionRuntimeBridge(
        decision_filter=IntelligentDecisionFilter(),
        execution_engine=execution,
    )
    result = bridge.process(make_decision(), good_context())
    assert result["execution"]["status"] == "NEW"
    assert len(execution.calls) == 1


def test_bridge_does_not_execute_rejected() -> None:
    execution = FakeExecution()
    bridge = IntelligentDecisionRuntimeBridge(
        decision_filter=IntelligentDecisionFilter(),
        execution_engine=execution,
    )
    context = good_context()
    context["trend"] = "DOWN"
    result = bridge.process(make_decision(), context)
    assert result["execution"] is None
    assert execution.calls == []


def test_bridge_dashboard() -> None:
    bridge = IntelligentDecisionRuntimeBridge(
        decision_filter=IntelligentDecisionFilter(),
    )
    data = bridge.dashboard()
    assert "counts" in data


def test_normalize_symbol() -> None:
    assert IntelligentDecisionFilter.normalize_symbol("btc-usdt") == "BTCUSDT"


def test_unknown_trend_rejected_by_default() -> None:
    context = good_context()
    context["trend"] = "UNKNOWN"
    result = IntelligentDecisionFilter().evaluate(make_decision(), context)
    assert result.verdict == DecisionVerdict.REJECTED


def test_unknown_trend_allowed_when_disabled() -> None:
    config = DecisionFilterConfig(require_trend_alignment=False)
    item = IntelligentDecisionFilter(config)
    context = good_context()
    context["trend"] = "UNKNOWN"
    result = item.evaluate(make_decision(), context)
    assert result.verdict in {
        DecisionVerdict.APPROVED,
        DecisionVerdict.REDUCED,
    }
