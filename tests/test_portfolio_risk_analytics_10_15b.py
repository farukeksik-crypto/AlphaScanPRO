from __future__ import annotations

import pytest

from engine.portfolio_risk_analytics import (
    StressScenario,
    build_portfolio_risk_report,
    recommend_risk_per_trade,
)


def test_empty_portfolio_is_low_risk():
    report = build_portfolio_risk_report([], equity=100_000)
    assert report.total_exposure == 0
    assert report.risk_level == "DÜŞÜK"
    assert report.recommended_risk_per_trade_pct == 1.0


def test_concentration_and_stop_risk_are_calculated():
    positions = [
        {"symbol": "AAA", "quantity": 100, "entry_price": 100, "current_price": 110, "stop_price": 95, "group": "BIST"},
        {"symbol": "BBB", "quantity": 50, "entry_price": 100, "current_price": 100, "stop_price": 90, "group": "BIST"},
    ]
    report = build_portfolio_risk_report(positions, equity=20_000)
    assert report.total_exposure == pytest.approx(16_000)
    assert report.total_stop_risk == pytest.approx(1_000)
    assert report.largest_symbol_pct == pytest.approx(55.0)
    assert report.concentration_hhi > 0.5
    assert report.risk_level in {"YÜKSEK", "KRİTİK"}


def test_stress_loss_uses_total_exposure():
    report = build_portfolio_risk_report(
        [{"symbol": "AAA", "quantity": 10, "entry_price": 100, "current_price": 100, "stop_price": 90}],
        equity=10_000,
        scenarios=[StressScenario("Test", -10)],
    )
    assert report.stress_results[0]["estimated_loss"] == pytest.approx(100)
    assert report.stress_results[0]["stressed_equity"] == pytest.approx(9_900)


def test_adaptive_risk_scaling():
    assert recommend_risk_per_trade(base_risk_pct=1, exposure_utilization_pct=20, stop_risk_utilization_pct=20) == 1
    assert recommend_risk_per_trade(base_risk_pct=1, exposure_utilization_pct=75, stop_risk_utilization_pct=20) == 0.5
    assert recommend_risk_per_trade(base_risk_pct=1, exposure_utilization_pct=101, stop_risk_utilization_pct=20) == 0


def test_invalid_equity_and_scenario_are_rejected():
    with pytest.raises(ValueError):
        build_portfolio_risk_report([], equity=0)
    with pytest.raises(ValueError):
        StressScenario("Yanlış", 5)
