from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any, Iterable


@dataclass
class OptimizationSuggestion:
    parameter: str
    current_value: Any
    suggested_value: Any
    confidence: float
    reason: str
    sample_size: int
    metric_name: str
    metric_value: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AdaptiveOptimizer:
    def analyze_score_bands(
        self,
        trades: Iterable[dict[str, Any]],
        *,
        score_field: str = "ai_score",
        band_size: int = 10,
    ) -> list[dict[str, Any]]:
        if band_size <= 0:
            raise ValueError("band_size 0'dan büyük olmalıdır.")

        buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for trade in self._closed_trades(trades):
            score = trade.get(score_field)
            if score is None:
                continue

            score_value = max(0, min(100, int(float(score))))
            lower = (score_value // band_size) * band_size
            upper = min(100, lower + band_size - 1)
            label = f"{lower}-{upper}"
            buckets[label].append(trade)

        rows = [
            self._summarize_bucket(label, bucket)
            for label, bucket in buckets.items()
        ]
        return sorted(rows, key=lambda row: int(row["band"].split("-")[0]))

    def analyze_numeric_parameter(
        self,
        trades: Iterable[dict[str, Any]],
        *,
        field: str,
        bins: list[tuple[float, float]],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []

        for lower, upper in bins:
            bucket = []
            for trade in self._closed_trades(trades):
                value = trade.get(field)
                if value is None:
                    continue
                numeric = float(value)
                if lower <= numeric < upper:
                    bucket.append(trade)

            label = f"{lower:g}-{upper:g}"
            summary = self._summarize_bucket(label, bucket)
            summary["field"] = field
            summary["range_min"] = lower
            summary["range_max"] = upper
            rows.append(summary)

        return rows

    def optimize_ai_minimum_score(
        self,
        trades: Iterable[dict[str, Any]],
        *,
        current_value: int,
        minimum_samples: int = 5,
    ) -> OptimizationSuggestion:
        bands = self.analyze_score_bands(trades)

        eligible = [
            band for band in bands
            if band["sample_size"] >= minimum_samples
        ]

        if not eligible:
            return OptimizationSuggestion(
                parameter="ai_minimum_trade_score",
                current_value=current_value,
                suggested_value=current_value,
                confidence=0.0,
                reason="Yeterli örnek bulunamadı.",
                sample_size=sum(band["sample_size"] for band in bands),
                metric_name="expectancy",
                metric_value=0.0,
            )

        best = max(
            eligible,
            key=lambda row: (
                row["expectancy"],
                row["profit_factor"],
                row["win_rate"],
            ),
        )
        lower = int(best["band"].split("-")[0])
        suggested = max(0, min(100, lower))

        return OptimizationSuggestion(
            parameter="ai_minimum_trade_score",
            current_value=current_value,
            suggested_value=suggested,
            confidence=self._confidence(
                best["sample_size"],
                best["win_rate"],
            ),
            reason=(
                f"{best['band']} AI skor bandı en yüksek beklenti değerini "
                f"üretti."
            ),
            sample_size=best["sample_size"],
            metric_name="expectancy",
            metric_value=round(best["expectancy"], 8),
        )

    def optimize_adx_threshold(
        self,
        trades: Iterable[dict[str, Any]],
        *,
        current_value: float,
        minimum_samples: int = 5,
    ) -> OptimizationSuggestion:
        bins = [
            (0, 12),
            (12, 18),
            (18, 25),
            (25, 35),
            (35, 1000),
        ]
        rows = self.analyze_numeric_parameter(
            trades,
            field="adx",
            bins=bins,
        )
        return self._numeric_suggestion(
            parameter="adx_threshold",
            current_value=current_value,
            rows=rows,
            minimum_samples=minimum_samples,
            metric_name="expectancy",
        )

    def optimize_rsi_range(
        self,
        trades: Iterable[dict[str, Any]],
        *,
        current_min: float,
        current_max: float,
        minimum_samples: int = 5,
    ) -> dict[str, OptimizationSuggestion]:
        bins = [
            (0, 30),
            (30, 40),
            (40, 50),
            (50, 60),
            (60, 70),
            (70, 101),
        ]
        rows = self.analyze_numeric_parameter(
            trades,
            field="rsi",
            bins=bins,
        )
        eligible = [
            row for row in rows
            if row["sample_size"] >= minimum_samples
        ]

        if not eligible:
            return {
                "rsi_min": self._no_change(
                    "rsi_min",
                    current_min,
                    sum(row["sample_size"] for row in rows),
                ),
                "rsi_max": self._no_change(
                    "rsi_max",
                    current_max,
                    sum(row["sample_size"] for row in rows),
                ),
            }

        best = max(
            eligible,
            key=lambda row: (
                row["expectancy"],
                row["profit_factor"],
                row["win_rate"],
            ),
        )

        confidence = self._confidence(
            best["sample_size"],
            best["win_rate"],
        )
        reason = (
            f"RSI {best['range_min']:g}-{best['range_max']:g} aralığı "
            f"en güçlü sonucu üretti."
        )

        return {
            "rsi_min": OptimizationSuggestion(
                parameter="rsi_min",
                current_value=current_min,
                suggested_value=best["range_min"],
                confidence=confidence,
                reason=reason,
                sample_size=best["sample_size"],
                metric_name="expectancy",
                metric_value=round(best["expectancy"], 8),
            ),
            "rsi_max": OptimizationSuggestion(
                parameter="rsi_max",
                current_value=current_max,
                suggested_value=best["range_max"],
                confidence=confidence,
                reason=reason,
                sample_size=best["sample_size"],
                metric_name="expectancy",
                metric_value=round(best["expectancy"], 8),
            ),
        }

    def analyze_exit_methods(
        self,
        trades: Iterable[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for trade in self._closed_trades(trades):
            reason = str(
                trade.get("exit_reason")
                or trade.get("close_reason")
                or "UNKNOWN"
            ).upper()
            buckets[reason].append(trade)

        rows = [
            {
                "exit_reason": reason,
                **self._summarize_bucket(reason, bucket),
            }
            for reason, bucket in buckets.items()
        ]
        return sorted(rows, key=lambda row: row["expectancy"], reverse=True)

    def full_report(
        self,
        trades: Iterable[dict[str, Any]],
        *,
        current_ai_minimum_score: int = 60,
        current_adx_threshold: float = 18.0,
        current_rsi_min: float = 42.0,
        current_rsi_max: float = 65.0,
        minimum_samples: int = 5,
    ) -> dict[str, Any]:
        records = [dict(trade) for trade in trades]
        rsi = self.optimize_rsi_range(
            records,
            current_min=current_rsi_min,
            current_max=current_rsi_max,
            minimum_samples=minimum_samples,
        )

        suggestions = [
            self.optimize_ai_minimum_score(
                records,
                current_value=current_ai_minimum_score,
                minimum_samples=minimum_samples,
            ),
            self.optimize_adx_threshold(
                records,
                current_value=current_adx_threshold,
                minimum_samples=minimum_samples,
            ),
            rsi["rsi_min"],
            rsi["rsi_max"],
        ]

        return {
            "score_bands": self.analyze_score_bands(records),
            "adx_analysis": self.analyze_numeric_parameter(
                records,
                field="adx",
                bins=[
                    (0, 12),
                    (12, 18),
                    (18, 25),
                    (25, 35),
                    (35, 1000),
                ],
            ),
            "rsi_analysis": self.analyze_numeric_parameter(
                records,
                field="rsi",
                bins=[
                    (0, 30),
                    (30, 40),
                    (40, 50),
                    (50, 60),
                    (60, 70),
                    (70, 101),
                ],
            ),
            "exit_method_analysis": self.analyze_exit_methods(records),
            "suggestions": [
                suggestion.to_dict()
                for suggestion in suggestions
            ],
        }

    def _numeric_suggestion(
        self,
        *,
        parameter: str,
        current_value: float,
        rows: list[dict[str, Any]],
        minimum_samples: int,
        metric_name: str,
    ) -> OptimizationSuggestion:
        eligible = [
            row for row in rows
            if row["sample_size"] >= minimum_samples
        ]

        if not eligible:
            return self._no_change(
                parameter,
                current_value,
                sum(row["sample_size"] for row in rows),
            )

        best = max(
            eligible,
            key=lambda row: (
                row[metric_name],
                row["profit_factor"],
                row["win_rate"],
            ),
        )

        return OptimizationSuggestion(
            parameter=parameter,
            current_value=current_value,
            suggested_value=best["range_min"],
            confidence=self._confidence(
                best["sample_size"],
                best["win_rate"],
            ),
            reason=(
                f"{best['range_min']:g}-{best['range_max']:g} aralığı "
                f"en yüksek {metric_name} değerini üretti."
            ),
            sample_size=best["sample_size"],
            metric_name=metric_name,
            metric_value=round(float(best[metric_name]), 8),
        )

    @staticmethod
    def _closed_trades(
        trades: Iterable[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [
            dict(trade)
            for trade in trades
            if str(trade.get("status") or "").upper() == "CLOSED"
            and trade.get("pnl") is not None
        ]

    @staticmethod
    def _summarize_bucket(
        label: str,
        trades: list[dict[str, Any]],
    ) -> dict[str, Any]:
        pnls = [float(trade.get("pnl") or 0.0) for trade in trades]
        wins = [value for value in pnls if value > 0]
        losses = [value for value in pnls if value < 0]
        total = len(pnls)

        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        net_pnl = sum(pnls)
        win_rate = (len(wins) / total * 100.0) if total else 0.0
        expectancy = (net_pnl / total) if total else 0.0
        profit_factor = (
            gross_profit / gross_loss
            if gross_loss > 0
            else (999.0 if gross_profit > 0 else 0.0)
        )

        return {
            "band": label,
            "sample_size": total,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(win_rate, 8),
            "gross_profit": round(gross_profit, 8),
            "gross_loss": round(gross_loss, 8),
            "net_pnl": round(net_pnl, 8),
            "expectancy": round(expectancy, 8),
            "profit_factor": round(profit_factor, 8),
        }

    @staticmethod
    def _confidence(
        sample_size: int,
        win_rate: float,
    ) -> float:
        sample_component = min(1.0, sample_size / 30.0)
        win_component = min(1.0, max(0.0, win_rate / 100.0))
        return round(
            (sample_component * 0.65 + win_component * 0.35) * 100.0,
            2,
        )

    @staticmethod
    def _no_change(
        parameter: str,
        current_value: Any,
        sample_size: int,
    ) -> OptimizationSuggestion:
        return OptimizationSuggestion(
            parameter=parameter,
            current_value=current_value,
            suggested_value=current_value,
            confidence=0.0,
            reason="Yeterli örnek bulunamadı; mevcut değer korunmalı.",
            sample_size=sample_size,
            metric_name="expectancy",
            metric_value=0.0,
        )
