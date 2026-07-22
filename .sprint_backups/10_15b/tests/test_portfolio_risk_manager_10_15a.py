from __future__ import annotations

import pytest

from engine.portfolio_risk_manager import (
    PortfolioDecision,
    PortfolioPosition,
    PortfolioRiskConfig,
    PortfolioRiskManager,
    PortfolioRuntimeBridge,
)


def make_manager(**kwargs) -> PortfolioRiskManager:
    values = {
        "initial_equity": 100_000,
        "max_open_positions": 5,
        "max_total_exposure_pct": 75,
        "max_symbol_exposure_pct": 25,
        "max_group_exposure_pct": 40,
        "max_total_risk_pct": 5,
        "max_risk_per_trade_pct": 1,
        "daily_loss_limit_pct": 3,
        "minimum_position_value": 100,
    }
    values.update(kwargs)
    return PortfolioRiskManager(PortfolioRiskConfig(**values))


def test_risk_quantity_uses_equity_and_stop_distance() -> None:
    manager = make_manager()
    quantity, budget = manager.calculate_risk_quantity(
        entry_price=100,
        stop_price=95,
    )
    assert budget == pytest.approx(1_000)
    assert quantity == pytest.approx(200)


def test_risk_quantity_rejects_zero_stop_distance() -> None:
    with pytest.raises(ValueError, match="Stop mesafesi"):
        make_manager().calculate_risk_quantity(entry_price=100, stop_price=100)


def test_risk_quantity_cannot_exceed_trade_limit() -> None:
    with pytest.raises(ValueError, match="risk_pct"):
        make_manager().calculate_risk_quantity(
            entry_price=100,
            stop_price=95,
            risk_pct=2,
        )


def test_plan_trade_sizes_then_applies_exposure_limit() -> None:
    manager = make_manager(max_symbol_exposure_pct=10)
    plan = manager.plan_trade(
        symbol="BTC/USDT",
        side="BUY",
        entry_price=100,
        stop_price=95,
    )
    assert plan.raw_quantity == pytest.approx(200)
    assert plan.evaluation.decision == PortfolioDecision.REDUCED
    assert plan.approved_quantity == pytest.approx(100)
    assert plan.to_dict()["approved"] is True


def test_plan_trade_with_requested_quantity() -> None:
    plan = make_manager().plan_trade(
        symbol="ETHUSDT",
        side="BUY",
        entry_price=100,
        stop_price=95,
        requested_quantity=50,
    )
    assert plan.raw_quantity == 50
    assert plan.risk_budget == pytest.approx(250)
    assert plan.evaluation.decision == PortfolioDecision.APPROVED


def test_set_account_state_blocks_daily_loss() -> None:
    manager = make_manager()
    manager.set_account_state(
        equity=97_000,
        day_start_equity=100_000,
        realized_pnl_today=-3_000,
    )
    plan = manager.plan_trade(
        symbol="BTCUSDT",
        side="BUY",
        entry_price=100,
        stop_price=95,
    )
    assert plan.approved is False
    assert plan.evaluation.reason.value == "DAILY_LOSS_LIMIT"


def test_sync_positions_populates_portfolio_metrics() -> None:
    manager = make_manager()
    manager.sync_positions(
        [
            PortfolioPosition(
                symbol="BTC/USDT",
                quantity=100,
                entry_price=100,
                current_price=110,
                stop_price=95,
                group="crypto",
            )
        ]
    )
    metrics = manager.metrics()
    assert metrics["open_position_count"] == 1
    assert metrics["total_exposure"] == pytest.approx(11_000)
    assert metrics["total_risk"] == pytest.approx(500)


def test_sync_positions_rejects_duplicate_symbol() -> None:
    manager = make_manager()
    positions = [
        PortfolioPosition("BTCUSDT", 1, 100, 100, 95),
        PortfolioPosition("BTC/USDT", 1, 100, 100, 95),
    ]
    with pytest.raises(ValueError, match="Tekrarlanan"):
        manager.sync_positions(positions)


def test_dashboard_contains_limits_and_utilization() -> None:
    dashboard = make_manager().dashboard()
    assert dashboard["limits"]["max_open_positions"] == 5
    assert set(dashboard["utilization"]) == {
        "exposure",
        "risk",
        "positions",
        "daily_loss",
    }


def test_runtime_bridge_can_plan_execution() -> None:
    bridge = PortfolioRuntimeBridge(make_manager())
    plan = bridge.plan_execution(
        symbol="SOLUSDT",
        side="BUY",
        price=50,
        stop_price=45,
        risk_pct=0.5,
    )
    assert plan.approved is True
    assert plan.risk_budget == pytest.approx(500)
    assert plan.approved_quantity == pytest.approx(100)
