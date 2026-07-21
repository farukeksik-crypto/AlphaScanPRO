from __future__ import annotations

from engine.ai_decision_engine import AIDecisionEngine


def test_strong_buy_result() -> None:
    engine = AIDecisionEngine()
    result = engine.evaluate(
        technical_score=95,
        trend_quality=92,
        volume_quality=88,
        risk_quality=90,
        market_regime_score=94,
        correlation_quality=85,
        backtest_quality=90,
        fundamental_quality=80,
    )

    assert result.decision == "STRONG BUY"
    assert result.allow_trade is True
    assert result.score >= 88


def test_watch_result() -> None:
    engine = AIDecisionEngine()
    result = engine.evaluate(
        technical_score=68,
        trend_quality=66,
        volume_quality=62,
        risk_quality=70,
        market_regime_score=64,
        correlation_quality=72,
        backtest_quality=60,
        fundamental_quality=55,
    )

    assert result.decision == "WATCH"
    assert result.allow_trade is False


def test_hard_block_overrides_score() -> None:
    engine = AIDecisionEngine()
    result = engine.evaluate(
        technical_score=95,
        trend_quality=95,
        volume_quality=95,
        risk_quality=95,
        market_regime_score=95,
        correlation_quality=95,
        backtest_quality=95,
        fundamental_quality=95,
        hard_block_reasons=["BEAR rejimi"],
    )

    assert result.decision == "NO TRADE"
    assert result.allow_trade is False
    assert any("BEAR rejimi" in reason for reason in result.reasons)


def test_scores_are_clamped() -> None:
    engine = AIDecisionEngine()
    result = engine.evaluate(
        technical_score=140,
        trend_quality=-10,
        volume_quality=50,
        risk_quality=50,
        market_regime_score=50,
        correlation_quality=50,
        backtest_quality=50,
        fundamental_quality=50,
    )

    assert result.components["technical_score"] == 100.0
    assert result.components["trend_quality"] == 0.0
