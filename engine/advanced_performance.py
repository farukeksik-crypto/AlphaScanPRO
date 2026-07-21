from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from statistics import mean, pstdev
from typing import Any, Iterable


@dataclass
class AdvancedPerformanceSummary:
    total_periods: int
    cumulative_return_pct: float
    annualized_return_pct: float
    cagr_pct: float
    annualized_volatility_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown_pct: float
    best_period_return_pct: float
    worst_period_return_pct: float
    positive_periods: int
    negative_periods: int
    flat_periods: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AdvancedPerformanceEngine:
    def calculate_returns(
        self,
        equity_curve: Iterable[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        points = sorted(
            [dict(point) for point in equity_curve],
            key=lambda item: str(item.get("timestamp") or ""),
        )

        returns: list[dict[str, Any]] = []
        previous_equity: float | None = None

        for point in points:
            equity = float(point.get("equity") or 0.0)
            timestamp = str(point.get("timestamp") or "")

            if previous_equity is None or previous_equity == 0:
                return_pct = 0.0
            else:
                return_pct = ((equity / previous_equity) - 1.0) * 100.0

            returns.append(
                {
                    "timestamp": timestamp,
                    "equity": round(equity, 8),
                    "return_pct": round(return_pct, 8),
                }
            )
            previous_equity = equity

        return returns

    def summarize(
        self,
        equity_curve: Iterable[dict[str, Any]],
        *,
        periods_per_year: int = 252,
        risk_free_rate_pct: float = 0.0,
        max_drawdown_pct: float | None = None,
    ) -> AdvancedPerformanceSummary:
        points = sorted(
            [dict(point) for point in equity_curve],
            key=lambda item: str(item.get("timestamp") or ""),
        )

        if not points:
            return AdvancedPerformanceSummary(
                total_periods=0,
                cumulative_return_pct=0.0,
                annualized_return_pct=0.0,
                cagr_pct=0.0,
                annualized_volatility_pct=0.0,
                sharpe_ratio=0.0,
                sortino_ratio=0.0,
                calmar_ratio=0.0,
                max_drawdown_pct=0.0,
                best_period_return_pct=0.0,
                worst_period_return_pct=0.0,
                positive_periods=0,
                negative_periods=0,
                flat_periods=0,
            )

        equities = [float(point.get("equity") or 0.0) for point in points]
        initial_equity = float(
            points[0].get("initial_equity")
            or points[0].get("starting_equity")
            or equities[0]
        )
        final_equity = equities[-1]

        periodic = self.calculate_returns(points)
        periodic_returns_pct = [
            float(item["return_pct"])
            for item in periodic[1:]
        ]
        periodic_returns_decimal = [
            value / 100.0
            for value in periodic_returns_pct
        ]

        cumulative_return_pct = (
            ((final_equity / initial_equity) - 1.0) * 100.0
            if initial_equity != 0
            else 0.0
        )

        total_periods = len(periodic_returns_decimal)
        annualized_return_pct = self._annualized_return(
            cumulative_return_pct,
            total_periods,
            periods_per_year,
        )
        cagr_pct = annualized_return_pct

        volatility_pct = self._annualized_volatility(
            periodic_returns_decimal,
            periods_per_year,
        )

        sharpe = self._sharpe_ratio(
            periodic_returns_decimal,
            periods_per_year,
            risk_free_rate_pct,
        )
        sortino = self._sortino_ratio(
            periodic_returns_decimal,
            periods_per_year,
            risk_free_rate_pct,
        )

        calculated_mdd = (
            float(max_drawdown_pct)
            if max_drawdown_pct is not None
            else self._max_drawdown_pct(equities)
        )
        calmar = (
            annualized_return_pct / calculated_mdd
            if calculated_mdd > 0
            else 0.0
        )

        positive = sum(value > 0 for value in periodic_returns_pct)
        negative = sum(value < 0 for value in periodic_returns_pct)
        flat = sum(value == 0 for value in periodic_returns_pct)

        return AdvancedPerformanceSummary(
            total_periods=total_periods,
            cumulative_return_pct=round(cumulative_return_pct, 8),
            annualized_return_pct=round(annualized_return_pct, 8),
            cagr_pct=round(cagr_pct, 8),
            annualized_volatility_pct=round(volatility_pct, 8),
            sharpe_ratio=round(sharpe, 8),
            sortino_ratio=round(sortino, 8),
            calmar_ratio=round(calmar, 8),
            max_drawdown_pct=round(calculated_mdd, 8),
            best_period_return_pct=round(
                max(periodic_returns_pct) if periodic_returns_pct else 0.0,
                8,
            ),
            worst_period_return_pct=round(
                min(periodic_returns_pct) if periodic_returns_pct else 0.0,
                8,
            ),
            positive_periods=positive,
            negative_periods=negative,
            flat_periods=flat,
        )

    def rolling_returns(
        self,
        equity_curve: Iterable[dict[str, Any]],
        *,
        window: int = 20,
    ) -> list[dict[str, Any]]:
        if window <= 0:
            raise ValueError("window 0'dan büyük olmalıdır.")

        points = sorted(
            [dict(point) for point in equity_curve],
            key=lambda item: str(item.get("timestamp") or ""),
        )

        output: list[dict[str, Any]] = []
        for index in range(window, len(points)):
            start_equity = float(points[index - window].get("equity") or 0.0)
            end_equity = float(points[index].get("equity") or 0.0)
            value = (
                ((end_equity / start_equity) - 1.0) * 100.0
                if start_equity != 0
                else 0.0
            )
            output.append(
                {
                    "timestamp": str(points[index].get("timestamp") or ""),
                    "window": window,
                    "rolling_return_pct": round(value, 8),
                }
            )

        return output

    def monthly_performance(
        self,
        equity_curve: Iterable[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        points = sorted(
            [dict(point) for point in equity_curve],
            key=lambda item: str(item.get("timestamp") or ""),
        )

        buckets: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)

        for point in points:
            parsed = self._parse_timestamp(str(point.get("timestamp") or ""))
            if parsed is None:
                continue
            buckets[(parsed.year, parsed.month)].append(point)

        rows: list[dict[str, Any]] = []
        previous_close: float | None = None

        for year_month in sorted(buckets):
            month_points = buckets[year_month]
            month_end = float(month_points[-1].get("equity") or 0.0)

            if previous_close is None:
                month_start = float(month_points[0].get("equity") or 0.0)
            else:
                month_start = previous_close

            return_pct = (
                ((month_end / month_start) - 1.0) * 100.0
                if month_start != 0
                else 0.0
            )

            rows.append(
                {
                    "year": year_month[0],
                    "month": year_month[1],
                    "label": f"{year_month[0]:04d}-{year_month[1]:02d}",
                    "start_equity": round(month_start, 8),
                    "end_equity": round(month_end, 8),
                    "return_pct": round(return_pct, 8),
                }
            )
            previous_close = month_end

        return rows

    def yearly_performance(
        self,
        equity_curve: Iterable[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        monthly = self.monthly_performance(equity_curve)
        grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)

        for row in monthly:
            grouped[int(row["year"])].append(row)

        output: list[dict[str, Any]] = []
        for year in sorted(grouped):
            rows = grouped[year]
            start_equity = float(rows[0]["start_equity"])
            end_equity = float(rows[-1]["end_equity"])
            return_pct = (
                ((end_equity / start_equity) - 1.0) * 100.0
                if start_equity != 0
                else 0.0
            )
            output.append(
                {
                    "year": year,
                    "start_equity": round(start_equity, 8),
                    "end_equity": round(end_equity, 8),
                    "return_pct": round(return_pct, 8),
                    "positive_months": sum(
                        float(row["return_pct"]) > 0 for row in rows
                    ),
                    "negative_months": sum(
                        float(row["return_pct"]) < 0 for row in rows
                    ),
                }
            )

        return output

    def monthly_matrix(
        self,
        equity_curve: Iterable[dict[str, Any]],
    ) -> dict[int, dict[str, float]]:
        matrix: dict[int, dict[str, float]] = defaultdict(dict)

        for row in self.monthly_performance(equity_curve):
            month_key = f"{int(row['month']):02d}"
            matrix[int(row["year"])][month_key] = float(row["return_pct"])

        return dict(matrix)

    def full_report(
        self,
        equity_curve: Iterable[dict[str, Any]],
        *,
        periods_per_year: int = 252,
        risk_free_rate_pct: float = 0.0,
        max_drawdown_pct: float | None = None,
        rolling_window: int = 20,
    ) -> dict[str, Any]:
        points = [dict(point) for point in equity_curve]
        summary = self.summarize(
            points,
            periods_per_year=periods_per_year,
            risk_free_rate_pct=risk_free_rate_pct,
            max_drawdown_pct=max_drawdown_pct,
        )
        return {
            "summary": summary.to_dict(),
            "period_returns": self.calculate_returns(points),
            "rolling_returns": self.rolling_returns(
                points,
                window=rolling_window,
            ),
            "monthly_performance": self.monthly_performance(points),
            "yearly_performance": self.yearly_performance(points),
            "monthly_matrix": self.monthly_matrix(points),
        }

    @staticmethod
    def _annualized_return(
        cumulative_return_pct: float,
        total_periods: int,
        periods_per_year: int,
    ) -> float:
        if total_periods <= 0 or periods_per_year <= 0:
            return 0.0

        growth = 1.0 + (cumulative_return_pct / 100.0)
        if growth <= 0:
            return -100.0

        return (
            growth ** (periods_per_year / total_periods) - 1.0
        ) * 100.0

    @staticmethod
    def _annualized_volatility(
        returns_decimal: list[float],
        periods_per_year: int,
    ) -> float:
        if len(returns_decimal) < 2 or periods_per_year <= 0:
            return 0.0
        return pstdev(returns_decimal) * math.sqrt(periods_per_year) * 100.0

    @staticmethod
    def _sharpe_ratio(
        returns_decimal: list[float],
        periods_per_year: int,
        risk_free_rate_pct: float,
    ) -> float:
        if len(returns_decimal) < 2 or periods_per_year <= 0:
            return 0.0

        periodic_rf = (risk_free_rate_pct / 100.0) / periods_per_year
        excess = [value - periodic_rf for value in returns_decimal]
        deviation = pstdev(excess)

        if deviation == 0:
            return 0.0

        return (mean(excess) / deviation) * math.sqrt(periods_per_year)

    @staticmethod
    def _sortino_ratio(
        returns_decimal: list[float],
        periods_per_year: int,
        risk_free_rate_pct: float,
    ) -> float:
        if not returns_decimal or periods_per_year <= 0:
            return 0.0

        periodic_rf = (risk_free_rate_pct / 100.0) / periods_per_year
        excess = [value - periodic_rf for value in returns_decimal]
        downside = [min(value, 0.0) for value in excess]
        downside_deviation = math.sqrt(
            sum(value * value for value in downside) / len(downside)
        )

        if downside_deviation == 0:
            return 0.0

        return (
            mean(excess) / downside_deviation
        ) * math.sqrt(periods_per_year)

    @staticmethod
    def _max_drawdown_pct(equities: list[float]) -> float:
        if not equities:
            return 0.0

        peak = equities[0]
        maximum = 0.0

        for equity in equities:
            peak = max(peak, equity)
            if peak == 0:
                continue
            drawdown = ((peak - equity) / peak) * 100.0
            maximum = max(maximum, drawdown)

        return maximum

    @staticmethod
    def _parse_timestamp(value: str) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
