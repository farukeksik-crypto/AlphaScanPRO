from __future__ import annotations

from engine.adaptive_optimizer import AdaptiveOptimizer


def make_trades() -> list[dict]:
    trades = []
    for index in range(10):
        trades.append(
            {
                "status": "CLOSED",
                "pnl": 20 if index < 8 else -5,
                "ai_score": 82 + (index % 5),
                "adx": 26 + (index % 4),
                "rsi": 52 + (index % 5),
                "exit_reason": "TAKE_PROFIT",
            }
        )

    for index in range(10):
        trades.append(
            {
                "status": "CLOSED",
                "pnl": 5 if index < 4 else -15,
                "ai_score": 62 + (index % 5),
                "adx": 14 + (index % 3),
                "rsi": 35 + (index % 4),
                "exit_reason": "STOP_LOSS",
            }
        )

    trades.append(
        {
            "status": "OPEN",
            "pnl": None,
            "ai_score": 95,
            "adx": 40,
            "rsi": 60,
            "exit_reason": None,
        }
    )
    return trades


def test_score_band_analysis() -> None:
    optimizer = AdaptiveOptimizer()
    rows = optimizer.analyze_score_bands(make_trades())

    assert len(rows) >= 2
    best = max(rows, key=lambda row: row["expectancy"])
    assert best["band"].startswith("80")
    assert best["sample_size"] == 10


def test_ai_score_optimization() -> None:
    optimizer = AdaptiveOptimizer()
    suggestion = optimizer.optimize_ai_minimum_score(
        make_trades(),
        current_value=60,
        minimum_samples=5,
    )

    assert suggestion.parameter == "ai_minimum_trade_score"
    assert suggestion.suggested_value == 80
    assert suggestion.sample_size == 10
    assert suggestion.metric_value > 0


def test_adx_optimization() -> None:
    optimizer = AdaptiveOptimizer()
    suggestion = optimizer.optimize_adx_threshold(
        make_trades(),
        current_value=18,
        minimum_samples=5,
    )

    assert suggestion.parameter == "adx_threshold"
    assert suggestion.suggested_value == 25
    assert suggestion.confidence > 0


def test_rsi_optimization() -> None:
    optimizer = AdaptiveOptimizer()
    result = optimizer.optimize_rsi_range(
        make_trades(),
        current_min=42,
        current_max=65,
        minimum_samples=5,
    )

    assert result["rsi_min"].suggested_value == 50
    assert result["rsi_max"].suggested_value == 60


def test_exit_method_analysis_and_full_report() -> None:
    optimizer = AdaptiveOptimizer()
    exit_rows = optimizer.analyze_exit_methods(make_trades())
    report = optimizer.full_report(
        make_trades(),
        minimum_samples=5,
    )

    assert exit_rows[0]["exit_reason"] == "TAKE_PROFIT"
    assert "score_bands" in report
    assert "adx_analysis" in report
    assert "rsi_analysis" in report
    assert "exit_method_analysis" in report
    assert len(report["suggestions"]) == 4
