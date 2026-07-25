from __future__ import annotations

from engine.performance_center import build_performance_center_report


def row(pnl, score, *, risk="Orta", decision="AL ADAY", holding=120, mae=-1, mfe=2, trailing=0):
    return {
        "net_pnl": pnl,
        "entry_score": score,
        "exit_score": 50,
        "confirmations": 3,
        "holding_minutes": holding,
        "mfe_pct": mfe,
        "mae_pct": mae,
        "break_even_active": 0,
        "trailing_active": trailing,
        "closed_at": "2026-07-01 12:00:00",
        "metadata_json": '{"risk": "%s", "decision": "%s", "strategy_profile": "core"}' % (risk, decision),
    }


def test_empty_report_is_safe():
    report = build_performance_center_report([])
    assert report.trade_count == 0
    assert report.recommendations[0].severity == "BİLGİ"


def test_score_bands_and_metadata_segments():
    report = build_performance_center_report([row(10, 86), row(-5, 72, risk="Yüksek")], min_sample=2)
    assert {x.segment for x in report.score_bands} == {"85-89", "70-79"}
    assert {x.segment for x in report.risk_stats} == {"Orta", "Yüksek"}
    assert report.strategy_stats[0].segment == "core"


def test_winner_loser_comparison():
    report = build_performance_center_report([row(10, 90, mae=-0.5), row(-4, 70, mae=-3)])
    groups = {x.group: x for x in report.winner_loser_comparison}
    assert groups["Kazanan"].average_entry_score == 90
    assert groups["Kaybeden"].average_mae_pct == -3


def test_low_sample_does_not_recommend_filter_change():
    report = build_performance_center_report([row(1, 90)] * 3, min_sample=10)
    assert len(report.recommendations) == 1
    assert "filtre değiştirme" in report.recommendations[0].action


def test_weak_score_band_creates_controlled_warning():
    rows = [row(-10, 72) for _ in range(10)] + [row(15, 90) for _ in range(10)]
    report = build_performance_center_report(rows, min_sample=10)
    titles = [x.title for x in report.recommendations]
    assert any("70-79" in title and "zayıf" in title for title in titles)
    assert all("otomatik" in x.action or "test" in x.action or "devam" in x.action for x in report.recommendations)


def test_invalid_minimum_sample_rejected():
    try:
        build_performance_center_report([], min_sample=1)
    except ValueError:
        pass
    else:
        raise AssertionError("ValueError bekleniyordu")
