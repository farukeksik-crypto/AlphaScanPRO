from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class AIDecisionResult:
    score: float
    decision: str
    confidence: float
    allow_trade: bool
    reasons: tuple[str, ...]
    components: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["reasons"] = list(self.reasons)
        return data


class AIDecisionEngine:
    DEFAULT_WEIGHTS = {
        "technical_score": 0.28,
        "trend_quality": 0.15,
        "volume_quality": 0.10,
        "risk_quality": 0.15,
        "market_regime_score": 0.12,
        "correlation_quality": 0.08,
        "backtest_quality": 0.07,
        "fundamental_quality": 0.05,
    }

    def __init__(
        self,
        *,
        minimum_trade_score: float = 70.0,
        strong_buy_score: float = 88.0,
        buy_score: float = 78.0,
        watch_score: float = 65.0,
        weights: dict[str, float] | None = None,
    ) -> None:
        self.minimum_trade_score = float(minimum_trade_score)
        self.strong_buy_score = float(strong_buy_score)
        self.buy_score = float(buy_score)
        self.watch_score = float(watch_score)

        if not (
            0.0 <= self.watch_score
            <= self.minimum_trade_score
            <= self.buy_score
            <= self.strong_buy_score
            <= 100.0
        ):
            raise ValueError("Karar eşikleri 0-100 arasında ve sıralı olmalıdır.")

        selected = dict(self.DEFAULT_WEIGHTS)
        if weights:
            selected.update(weights)

        if any(value < 0 for value in selected.values()):
            raise ValueError("Ağırlıklar negatif olamaz.")

        total = sum(selected.values())
        if total <= 0:
            raise ValueError("Toplam ağırlık sıfırdan büyük olmalıdır.")

        self.weights = {
            key: float(value) / total
            for key, value in selected.items()
        }

    def evaluate(
        self,
        *,
        technical_score: float,
        trend_quality: float,
        volume_quality: float,
        risk_quality: float,
        market_regime_score: float,
        correlation_quality: float,
        backtest_quality: float = 50.0,
        fundamental_quality: float = 50.0,
        hard_block_reasons: list[str] | tuple[str, ...] | None = None,
    ) -> AIDecisionResult:
        raw_components = {
            "technical_score": technical_score,
            "trend_quality": trend_quality,
            "volume_quality": volume_quality,
            "risk_quality": risk_quality,
            "market_regime_score": market_regime_score,
            "correlation_quality": correlation_quality,
            "backtest_quality": backtest_quality,
            "fundamental_quality": fundamental_quality,
        }

        components = {
            key: self._clamp_score(value)
            for key, value in raw_components.items()
        }

        weighted_score = sum(
            components[key] * self.weights[key]
            for key in self.weights
        )

        block_reasons = tuple(
            str(reason).strip()
            for reason in (hard_block_reasons or [])
            if str(reason).strip()
        )

        reasons = self._build_reasons(components)

        if block_reasons:
            decision = "NO TRADE"
            allow_trade = False
            reasons.extend(f"Zorunlu engel: {reason}" for reason in block_reasons)
        else:
            decision = self._decision_from_score(weighted_score)
            allow_trade = weighted_score >= self.minimum_trade_score

        confidence = self._confidence(components, weighted_score)

        return AIDecisionResult(
            score=round(weighted_score, 2),
            decision=decision,
            confidence=round(confidence, 2),
            allow_trade=allow_trade,
            reasons=tuple(reasons),
            components={
                key: round(value, 2)
                for key, value in components.items()
            },
        )

    def _decision_from_score(self, score: float) -> str:
        if score >= self.strong_buy_score:
            return "STRONG BUY"
        if score >= self.buy_score:
            return "BUY"
        if score >= self.minimum_trade_score:
            return "BUY CANDIDATE"
        if score >= self.watch_score:
            return "WATCH"
        if score >= 50.0:
            return "WEAK"
        return "NO TRADE"

    def _build_reasons(self, components: dict[str, float]) -> list[str]:
        labels = {
            "technical_score": "Teknik skor",
            "trend_quality": "Trend kalitesi",
            "volume_quality": "Hacim kalitesi",
            "risk_quality": "Risk kalitesi",
            "market_regime_score": "Piyasa rejimi",
            "correlation_quality": "Korelasyon kalitesi",
            "backtest_quality": "Backtest kalitesi",
            "fundamental_quality": "Finansal kalite",
        }

        strongest = sorted(
            components.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:3]

        weakest = sorted(
            components.items(),
            key=lambda item: item[1],
        )[:2]

        reasons = [
            f"Güçlü bileşen: {labels[key]} {value:.1f}"
            for key, value in strongest
            if value >= 70.0
        ]

        reasons.extend(
            f"Zayıf bileşen: {labels[key]} {value:.1f}"
            for key, value in weakest
            if value < 50.0
        )

        if not reasons:
            reasons.append("Bileşenler orta seviyede ve dengeli.")

        return reasons

    @staticmethod
    def _confidence(
        components: dict[str, float],
        weighted_score: float,
    ) -> float:
        values = list(components.values())
        spread = max(values) - min(values)
        consistency = max(0.0, 100.0 - spread)

        distance_from_mid = abs(weighted_score - 50.0) * 2.0
        return min(100.0, consistency * 0.55 + distance_from_mid * 0.45)

    @staticmethod
    def _clamp_score(value: float) -> float:
        return max(0.0, min(100.0, float(value)))
