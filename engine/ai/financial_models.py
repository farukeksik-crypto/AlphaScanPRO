from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


def _to_float(value: Any) -> float | None:
    """Farklı kaynaklardan gelen sayısal değerleri güvenli biçimde dönüştürür."""
    if value is None:
        return None

    if isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()

    if not text or text.lower() in {"none", "nan", "null", "-", "n/a"}:
        return None

    text = (
        text.replace("₺", "")
        .replace("$", "")
        .replace("€", "")
        .replace("%", "")
        .replace(" ", "")
    )

    try:
        # Türkçe sayı biçimi: 1.234.567,89
        if "," in text and "." in text:
            text = text.replace(".", "").replace(",", ".")
        elif "," in text:
            text = text.replace(",", ".")

        return float(text)
    except (TypeError, ValueError):
        return None


@dataclass(slots=True)
class FinancialPeriod:
    symbol: str
    period_end: date
    currency: str = "TRY"
    period_type: str = "QUARTERLY"

    # Gelir tablosu
    revenue: float | None = None
    gross_profit: float | None = None
    operating_profit: float | None = None
    ebitda: float | None = None
    net_income: float | None = None
    finance_expense: float | None = None

    # Bilanço
    total_assets: float | None = None
    current_assets: float | None = None
    cash_and_equivalents: float | None = None
    inventories: float | None = None
    total_liabilities: float | None = None
    current_liabilities: float | None = None
    short_term_debt: float | None = None
    long_term_debt: float | None = None
    total_equity: float | None = None

    # Nakit akışı
    operating_cash_flow: float | None = None
    investing_cash_flow: float | None = None
    financing_cash_flow: float | None = None
    capital_expenditures: float | None = None
    free_cash_flow: float | None = None

    # Piyasa verileri
    market_cap: float | None = None
    share_price: float | None = None
    shares_outstanding: float | None = None

    # İzlenebilirlik
    source: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.symbol = self.symbol.strip().upper()
        self.currency = self.currency.strip().upper()
        self.period_type = self.period_type.strip().upper()

        numeric_fields = (
            "revenue",
            "gross_profit",
            "operating_profit",
            "ebitda",
            "net_income",
            "finance_expense",
            "total_assets",
            "current_assets",
            "cash_and_equivalents",
            "inventories",
            "total_liabilities",
            "current_liabilities",
            "short_term_debt",
            "long_term_debt",
            "total_equity",
            "operating_cash_flow",
            "investing_cash_flow",
            "financing_cash_flow",
            "capital_expenditures",
            "free_cash_flow",
            "market_cap",
            "share_price",
            "shares_outstanding",
        )

        for field_name in numeric_fields:
            setattr(self, field_name, _to_float(getattr(self, field_name)))

        if self.free_cash_flow is None:
            self.free_cash_flow = self.calculate_free_cash_flow()

    @property
    def total_debt(self) -> float | None:
        values = [
            value
            for value in (self.short_term_debt, self.long_term_debt)
            if value is not None
        ]

        if not values:
            return None

        return sum(values)

    @property
    def net_debt(self) -> float | None:
        if self.total_debt is None:
            return None

        return self.total_debt - (self.cash_and_equivalents or 0.0)

    def calculate_free_cash_flow(self) -> float | None:
        if self.operating_cash_flow is None:
            return None

        if self.capital_expenditures is None:
            return self.operating_cash_flow

        # Veri kaynağı yatırım harcamasını negatif veya pozitif verebilir.
        return self.operating_cash_flow - abs(self.capital_expenditures)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "period_end": self.period_end.isoformat(),
            "currency": self.currency,
            "period_type": self.period_type,
            "revenue": self.revenue,
            "gross_profit": self.gross_profit,
            "operating_profit": self.operating_profit,
            "ebitda": self.ebitda,
            "net_income": self.net_income,
            "finance_expense": self.finance_expense,
            "total_assets": self.total_assets,
            "current_assets": self.current_assets,
            "cash_and_equivalents": self.cash_and_equivalents,
            "inventories": self.inventories,
            "total_liabilities": self.total_liabilities,
            "current_liabilities": self.current_liabilities,
            "short_term_debt": self.short_term_debt,
            "long_term_debt": self.long_term_debt,
            "total_debt": self.total_debt,
            "net_debt": self.net_debt,
            "total_equity": self.total_equity,
            "operating_cash_flow": self.operating_cash_flow,
            "investing_cash_flow": self.investing_cash_flow,
            "financing_cash_flow": self.financing_cash_flow,
            "capital_expenditures": self.capital_expenditures,
            "free_cash_flow": self.free_cash_flow,
            "market_cap": self.market_cap,
            "share_price": self.share_price,
            "shares_outstanding": self.shares_outstanding,
            "source": self.source,
        }