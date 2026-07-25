from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from engine.ai.financial_models import FinancialPeriod


def _safe_divide(
    numerator: float | None,
    denominator: float | None,
    *,
    multiplier: float = 1.0,
) -> float | None:
    if numerator is None or denominator is None:
        return None

    if denominator == 0:
        return None

    return (numerator / denominator) * multiplier


@dataclass(slots=True)
class FinancialRatios:
    symbol: str
    period_end: str

    # Karlılık
    gross_margin_pct: float | None = None
    operating_margin_pct: float | None = None
    ebitda_margin_pct: float | None = None
    net_margin_pct: float | None = None
    roe_pct: float | None = None
    roa_pct: float | None = None

    # Likidite
    current_ratio: float | None = None
    quick_ratio: float | None = None
    cash_ratio: float | None = None

    # Borçluluk
    debt_to_equity: float | None = None
    debt_to_assets: float | None = None
    net_debt_to_ebitda: float | None = None

    # Nakit üretimi
    operating_cash_flow_margin_pct: float | None = None
    free_cash_flow_margin_pct: float | None = None
    cash_conversion_ratio: float | None = None

    # Değerleme
    price_to_earnings: float | None = None
    price_to_book: float | None = None
    enterprise_value: float | None = None
    enterprise_value_to_ebitda: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RatioEngine:
    def calculate(self, period: FinancialPeriod) -> FinancialRatios:
        total_debt = period.total_debt
        net_debt = period.net_debt

        enterprise_value = None
        if period.market_cap is not None:
            enterprise_value = (
                period.market_cap
                + (total_debt or 0.0)
                - (period.cash_and_equivalents or 0.0)
            )

        return FinancialRatios(
            symbol=period.symbol,
            period_end=period.period_end.isoformat(),

            gross_margin_pct=_safe_divide(
                period.gross_profit,
                period.revenue,
                multiplier=100.0,
            ),
            operating_margin_pct=_safe_divide(
                period.operating_profit,
                period.revenue,
                multiplier=100.0,
            ),
            ebitda_margin_pct=_safe_divide(
                period.ebitda,
                period.revenue,
                multiplier=100.0,
            ),
            net_margin_pct=_safe_divide(
                period.net_income,
                period.revenue,
                multiplier=100.0,
            ),
            roe_pct=_safe_divide(
                period.net_income,
                period.total_equity,
                multiplier=100.0,
            ),
            roa_pct=_safe_divide(
                period.net_income,
                period.total_assets,
                multiplier=100.0,
            ),

            current_ratio=_safe_divide(
                period.current_assets,
                period.current_liabilities,
            ),
            quick_ratio=_safe_divide(
                None
                if period.current_assets is None
                else period.current_assets - (period.inventories or 0.0),
                period.current_liabilities,
            ),
            cash_ratio=_safe_divide(
                period.cash_and_equivalents,
                period.current_liabilities,
            ),

            debt_to_equity=_safe_divide(
                total_debt,
                period.total_equity,
            ),
            debt_to_assets=_safe_divide(
                total_debt,
                period.total_assets,
            ),
            net_debt_to_ebitda=_safe_divide(
                net_debt,
                period.ebitda,
            ),

            operating_cash_flow_margin_pct=_safe_divide(
                period.operating_cash_flow,
                period.revenue,
                multiplier=100.0,
            ),
            free_cash_flow_margin_pct=_safe_divide(
                period.free_cash_flow,
                period.revenue,
                multiplier=100.0,
            ),
            cash_conversion_ratio=_safe_divide(
                period.operating_cash_flow,
                period.net_income,
            ),

            price_to_earnings=_safe_divide(
                period.market_cap,
                period.net_income,
            ),
            price_to_book=_safe_divide(
                period.market_cap,
                period.total_equity,
            ),
            enterprise_value=enterprise_value,
            enterprise_value_to_ebitda=_safe_divide(
                enterprise_value,
                period.ebitda,
            ),
        )