from __future__ import annotations

import pytest

from engine.smart_exit import (
    SmartExitAction,
    SmartExitConfig,
    evaluate_smart_exit,
)


def _evaluate(**overrides):
    values = {
        "entry_price": 100.0,
        "current_price": 104.0,
        "current_rsi": 60.0,
        "previous_rsi": 72.0,
        "macd_hist": -0.5,
        "close_price": 99.0,
        "ema20": 101.0,
        "volume_ratio": 0.60,
        "current_adx": 16.0,
        "previous_adx": 24.0,
    }
    values.update(overrides)
    return evaluate_smart_exit(**values)


def test_profit_filter_preserves_position() -> None:
    result = _evaluate(current_price=100.20)
    assert result.action == SmartExitAction.HOLD
    assert result.status == "PROFIT_FILTER"
    assert result.should_exit is False


def test_weak_market_can_produce_full_exit() -> None:
    result = _evaluate(break_even_active=True, partial_stage=1)
    assert result.action == SmartExitAction.FULL_EXIT
    assert result.should_full_exit is True
    assert result.score >= 70
    assert result.confirmations >= 3


def test_medium_deterioration_produces_partial_exit() -> None:
    result = _evaluate(
        close_price=104.0,
        ema20=101.0,
        volume_ratio=1.0,
        current_adx=25.0,
        previous_adx=24.0,
    )
    assert result.action == SmartExitAction.PARTIAL_EXIT
    assert result.should_partial_exit is True
    assert result.score == 50


def test_watch_zone_uses_trailing_instead_of_selling() -> None:
    config = SmartExitConfig(
        watch_score_threshold=20,
        partial_exit_score_threshold=60,
        full_exit_score_threshold=80,
    )
    result = _evaluate(
        current_rsi=55.0,
        previous_rsi=60.0,
        macd_hist=0.2,
        close_price=99.0,
        ema20=101.0,
        volume_ratio=1.0,
        current_adx=25.0,
        previous_adx=24.0,
        config=config,
    )
    assert result.action == SmartExitAction.TRAIL
    assert result.should_exit is False


def test_break_even_context_increases_protection_score() -> None:
    plain = _evaluate(
        current_rsi=55.0,
        previous_rsi=60.0,
        macd_hist=-0.1,
        close_price=104.0,
        ema20=101.0,
        volume_ratio=1.0,
        current_adx=25.0,
        previous_adx=24.0,
    )
    protected = _evaluate(
        current_rsi=55.0,
        previous_rsi=60.0,
        macd_hist=-0.1,
        close_price=104.0,
        ema20=101.0,
        volume_ratio=1.0,
        current_adx=25.0,
        previous_adx=24.0,
        break_even_active=True,
    )
    assert protected.score > plain.score
    assert "Kâr koruma modu aktif" in protected.reasons


def test_invalid_threshold_order_is_rejected() -> None:
    with pytest.raises(ValueError):
        SmartExitConfig(
            watch_score_threshold=60,
            partial_exit_score_threshold=50,
            full_exit_score_threshold=70,
        )
