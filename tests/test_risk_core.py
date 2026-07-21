from __future__ import annotations

import pytest

from engine.risk_core import RiskConfig, RiskCore


def test_position_size_calculation() -> None:
    core = RiskCore(
        RiskConfig(
            risk_per_trade_pct=1.0,
            min_stop_distance_pct=0.1,
        )
    )

    result = core.calculate_position_size(
        equity=100_000,
        entry_price=100,
        stop_price=95,
    )

    assert result.allowed is True
    assert result.risk_amount == 1000
    assert result.quantity == 200
    assert result.position_value == 20_000


def test_position_size_respects_available_cash() -> None:
    core = RiskCore(
        RiskConfig(
            risk_per_trade_pct=2.0,
            min_stop_distance_pct=0.1,
        )
    )

    result = core.calculate_position_size(
        equity=100_000,
        entry_price=100,
        stop_price=95,
        available_cash=5_000,
    )

    assert result.allowed is True
    assert result.position_value == 5_000
    assert result.quantity == 50
    assert result.risk_amount == 250


def test_daily_loss_limit_blocks_trade() -> None:
    core = RiskCore(RiskConfig(max_daily_loss_pct=3.0))

    decision = core.check_daily_limits(
        starting_equity=100_000,
        current_equity=96_500,
        daily_trade_count=1,
        consecutive_losses=1,
    )

    assert decision.allowed is False
    assert decision.code == "DAILY_LOSS_LIMIT"


def test_trade_and_consecutive_loss_limits() -> None:
    core = RiskCore(
        RiskConfig(
            max_daily_trades=5,
            max_consecutive_losses=3,
        )
    )

    trade_limit = core.check_daily_limits(
        starting_equity=100_000,
        current_equity=100_000,
        daily_trade_count=5,
        consecutive_losses=0,
    )
    loss_limit = core.check_daily_limits(
        starting_equity=100_000,
        current_equity=100_000,
        daily_trade_count=1,
        consecutive_losses=3,
    )

    assert trade_limit.code == "DAILY_TRADE_LIMIT"
    assert loss_limit.code == "CONSECUTIVE_LOSS_LIMIT"


def test_equity_floor_and_portfolio_capacity() -> None:
    core = RiskCore(
        RiskConfig(
            equity_floor_pct=80,
            max_open_positions=3,
            max_total_risk_pct=4,
            risk_per_trade_pct=1,
        )
    )

    equity = core.check_equity_protection(
        initial_equity=100_000,
        current_equity=79_000,
    )
    positions = core.check_portfolio_capacity(
        open_positions=3,
        current_total_risk_pct=2,
    )
    total_risk = core.check_portfolio_capacity(
        open_positions=2,
        current_total_risk_pct=3.5,
    )

    assert equity.code == "EQUITY_FLOOR"
    assert positions.code == "MAX_OPEN_POSITIONS"
    assert total_risk.code == "MAX_TOTAL_RISK"


def test_full_trade_evaluation_and_report() -> None:
    core = RiskCore(
        RiskConfig(
            risk_per_trade_pct=1,
            min_stop_distance_pct=0.1,
        )
    )

    result = core.evaluate_new_trade(
        initial_equity=100_000,
        starting_equity=100_000,
        current_equity=99_000,
        daily_trade_count=2,
        consecutive_losses=1,
        open_positions=1,
        current_total_risk_pct=1,
        entry_price=100,
        stop_price=96,
        available_cash=50_000,
    )
    report = core.risk_report(
        initial_equity=100_000,
        starting_equity=100_000,
        current_equity=99_000,
        daily_trade_count=2,
        consecutive_losses=1,
        open_positions=1,
        current_total_risk_pct=1,
    )

    assert result["allowed"] is True
    assert result["stage"] == "approved"
    assert result["position"]["quantity"] > 0
    assert report["equity"]["allowed"] is True
    assert report["daily"]["allowed"] is True


def test_invalid_values_raise() -> None:
    core = RiskCore()

    with pytest.raises(ValueError):
        core.calculate_position_size(
            equity=0,
            entry_price=100,
            stop_price=95,
        )
