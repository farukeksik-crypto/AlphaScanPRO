from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from engine.market_regime_engine import MarketRegimeResult


@dataclass(frozen=True)
class AdaptiveStrategyPolicy:
    profile: str
    allow_new_positions: bool
    minimum_entry_score: float
    position_size_multiplier: float
    target1_multiplier: float
    target2_multiplier: float
    trailing_atr_multiplier: float
    smart_exit_score_delta: int
    max_holding_hours_multiplier: float
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["reasons"] = list(self.reasons)
        return data


class AdaptiveStrategyEngine:
    """Piyasa rejimini robotun uygulanabilir işlem politikasına dönüştürür.

    Motor emir üretmez. Giriş eşiği, pozisyon boyutu, hedef genişliği ve
    çıkış hassasiyeti için deterministik bir politika üretir.
    """

    def __init__(
        self,
        *,
        base_minimum_entry_score: float = 75.0,
        base_trailing_atr_multiplier: float = 2.0,
        base_max_holding_hours: float = 72.0,
    ) -> None:
        self.base_minimum_entry_score = float(base_minimum_entry_score)
        self.base_trailing_atr_multiplier = float(base_trailing_atr_multiplier)
        self.base_max_holding_hours = float(base_max_holding_hours)

    def build_policy(self, regime: MarketRegimeResult | dict[str, Any]) -> AdaptiveStrategyPolicy:
        data = regime.to_dict() if isinstance(regime, MarketRegimeResult) else dict(regime or {})
        name = str(data.get("regime", "YETERSİZ VERİ")).upper()
        confidence = self._clamp(float(data.get("confidence", 0.0) or 0.0), 0.0, 100.0)
        volatility = str(data.get("volatility_level", "UNKNOWN")).upper()
        regime_allows = bool(data.get("allow_new_positions", False))

        presets = {
            "BULL": dict(profile="TREND_AGGRESSIVE", score_delta=-3.0, size=1.00, t1=1.15, t2=1.30, trail=1.15, exit_delta=5, hold=1.25),
            "RECOVERY": dict(profile="TREND_BALANCED", score_delta=0.0, size=0.90, t1=1.05, t2=1.15, trail=1.05, exit_delta=2, hold=1.10),
            "SIDEWAYS": dict(profile="RANGE_SELECTIVE", score_delta=7.0, size=0.70, t1=0.80, t2=0.75, trail=0.85, exit_delta=-5, hold=0.65),
            "WEAK": dict(profile="DEFENSIVE", score_delta=12.0, size=0.45, t1=0.70, t2=0.60, trail=0.75, exit_delta=-10, hold=0.45),
            "BEAR": dict(profile="CAPITAL_PROTECTION", score_delta=20.0, size=0.00, t1=0.60, t2=0.50, trail=0.65, exit_delta=-15, hold=0.30),
        }
        preset = presets.get(name, dict(profile="WAIT_FOR_DATA", score_delta=20.0, size=0.00, t1=1.0, t2=1.0, trail=1.0, exit_delta=-10, hold=0.5))

        reasons = [f"Rejim profili: {name} → {preset['profile']}."]
        allow = regime_allows and preset["size"] > 0
        size = float(preset["size"])
        score_delta = float(preset["score_delta"])

        if confidence < 55.0:
            allow = False
            size = 0.0
            score_delta = max(score_delta, 15.0)
            reasons.append("Rejim güveni %55 altında; yeni işlem kilitlendi.")
        elif confidence < 70.0:
            size *= 0.80
            score_delta += 3.0
            reasons.append("Orta güven nedeniyle pozisyon küçültüldü ve giriş eşiği yükseltildi.")
        else:
            reasons.append("Rejim güveni işlem politikası için yeterli.")

        volatility_size = {"LOW": 1.00, "MEDIUM": 1.00, "HIGH": 0.75, "EXTREME": 0.40}.get(volatility, 0.75)
        size *= volatility_size
        if volatility == "HIGH":
            score_delta += 4.0
            reasons.append("Yüksek volatilite nedeniyle risk azaltıldı.")
        elif volatility == "EXTREME":
            score_delta += 8.0
            reasons.append("Aşırı volatilite nedeniyle savunmacı politika uygulandı.")

        minimum_score = self._clamp(self.base_minimum_entry_score + score_delta, 0.0, 100.0)
        trailing = self._clamp(self.base_trailing_atr_multiplier * float(preset["trail"]), 0.5, 6.0)

        return AdaptiveStrategyPolicy(
            profile=str(preset["profile"]),
            allow_new_positions=allow,
            minimum_entry_score=round(minimum_score, 2),
            position_size_multiplier=round(self._clamp(size, 0.0, 1.25), 3),
            target1_multiplier=round(float(preset["t1"]), 3),
            target2_multiplier=round(float(preset["t2"]), 3),
            trailing_atr_multiplier=round(trailing, 3),
            smart_exit_score_delta=int(preset["exit_delta"]),
            max_holding_hours_multiplier=round(float(preset["hold"]), 3),
            reasons=tuple(reasons),
        )

    @staticmethod
    def adjust_targets(entry_price: float, target1: float, target2: float, policy: AdaptiveStrategyPolicy) -> tuple[float, float]:
        entry = float(entry_price)
        if entry <= 0:
            return float(target1), float(target2)
        distance1 = max(0.0, float(target1) - entry)
        distance2 = max(0.0, float(target2) - entry)
        adjusted1 = entry + distance1 * policy.target1_multiplier
        adjusted2 = entry + distance2 * policy.target2_multiplier
        return round(adjusted1, 8), round(adjusted2, 8)

    @staticmethod
    def _clamp(value: float, lower: float, upper: float) -> float:
        return max(lower, min(upper, value))
