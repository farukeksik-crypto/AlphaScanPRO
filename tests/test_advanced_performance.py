from __future__ import annotations

from engine.advanced_performance import AdvancedPerformanceEngine


EQUITY_CURVE = [
    {
        "timestamp": "2026-01-02T10:00:00+00:00",
        "equity": 1000.0,
        "initial_equity": 1000.0,
    },
    {
        "timestamp": "2026-01-03T10:00:00+00:00",
        "equity": 1050.0,
    },
    {
        "timestamp": "2026-01-04T10:00:00+00:00",
        "equity": 1020.0,
    },
    {
        "timestamp": "2026-02-02T10:00:00+00:00",
        "equity": 1080.0,
    },
    {
        "timestamp": "2026-02-03T10:00:00+00:00",
        "equity": 1120.0,
    },
    {
        "timestamp": "2026-03-02T10:00:00+00:00",
        "equity": 1100.0,
    },
    {
        "timestamp": "2026-03-03T10:00:00+00:00",
        "equity": 1200.0,
    },
]


def test_calculate_returns() -> None:
    engine = AdvancedPerformanceEngine()
    returns = engine.calculate_returns(EQUITY_CURVE)

    assert len(returns) == 7
    assert returns[0]["return_pct"] == 0.0
    assert round(returns[1]["return_pct"], 6) == 5.0
    assert returns[2]["return_pct"] < 0


def test_summary_metrics() -> None:
    engine = AdvancedPerformanceEngine()
    summary = engine.summarize(
        EQUITY_CURVE,
        periods_per_year=252,
        risk_free_rate_pct=0.0,
    )

    assert summary.total_periods == 6
    assert round(summary.cumulative_return_pct, 6) == 20.0
    assert summary.annualized_volatility_pct > 0
    assert summary.max_drawdown_pct > 0
    assert summary.best_period_return_pct > 0
    assert summary.worst_period_return_pct < 0
    assert summary.positive_periods == 4
    assert summary.negative_periods == 2


def test_rolling_returns() -> None:
    engine = AdvancedPerformanceEngine()
    rows = engine.rolling_returns(
        EQUITY_CURVE,
        window=2,
    )

    assert len(rows) == 5
    assert rows[0]["window"] == 2
    assert round(rows[0]["rolling_return_pct"], 6) == 2.0


def test_monthly_and_yearly_performance() -> None:
    engine = AdvancedPerformanceEngine()

    monthly = engine.monthly_performance(EQUITY_CURVE)
    yearly = engine.yearly_performance(EQUITY_CURVE)
    matrix = engine.monthly_matrix(EQUITY_CURVE)

    assert len(monthly) == 3
    assert monthly[0]["label"] == "2026-01"
    assert monthly[-1]["end_equity"] == 1200.0
    assert len(yearly) == 1
    assert yearly[0]["year"] == 2026
    assert "01" in matrix[2026]
    assert "03" in matrix[2026]


def test_full_report() -> None:
    engine = AdvancedPerformanceEngine()
    report = engine.full_report(
        EQUITY_CURVE,
        periods_per_year=252,
        rolling_window=2,
    )

    assert "summary" in report
    assert "period_returns" in report
    assert "rolling_returns" in report
    assert "monthly_performance" in report
    assert "yearly_performance" in report
    assert "monthly_matrix" in report
