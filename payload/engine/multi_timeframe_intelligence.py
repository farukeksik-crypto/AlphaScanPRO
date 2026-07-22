from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

import pandas as pd

from engine.market_regime_engine import MarketRegimeEngine, MarketRegimeResult


@dataclass(frozen=True)
class TimeframeRegime:
    timeframe: str
    weight: float
    regime: str
    score: float
    confidence: float
    direction: float
    allow_new_positions: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MultiTimeframeResult:
    dominant_regime: str
    alignment_score: float
    confidence: float
    conflict_level: str
    allow_new_positions: bool
    risk_multiplier: float
    position_size_multiplier: float
    minimum_entry_score_delta: float
    recommendation: str
    reasons: tuple[str, ...]
    timeframes: tuple[TimeframeRegime, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["reasons"] = list(self.reasons)
        data["timeframes"] = [item.to_dict() for item in self.timeframes]
        return data


class MultiTimeframeIntelligence:
    """Birden fazla zaman dilimindeki rejimleri tek, deterministik karara indirger."""

    DEFAULT_WEIGHTS = {"15m": 0.10, "1h": 0.25, "4h": 0.35, "1d": 0.30}
    REGIME_DIRECTION = {
        "BULL": 1.0,
        "RECOVERY": 0.55,
        "SIDEWAYS": 0.0,
        "WEAK": -0.55,
        "BEAR": -1.0,
    }

    def __init__(
        self,
        *,
        weights: Mapping[str, float] | None = None,
        regime_engine: MarketRegimeEngine | None = None,
    ) -> None:
        raw = dict(weights or self.DEFAULT_WEIGHTS)
        total = sum(max(0.0, float(value)) for value in raw.values()) or 1.0
        self.weights = {str(key): max(0.0, float(value)) / total for key, value in raw.items()}
        self.regime_engine = regime_engine or MarketRegimeEngine()

    def analyze_frames(self, frames: Mapping[str, pd.DataFrame | None]) -> MultiTimeframeResult:
        results: dict[str, MarketRegimeResult | dict[str, Any]] = {}
        for timeframe, frame in (frames or {}).items():
            if frame is not None and not frame.empty:
                results[str(timeframe)] = self.regime_engine.analyze_market_data(frame)
        return self.analyze_results(results)

    def analyze_results(
        self,
        results: Mapping[str, MarketRegimeResult | Mapping[str, Any]],
    ) -> MultiTimeframeResult:
        rows: list[TimeframeRegime] = []
        for timeframe, weight in self.weights.items():
            raw = (results or {}).get(timeframe)
            if raw is None:
                continue
            data = raw.to_dict() if isinstance(raw, MarketRegimeResult) else dict(raw)
            regime = str(data.get("regime", "YETERSİZ VERİ")).upper()
            if regime not in self.REGIME_DIRECTION:
                continue
            rows.append(
                TimeframeRegime(
                    timeframe=timeframe,
                    weight=weight,
                    regime=regime,
                    score=float(data.get("score", 0.0) or 0.0),
                    confidence=float(data.get("confidence", 0.0) or 0.0),
                    direction=self.REGIME_DIRECTION[regime],
                    allow_new_positions=bool(data.get("allow_new_positions", False)),
                )
            )

        if not rows:
            return self._fallback("Geçerli zaman dilimi sonucu bulunamadı.")

        available_weight = sum(row.weight for row in rows) or 1.0
        normalized = [(row, row.weight / available_weight) for row in rows]
        directional = sum(row.direction * weight for row, weight in normalized)
        weighted_confidence = sum(row.confidence * weight for row, weight in normalized)
        agreement = sum(abs(row.direction - directional) * weight for row, weight in normalized)
        alignment = max(0.0, min(100.0, (1.0 - agreement / 2.0) * 100.0))

        higher = [row for row in rows if row.timeframe in {"4h", "1d"}]
        lower = [row for row in rows if row.timeframe in {"15m", "1h"}]
        high_direction = self._weighted_direction(higher)
        low_direction = self._weighted_direction(lower)
        cross_conflict = bool(higher and lower and high_direction * low_direction < -0.12)

        if cross_conflict or alignment < 40:
            conflict = "HIGH"
        elif alignment < 65:
            conflict = "MEDIUM"
        else:
            conflict = "LOW"

        dominant = self._dominant_regime(directional)
        coverage = available_weight
        confidence = max(0.0, min(100.0, weighted_confidence * min(1.0, coverage / 0.70)))

        risk = 1.0
        size = 1.0
        score_delta = 0.0
        reasons = [f"Ağırlıklı ana rejim: {dominant}.", f"Zaman dilimi uyumu: %{alignment:.1f}."]
        allow = True

        if conflict == "MEDIUM":
            risk *= 0.75; size *= 0.70; score_delta += 5.0
            reasons.append("Orta zaman dilimi çatışması nedeniyle risk azaltıldı.")
        elif conflict == "HIGH":
            risk *= 0.40; size *= 0.35; score_delta += 10.0
            reasons.append("Yüksek zaman dilimi çatışması nedeniyle savunmacı politika uygulandı.")

        if cross_conflict:
            reasons.append("Alt ve üst zaman dilimleri ters yönde.")

        if high_direction <= -0.45:
            allow = False
            risk = 0.0; size = 0.0; score_delta = max(score_delta, 15.0)
            reasons.append("4H/Günlük görünüm zayıf veya ayı; yeni işlem kilitlendi.")
        elif dominant in {"WEAK", "BEAR"}:
            allow = False
            risk = 0.0; size = 0.0; score_delta = max(score_delta, 15.0)
            reasons.append("Baskın rejim savunmacı; yeni işlem kilitlendi.")

        if confidence < 55.0:
            allow = False
            risk = 0.0; size = 0.0; score_delta = max(score_delta, 12.0)
            reasons.append("Çoklu zaman dilimi güveni %55 altında.")
        elif confidence < 70.0:
            risk *= 0.80; size *= 0.80; score_delta += 3.0
            reasons.append("Orta güven nedeniyle ilave risk azaltımı uygulandı.")

        if len(rows) < 2:
            allow = False
            risk = 0.0; size = 0.0; score_delta = max(score_delta, 12.0)
            reasons.append("Karar için en az iki zaman dilimi gerekli.")

        recommendation = "NORMAL"
        if not allow:
            recommendation = "İŞLEM YOK"
        elif conflict == "HIGH":
            recommendation = "SAVUNMACI"
        elif conflict == "MEDIUM" or confidence < 70:
            recommendation = "TEMKİNLİ"

        return MultiTimeframeResult(
            dominant_regime=dominant,
            alignment_score=round(alignment, 2),
            confidence=round(confidence, 2),
            conflict_level=conflict,
            allow_new_positions=allow,
            risk_multiplier=round(max(0.0, min(1.0, risk)), 3),
            position_size_multiplier=round(max(0.0, min(1.0, size)), 3),
            minimum_entry_score_delta=round(score_delta, 2),
            recommendation=recommendation,
            reasons=tuple(reasons),
            timeframes=tuple(rows),
        )

    @staticmethod
    def _weighted_direction(rows: list[TimeframeRegime]) -> float:
        if not rows:
            return 0.0
        total = sum(row.weight for row in rows) or 1.0
        return sum(row.direction * row.weight for row in rows) / total

    @staticmethod
    def _dominant_regime(direction: float) -> str:
        if direction >= 0.65: return "BULL"
        if direction >= 0.20: return "RECOVERY"
        if direction > -0.20: return "SIDEWAYS"
        if direction > -0.65: return "WEAK"
        return "BEAR"

    @staticmethod
    def _fallback(reason: str) -> MultiTimeframeResult:
        return MultiTimeframeResult(
            dominant_regime="YETERSİZ VERİ", alignment_score=0.0, confidence=0.0,
            conflict_level="UNKNOWN", allow_new_positions=False,
            risk_multiplier=0.0, position_size_multiplier=0.0,
            minimum_entry_score_delta=12.0, recommendation="VERİ BEKLE",
            reasons=(reason,), timeframes=(),
        )
