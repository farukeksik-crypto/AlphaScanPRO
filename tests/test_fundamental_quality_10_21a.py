from __future__ import annotations

import pandas as pd

from engine.fundamental_quality import build_financial_quality_report, metrics_frame


def _income(latest_revenue=120.0, previous_revenue=100.0, latest_profit=18.0, previous_profit=12.0):
    return pd.DataFrame(
        {
            "2025": [latest_revenue, latest_profit],
            "2024": [previous_revenue, previous_profit],
        },
        index=["Total Revenue", "Net Income"],
    )


def test_strong_company_receives_high_score_and_grade():
    report = build_financial_quality_report(
        "TEST.IS",
        "Test Güçlü",
        {
            "revenueGrowth": 0.28,
            "earningsGrowth": 0.42,
            "returnOnEquity": 0.31,
            "returnOnAssets": 0.16,
            "profitMargins": 0.22,
            "operatingMargins": 0.25,
            "debtToEquity": 30,
            "currentRatio": 2.1,
            "quickRatio": 1.8,
            "freeCashflow": 150_000_000,
            "trailingPE": 12,
            "priceToBook": 2.2,
        },
        income_statement=_income(),
    )
    assert report.overall_score is not None
    assert report.overall_score >= 80
    assert report.grade in {"A", "A+"}
    assert report.coverage_pct == 100.0
    assert report.positives


def test_missing_data_does_not_become_zero_score():
    report = build_financial_quality_report("EMPTY.IS", "Eksik Veri", {}, income_statement=pd.DataFrame())
    assert report.overall_score is None
    assert report.grade == "N/A"
    assert report.coverage_pct == 0.0
    assert "yeterli veri" in report.summary.lower()


def test_statement_growth_is_used_when_info_growth_missing():
    report = build_financial_quality_report(
        "TABLO.IS",
        "Tablo Şirketi",
        {"returnOnEquity": 0.20},
        income_statement=_income(latest_revenue=150, previous_revenue=100, latest_profit=30, previous_profit=10),
    )
    by_key = {metric.key: metric for metric in report.metrics}
    assert by_key["statement_revenue_growth"].value == 0.5
    assert by_key["statement_net_income_growth"].value == 2.0
    assert by_key["statement_revenue_growth"].score >= 90


def test_weak_balance_sheet_creates_caution():
    report = build_financial_quality_report(
        "RISK.IS",
        "Riskli Şirket",
        {
            "returnOnEquity": -0.05,
            "profitMargins": -0.10,
            "debtToEquity": 350,
            "currentRatio": 0.5,
            "freeCashflow": -10_000,
        },
    )
    assert report.overall_score is not None
    assert report.overall_score < 45
    assert report.cautions


def test_metrics_frame_contains_explainable_columns():
    report = build_financial_quality_report("TEST.IS", "Test", {"returnOnEquity": 0.2})
    frame = metrics_frame(report)
    assert {"Kategori", "Gösterge", "Değer", "Puan", "Durum", "Kaynak", "Açıklama"}.issubset(frame.columns)
    assert len(frame) == 14
