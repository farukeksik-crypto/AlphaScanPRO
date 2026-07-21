from __future__ import annotations

from engine.smart_exit import SmartExitConfig, evaluate_smart_exit


def test_smart_exit_requires_profit() -> None:
    result = evaluate_smart_exit(
        entry_price=100,
        current_price=100.20,
        current_rsi=60,
        previous_rsi=72,
        macd_hist=-1,
        close_price=99,
        ema20=101,
        volume_ratio=0.50,
        current_adx=20,
        previous_adx=25,
    )
    assert result.should_exit is False
    assert result.status == "PROFIT_FILTER"


def test_single_signal_does_not_exit() -> None:
    result = evaluate_smart_exit(
        entry_price=100,
        current_price=103,
        current_rsi=60,
        previous_rsi=72,
        macd_hist=1,
        close_price=103,
        ema20=100,
        volume_ratio=1.10,
        current_adx=25,
        previous_adx=24,
    )
    assert result.should_exit is False
    assert result.confirmations == 1


def test_two_strong_signals_trigger_exit() -> None:
    result = evaluate_smart_exit(
        entry_price=100,
        current_price=104,
        current_rsi=60,
        previous_rsi=72,
        macd_hist=-0.5,
        close_price=104,
        ema20=101,
        volume_ratio=1.0,
        current_adx=25,
        previous_adx=24,
    )
    assert result.should_exit is True
    assert result.status == "SMART_EXIT"
    assert result.score == 50 or result.score >= 50


def test_configurable_threshold() -> None:
    config = SmartExitConfig(exit_score_threshold=50)
    result = evaluate_smart_exit(
        entry_price=100,
        current_price=104,
        current_rsi=60,
        previous_rsi=72,
        macd_hist=-0.5,
        close_price=104,
        ema20=101,
        volume_ratio=1.0,
        current_adx=25,
        previous_adx=24,
        config=config,
    )
    assert result.should_exit is True
