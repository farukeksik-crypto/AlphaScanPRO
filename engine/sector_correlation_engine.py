from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CorrelationCheckResult:
    allowed: bool
    symbol: str
    sector: str
    sector_position_count: int
    max_sector_positions: int
    highest_correlation: float
    highest_correlated_symbol: str | None
    correlation_limit: float
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["reasons"] = list(self.reasons)
        return data


class SectorCorrelationEngine:
    def __init__(
        self,
        *,
        max_sector_positions: int = 2,
        correlation_limit: float = 0.85,
        min_observations: int = 30,
    ) -> None:
        if max_sector_positions < 1:
            raise ValueError("max_sector_positions en az 1 olmalıdır.")
        if not 0.0 <= correlation_limit <= 1.0:
            raise ValueError("correlation_limit 0 ile 1 arasında olmalıdır.")
        if min_observations < 5:
            raise ValueError("min_observations en az 5 olmalıdır.")

        self.max_sector_positions = int(max_sector_positions)
        self.correlation_limit = float(correlation_limit)
        self.min_observations = int(min_observations)

    def check_candidate(
        self,
        *,
        symbol: str,
        sector: str | None,
        open_positions: Iterable[dict[str, Any]] | pd.DataFrame | None,
        candidate_prices: pd.Series | None = None,
        position_price_map: dict[str, pd.Series] | None = None,
    ) -> CorrelationCheckResult:
        normalized_symbol = self._normalize_symbol(symbol)
        normalized_sector = self._normalize_sector(sector)
        positions = self._normalize_positions(open_positions)

        same_sector = [
            item
            for item in positions
            if self._normalize_sector(item.get("sector")) == normalized_sector
            and normalized_sector != "UNKNOWN"
        ]

        reasons: list[str] = []
        allowed = True

        if len(same_sector) >= self.max_sector_positions:
            allowed = False
            reasons.append(
                f"{normalized_sector} sektöründe maksimum pozisyon sayısına ulaşıldı."
            )
        else:
            reasons.append(
                f"{normalized_sector} sektör yoğunluğu uygun "
                f"({len(same_sector)}/{self.max_sector_positions})."
            )

        highest_corr = 0.0
        highest_symbol: str | None = None

        if candidate_prices is not None and position_price_map:
            for position in positions:
                position_symbol = self._normalize_symbol(position.get("symbol", ""))
                if not position_symbol or position_symbol == normalized_symbol:
                    continue

                price_series = position_price_map.get(position_symbol)
                if price_series is None:
                    continue

                correlation = self.calculate_return_correlation(
                    candidate_prices,
                    price_series,
                )
                if np.isnan(correlation):
                    continue

                abs_corr = abs(float(correlation))
                if abs_corr > highest_corr:
                    highest_corr = abs_corr
                    highest_symbol = position_symbol

            if highest_corr >= self.correlation_limit:
                allowed = False
                reasons.append(
                    f"{highest_symbol} ile korelasyon çok yüksek "
                    f"({highest_corr:.2f} >= {self.correlation_limit:.2f})."
                )
            elif highest_symbol is not None:
                reasons.append(
                    f"En yüksek korelasyon {highest_symbol} ile {highest_corr:.2f}; "
                    "limit altında."
                )
            else:
                reasons.append("Korelasyon karşılaştırması için yeterli veri bulunamadı.")
        else:
            reasons.append("Fiyat serileri verilmediği için korelasyon kontrolü atlandı.")

        return CorrelationCheckResult(
            allowed=allowed,
            symbol=normalized_symbol,
            sector=normalized_sector,
            sector_position_count=len(same_sector),
            max_sector_positions=self.max_sector_positions,
            highest_correlation=round(highest_corr, 4),
            highest_correlated_symbol=highest_symbol,
            correlation_limit=self.correlation_limit,
            reasons=tuple(reasons),
        )

    def calculate_return_correlation(
        self,
        first_prices: pd.Series,
        second_prices: pd.Series,
    ) -> float:
        first = pd.to_numeric(first_prices, errors="coerce").rename("first")
        second = pd.to_numeric(second_prices, errors="coerce").rename("second")

        aligned = pd.concat([first, second], axis=1).dropna()
        if len(aligned) < self.min_observations:
            return float("nan")

        returns = aligned.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
        if len(returns) < self.min_observations - 1:
            return float("nan")

        if returns["first"].std(ddof=0) == 0 or returns["second"].std(ddof=0) == 0:
            return float("nan")

        return float(returns["first"].corr(returns["second"]))

    def build_correlation_matrix(
        self,
        price_map: dict[str, pd.Series],
    ) -> pd.DataFrame:
        if not price_map:
            return pd.DataFrame()

        returns: dict[str, pd.Series] = {}
        for symbol, prices in price_map.items():
            normalized = self._normalize_symbol(symbol)
            series = pd.to_numeric(prices, errors="coerce")
            returns[normalized] = series.pct_change()

        frame = pd.DataFrame(returns).replace([np.inf, -np.inf], np.nan)
        return frame.corr(min_periods=self.min_observations)

    @staticmethod
    def _normalize_symbol(symbol: Any) -> str:
        return str(symbol or "").strip().upper()

    @staticmethod
    def _normalize_sector(sector: Any) -> str:
        value = str(sector or "").strip().upper()
        return value if value else "UNKNOWN"

    @staticmethod
    def _normalize_positions(
        open_positions: Iterable[dict[str, Any]] | pd.DataFrame | None,
    ) -> list[dict[str, Any]]:
        if open_positions is None:
            return []

        if isinstance(open_positions, pd.DataFrame):
            records = open_positions.to_dict(orient="records")
        else:
            records = list(open_positions)

        normalized: list[dict[str, Any]] = []
        for item in records:
            if isinstance(item, dict):
                normalized.append(item)
        return normalized
