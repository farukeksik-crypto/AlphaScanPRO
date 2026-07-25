from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import StrEnum
from typing import Any


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()

    if not text or text.lower() in {
        "none",
        "null",
        "nan",
        "n/a",
        "-",
    }:
        return None

    text = (
        text.replace("₺", "")
        .replace("$", "")
        .replace("€", "")
        .replace("%", "")
        .replace(" ", "")
    )

    try:
        if "," in text and "." in text:
            text = text.replace(".", "").replace(",", ".")
        elif "," in text:
            text = text.replace(",", ".")

        return float(text)
    except (TypeError, ValueError):
        return None


class EventCategory(StrEnum):
    FINANCIAL = "FINANCIAL"
    INVESTMENT = "INVESTMENT"
    CONTRACT = "CONTRACT"
    EXPORT = "EXPORT"
    FX_RISK = "FX_RISK"
    DEBT = "DEBT"
    CAPITAL = "CAPITAL"
    DIVIDEND = "DIVIDEND"
    BUYBACK = "BUYBACK"
    INSIDER_TRADE = "INSIDER_TRADE"
    FUND_FLOW = "FUND_FLOW"
    LEGAL = "LEGAL"
    CONCORDAT = "CONCORDAT"
    BANKRUPTCY = "BANKRUPTCY"
    REGULATORY = "REGULATORY"
    MANAGEMENT = "MANAGEMENT"
    AUDIT = "AUDIT"
    OPERATIONAL = "OPERATIONAL"
    OTHER = "OTHER"


class ImpactLevel(StrEnum):
    VERY_POSITIVE = "VERY_POSITIVE"
    POSITIVE = "POSITIVE"
    NEUTRAL = "NEUTRAL"
    NEGATIVE = "NEGATIVE"
    VERY_NEGATIVE = "VERY_NEGATIVE"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


class DataQuality(StrEnum):
    VERIFIED = "VERIFIED"
    REPORTED = "REPORTED"
    ESTIMATED = "ESTIMATED"
    INFERRED = "INFERRED"
    INCOMPLETE = "INCOMPLETE"


@dataclass(slots=True)
class CurrencyPosition:
    currency: str

    financial_assets: float | None = None
    financial_liabilities: float | None = None

    trade_receivables: float | None = None
    trade_payables: float | None = None

    cash: float | None = None
    bank_loans: float | None = None
    lease_liabilities: float | None = None
    bond_liabilities: float | None = None

    derivative_assets: float | None = None
    derivative_liabilities: float | None = None

    expected_export_revenue: float | None = None
    expected_import_cost: float | None = None

    source: str | None = None
    quality: DataQuality = DataQuality.REPORTED

    def __post_init__(self) -> None:
        self.currency = self.currency.strip().upper()

        numeric_fields = (
            "financial_assets",
            "financial_liabilities",
            "trade_receivables",
            "trade_payables",
            "cash",
            "bank_loans",
            "lease_liabilities",
            "bond_liabilities",
            "derivative_assets",
            "derivative_liabilities",
            "expected_export_revenue",
            "expected_import_cost",
        )

        for field_name in numeric_fields:
            setattr(self, field_name, _to_float(getattr(self, field_name)))

    @property
    def total_assets(self) -> float | None:
        values = (
            self.financial_assets,
            self.trade_receivables,
            self.cash,
            self.derivative_assets,
        )

        available = [value for value in values if value is not None]
        return sum(available) if available else None

    @property
    def total_liabilities(self) -> float | None:
        values = (
            self.financial_liabilities,
            self.trade_payables,
            self.bank_loans,
            self.lease_liabilities,
            self.bond_liabilities,
            self.derivative_liabilities,
        )

        available = [value for value in values if value is not None]
        return sum(available) if available else None

    @property
    def net_position(self) -> float | None:
        if self.total_assets is None and self.total_liabilities is None:
            return None

        return (self.total_assets or 0.0) - (
            self.total_liabilities or 0.0
        )

    @property
    def natural_hedge_amount(self) -> float | None:
        if (
            self.expected_export_revenue is None
            and self.expected_import_cost is None
        ):
            return None

        return (self.expected_export_revenue or 0.0) - (
            self.expected_import_cost or 0.0
        )

    @property
    def adjusted_net_position(self) -> float | None:
        if self.net_position is None and self.natural_hedge_amount is None:
            return None

        return (self.net_position or 0.0) + (
            self.natural_hedge_amount or 0.0
        )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["quality"] = self.quality.value
        result["total_assets"] = self.total_assets
        result["total_liabilities"] = self.total_liabilities
        result["net_position"] = self.net_position
        result["natural_hedge_amount"] = self.natural_hedge_amount
        result["adjusted_net_position"] = self.adjusted_net_position
        return result


@dataclass(slots=True)
class ExportProfile:
    symbol: str
    period_end: date

    total_revenue: float | None = None
    domestic_revenue: float | None = None
    export_revenue: float | None = None

    europe_revenue: float | None = None
    middle_east_revenue: float | None = None
    asia_revenue: float | None = None
    america_revenue: float | None = None
    africa_revenue: float | None = None
    other_foreign_revenue: float | None = None

    export_currencies: list[str] = field(default_factory=list)
    main_export_countries: list[str] = field(default_factory=list)

    imported_input_cost: float | None = None
    export_order_backlog: float | None = None

    source: str | None = None
    quality: DataQuality = DataQuality.REPORTED

    def __post_init__(self) -> None:
        self.symbol = self.symbol.strip().upper()

        numeric_fields = (
            "total_revenue",
            "domestic_revenue",
            "export_revenue",
            "europe_revenue",
            "middle_east_revenue",
            "asia_revenue",
            "america_revenue",
            "africa_revenue",
            "other_foreign_revenue",
            "imported_input_cost",
            "export_order_backlog",
        )

        for field_name in numeric_fields:
            setattr(self, field_name, _to_float(getattr(self, field_name)))

        self.export_currencies = sorted(
            {
                str(currency).strip().upper()
                for currency in self.export_currencies
                if str(currency).strip()
            }
        )

        self.main_export_countries = sorted(
            {
                str(country).strip()
                for country in self.main_export_countries
                if str(country).strip()
            }
        )

    @property
    def export_ratio_pct(self) -> float | None:
        if (
            self.export_revenue is None
            or self.total_revenue in (None, 0)
        ):
            return None

        return (self.export_revenue / self.total_revenue) * 100.0

    @property
    def import_dependency_pct(self) -> float | None:
        if (
            self.imported_input_cost is None
            or self.total_revenue in (None, 0)
        ):
            return None

        return (self.imported_input_cost / self.total_revenue) * 100.0

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["period_end"] = self.period_end.isoformat()
        result["quality"] = self.quality.value
        result["export_ratio_pct"] = self.export_ratio_pct
        result["import_dependency_pct"] = self.import_dependency_pct
        return result


@dataclass(slots=True)
class CompanyEvent:
    symbol: str
    event_time: datetime
    category: EventCategory
    title: str

    source_name: str = "KAP"
    source_id: str | None = None
    source_url: str | None = None

    summary: str | None = None
    raw_text: str | None = None

    impact: ImpactLevel = ImpactLevel.UNKNOWN
    importance_score: float | None = None
    confidence_score: float | None = None

    related_amount: float | None = None
    related_currency: str | None = None

    process_key: str | None = None
    process_status: str | None = None
    supersedes_source_id: str | None = None

    quality: DataQuality = DataQuality.VERIFIED
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        self.symbol = self.symbol.strip().upper()
        self.title = self.title.strip()

        self.related_amount = _to_float(self.related_amount)
        self.importance_score = _to_float(self.importance_score)
        self.confidence_score = _to_float(self.confidence_score)

        if self.related_currency:
            self.related_currency = (
                self.related_currency.strip().upper()
            )

        self.tags = sorted(
            {
                str(tag).strip().lower()
                for tag in self.tags
                if str(tag).strip()
            }
        )

        if self.importance_score is not None:
            self.importance_score = max(
                0.0,
                min(100.0, self.importance_score),
            )

        if self.confidence_score is not None:
            self.confidence_score = max(
                0.0,
                min(100.0, self.confidence_score),
            )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["event_time"] = self.event_time.isoformat()
        result["created_at"] = self.created_at.isoformat()
        result["category"] = self.category.value
        result["impact"] = self.impact.value
        result["quality"] = self.quality.value
        return result