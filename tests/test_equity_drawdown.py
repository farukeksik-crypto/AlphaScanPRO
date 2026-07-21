from __future__ import annotations

from engine.equity_drawdown import EquityDrawdownEngine


TRADES = [
    {
        "status": "CLOSED",
        "pnl": 100,
        "exit_time": "2026-07-20T10:00:00+00:00",
    },
    {
        "status": "CLOSED",
        "pnl": -40,
        "exit_time": "2026-07-20T11:00:00+00:00",
    },
    {
        "status": "CLOSED",
        "pnl": -80,
        "exit_time": "2026-07-21T09:00:00+00:00",
    },
    {
        "status": "CLOSED",
        "pnl": 50,
        "exit_time": "2026-07-21T12:00:00+00:00",
    },
    {
        "status": "CLOSED",
        "pnl": 100,
        "exit_time": "2026-07-22T15:00:00+00:00",
    },
]


def test_equity_curve() -> None:
    engine = EquityDrawdownEngine()
    curve = engine.build_equity_curve(
        TRADES,
        initial_equity=1000,
    )

    assert len(curve) == 5
    assert curve[0].equity == 1100
    assert curve[1].equity == 1060
    assert curve[2].equity == 980
    assert curve[-1].equity == 1130
    assert curve[2].drawdown_value == 120
    assert round(curve[2].drawdown_pct, 4) == round((120 / 1100) * 100, 4)


def test_drawdown_summary() -> None:
    engine = EquityDrawdownEngine()
    curve = engine.build_equity_curve(
        TRADES,
        initial_equity=1000,
    )
    summary = engine.summarize(
        curve,
        initial_equity=1000,
    )

    assert summary.initial_equity == 1000
    assert summary.final_equity == 1130
    assert summary.net_pnl == 130
    assert summary.max_equity == 1130
    assert summary.min_equity == 980
    assert summary.max_drawdown_value == 120
    assert summary.max_drawdown_duration == 3
    assert summary.current_drawdown_value == 0


def test_empty_summary() -> None:
    engine = EquityDrawdownEngine()
    summary = engine.summarize(
        [],
        initial_equity=5000,
    )

    assert summary.final_equity == 5000
    assert summary.net_pnl == 0
    assert summary.max_drawdown_pct == 0


def test_daily_snapshots() -> None:
    engine = EquityDrawdownEngine()
    curve = engine.build_equity_curve(
        TRADES,
        initial_equity=1000,
    )
    snapshots = engine.daily_snapshots(curve)

    assert len(snapshots) == 3
    assert snapshots[0]["date"] == "2026-07-20"
    assert snapshots[0]["equity"] == 1060
    assert snapshots[1]["equity"] == 1030
    assert snapshots[2]["equity"] == 1130


def test_full_report_and_export(tmp_path) -> None:
    engine = EquityDrawdownEngine()
    report = engine.full_report(
        TRADES,
        initial_equity=1000,
    )
    output = engine.export_json(
        report,
        tmp_path / "equity_report.json",
    )

    assert "summary" in report
    assert "equity_curve" in report
    assert "daily_snapshots" in report
    assert output.exists()
    assert '"final_equity": 1130.0' in output.read_text(encoding="utf-8")
