from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Iterable, Mapping

import pandas as pd


@dataclass(frozen=True)
class MetricAssessment:
    key: str
    label: str
    category: str
    value: float | None
    display_value: str
    score: float | None
    status: str
    explanation: str
    source: str


@dataclass(frozen=True)
class CategoryAssessment:
    key: str
    label: str
    score: float | None
    available_metrics: int
    total_metrics: int


@dataclass(frozen=True)
class FinancialQualityReport:
    symbol: str
    company_name: str
    overall_score: float | None
    grade: str
    coverage_pct: float
    categories: tuple[CategoryAssessment, ...]
    metrics: tuple[MetricAssessment, ...]
    positives: tuple[str, ...] = field(default_factory=tuple)
    cautions: tuple[str, ...] = field(default_factory=tuple)
    summary: str = ""


CATEGORY_LABELS = {
    "growth": "Büyüme",
    "profitability": "Kârlılık",
    "balance_sheet": "Finansal Yapı",
    "cash_flow": "Nakit ve Likidite",
    "valuation": "Değerleme",
}

CATEGORY_WEIGHTS = {
    "growth": 0.22,
    "profitability": 0.30,
    "balance_sheet": 0.22,
    "cash_flow": 0.16,
    "valuation": 0.10,
}


_INFO_METRICS = (
    # key, label, category, info aliases, formatter, scoring thresholds, direction
    ("revenue_growth", "Gelir Büyümesi", "growth", ("revenueGrowth",), "percent", (-0.10, 0.00, 0.10, 0.25), "higher"),
    ("earnings_growth", "Kâr Büyümesi", "growth", ("earningsGrowth", "earningsQuarterlyGrowth"), "percent", (-0.20, 0.00, 0.15, 0.35), "higher"),
    ("roe", "Özsermaye Kârlılığı (ROE)", "profitability", ("returnOnEquity",), "percent", (0.00, 0.08, 0.18, 0.30), "higher"),
    ("roa", "Aktif Kârlılığı (ROA)", "profitability", ("returnOnAssets",), "percent", (0.00, 0.04, 0.10, 0.18), "higher"),
    ("net_margin", "Net Kâr Marjı", "profitability", ("profitMargins",), "percent", (0.00, 0.05, 0.12, 0.25), "higher"),
    ("operating_margin", "Faaliyet Marjı", "profitability", ("operatingMargins",), "percent", (0.00, 0.06, 0.15, 0.28), "higher"),
    ("debt_to_equity", "Borç / Özsermaye", "balance_sheet", ("debtToEquity",), "ratio", (250.0, 150.0, 80.0, 35.0), "lower"),
    ("current_ratio", "Cari Oran", "cash_flow", ("currentRatio",), "ratio", (0.70, 1.00, 1.50, 2.00), "higher"),
    ("quick_ratio", "Likidite Oranı", "cash_flow", ("quickRatio",), "ratio", (0.50, 0.80, 1.20, 1.70), "higher"),
    ("free_cashflow", "Serbest Nakit Akışı", "cash_flow", ("freeCashflow",), "amount", (-1.0, 0.0, 1.0, 2.0), "positive_amount"),
    ("pe", "F/K", "valuation", ("trailingPE", "forwardPE"), "ratio", (45.0, 30.0, 18.0, 10.0), "lower_positive"),
    ("pb", "PD/DD", "valuation", ("priceToBook",), "ratio", (8.0, 5.0, 3.0, 1.5), "lower_positive"),
)


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _first_info_value(info: Mapping[str, Any], aliases: Iterable[str]) -> tuple[float | None, str | None]:
    for alias in aliases:
        value = _finite(info.get(alias))
        if value is not None:
            return value, alias
    return None, None


def _format_value(value: float | None, kind: str) -> str:
    if value is None:
        return "—"
    if kind == "percent":
        return f"%{value * 100:,.2f}"
    if kind == "amount":
        absolute = abs(value)
        if absolute >= 1_000_000_000:
            return f"{value / 1_000_000_000:,.2f} Mr"
        if absolute >= 1_000_000:
            return f"{value / 1_000_000:,.2f} Mn"
        return f"{value:,.2f}"
    return f"{value:,.2f}"


def _bucket_score(value: float, thresholds: tuple[float, float, float, float], direction: str) -> float:
    worst, weak, good, excellent = thresholds
    if direction == "higher":
        if value < worst:
            return 10.0
        if value < weak:
            return 30.0
        if value < good:
            return 55.0
        if value < excellent:
            return 78.0
        return 95.0
    if direction == "lower":
        if value > worst:
            return 10.0
        if value > weak:
            return 35.0
        if value > good:
            return 60.0
        if value > excellent:
            return 80.0
        return 95.0
    if direction == "lower_positive":
        if value <= 0:
            return 20.0
        if value > worst:
            return 25.0
        if value > weak:
            return 45.0
        if value > good:
            return 65.0
        if value > excellent:
            return 82.0
        return 92.0
    if direction == "positive_amount":
        return 80.0 if value > 0 else 20.0
    raise ValueError(f"Bilinmeyen puan yönü: {direction}")


def _status(score: float | None) -> str:
    if score is None:
        return "Veri Yok"
    if score >= 80:
        return "Güçlü"
    if score >= 60:
        return "Olumlu"
    if score >= 40:
        return "Nötr"
    return "Zayıf"


def _explanation(label: str, display: str, score: float | None, direction: str) -> str:
    if score is None:
        return f"{label} için kullanılabilir veri bulunamadı."
    status = _status(score).lower()
    if direction in {"lower", "lower_positive"}:
        return f"{label} {display}; düşük değer tercih edilen bu ölçütte görünüm {status}."
    if direction == "positive_amount":
        return f"{label} {display}; nakit üretimi görünümü {status}."
    return f"{label} {display}; görünüm {status}."


def _statement_row(frame: pd.DataFrame | None, aliases: Iterable[str]) -> pd.Series | None:
    if frame is None or frame.empty:
        return None
    aliases_lower = tuple(alias.lower() for alias in aliases)
    for index in frame.index:
        text = str(index).lower()
        if any(alias in text for alias in aliases_lower):
            row = pd.to_numeric(frame.loc[index], errors="coerce").dropna()
            if not row.empty:
                return row
    return None


def _latest_growth(frame: pd.DataFrame | None, aliases: Iterable[str]) -> float | None:
    row = _statement_row(frame, aliases)
    if row is None or len(row) < 2:
        return None
    # yfinance tabloları genellikle en güncel dönem önce olacak şekilde gelir.
    latest, previous = _finite(row.iloc[0]), _finite(row.iloc[1])
    if latest is None or previous in (None, 0):
        return None
    return (latest - previous) / abs(previous)


def _statement_metric(
    key: str,
    label: str,
    category: str,
    value: float | None,
    source: str,
    thresholds: tuple[float, float, float, float],
) -> MetricAssessment:
    score = _bucket_score(value, thresholds, "higher") if value is not None else None
    display = _format_value(value, "percent")
    return MetricAssessment(
        key=key,
        label=label,
        category=category,
        value=value,
        display_value=display,
        score=score,
        status=_status(score),
        explanation=_explanation(label, display, score, "higher"),
        source=source,
    )


def _grade(score: float | None) -> str:
    if score is None:
        return "N/A"
    if score >= 90:
        return "A+"
    if score >= 82:
        return "A"
    if score >= 74:
        return "B+"
    if score >= 66:
        return "B"
    if score >= 58:
        return "C+"
    if score >= 50:
        return "C"
    if score >= 40:
        return "D"
    return "E"


def build_financial_quality_report(
    symbol: str,
    company_name: str,
    info: Mapping[str, Any] | None,
    income_statement: pd.DataFrame | None = None,
    balance_sheet: pd.DataFrame | None = None,
    cashflow: pd.DataFrame | None = None,
) -> FinancialQualityReport:
    """Yahoo/KAP benzeri ham verilerden açıklanabilir finansal kalite raporu üretir.

    Eksik veriler sıfır puan sayılmaz; kapsama oranında görünür ve yalnızca mevcut
    ölçütler kategori/sonuç puanına katılır.
    """
    del balance_sheet, cashflow  # Gelecek sprintlerde doğrudan kalem analizi için ayrıldı.
    info = info or {}
    metrics: list[MetricAssessment] = []

    for key, label, category, aliases, formatter, thresholds, direction in _INFO_METRICS:
        value, source_key = _first_info_value(info, aliases)
        score = _bucket_score(value, thresholds, direction) if value is not None else None
        display = _format_value(value, formatter)
        metrics.append(
            MetricAssessment(
                key=key,
                label=label,
                category=category,
                value=value,
                display_value=display,
                score=score,
                status=_status(score),
                explanation=_explanation(label, display, score, direction),
                source=f"Yahoo Finance / {source_key}" if source_key else "Yahoo Finance",
            )
        )

    # Info alanı eksik olduğunda finansal tablo dönem değişimini ek ölçüt olarak kullan.
    revenue_statement_growth = _latest_growth(
        income_statement,
        ("total revenue", "operating revenue", "revenue", "hasılat", "satış gelirleri"),
    )
    net_income_statement_growth = _latest_growth(
        income_statement,
        ("net income", "net income common stockholders", "net dönem karı", "dönem karı"),
    )
    metrics.extend(
        [
            _statement_metric(
                "statement_revenue_growth",
                "Tablo Bazlı Gelir Değişimi",
                "growth",
                revenue_statement_growth,
                "Gelir tablosu / son iki dönem",
                (-0.10, 0.00, 0.10, 0.25),
            ),
            _statement_metric(
                "statement_net_income_growth",
                "Tablo Bazlı Net Kâr Değişimi",
                "growth",
                net_income_statement_growth,
                "Gelir tablosu / son iki dönem",
                (-0.20, 0.00, 0.15, 0.35),
            ),
        ]
    )

    categories: list[CategoryAssessment] = []
    weighted_total = 0.0
    available_weight = 0.0
    for category, label in CATEGORY_LABELS.items():
        category_metrics = [metric for metric in metrics if metric.category == category]
        scores = [metric.score for metric in category_metrics if metric.score is not None]
        category_score = sum(scores) / len(scores) if scores else None
        categories.append(
            CategoryAssessment(
                key=category,
                label=label,
                score=round(category_score, 2) if category_score is not None else None,
                available_metrics=len(scores),
                total_metrics=len(category_metrics),
            )
        )
        if category_score is not None:
            weight = CATEGORY_WEIGHTS[category]
            weighted_total += category_score * weight
            available_weight += weight

    overall = weighted_total / available_weight if available_weight else None
    overall = round(overall, 2) if overall is not None else None
    available_count = sum(metric.score is not None for metric in metrics)
    coverage = round(100.0 * available_count / len(metrics), 1) if metrics else 0.0

    ranked = sorted((metric for metric in metrics if metric.score is not None), key=lambda item: item.score or 0)
    positives = tuple(metric.explanation for metric in reversed(ranked[-3:]) if (metric.score or 0) >= 70)
    cautions = tuple(metric.explanation for metric in ranked[:3] if (metric.score or 0) < 45)

    if overall is None:
        summary = "Finansal kalite puanı üretmek için yeterli veri bulunamadı."
    else:
        strongest = max((item for item in categories if item.score is not None), key=lambda item: item.score, default=None)
        weakest = min((item for item in categories if item.score is not None), key=lambda item: item.score, default=None)
        summary = (
            f"{company_name} için finansal kalite puanı {overall:.1f}/100 ({_grade(overall)}). "
            f"Veri kapsama oranı %{coverage:.1f}."
        )
        if strongest and weakest and strongest.key != weakest.key:
            summary += f" En güçlü alan {strongest.label}; en dikkat gerektiren alan {weakest.label}."

    return FinancialQualityReport(
        symbol=symbol,
        company_name=company_name,
        overall_score=overall,
        grade=_grade(overall),
        coverage_pct=coverage,
        categories=tuple(categories),
        metrics=tuple(metrics),
        positives=positives,
        cautions=cautions,
        summary=summary,
    )


def metrics_frame(report: FinancialQualityReport) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Kategori": CATEGORY_LABELS.get(metric.category, metric.category),
                "Gösterge": metric.label,
                "Değer": metric.display_value,
                "Puan": round(metric.score, 1) if metric.score is not None else None,
                "Durum": metric.status,
                "Kaynak": metric.source,
                "Açıklama": metric.explanation,
            }
            for metric in report.metrics
        ]
    )
