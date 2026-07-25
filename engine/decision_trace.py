from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DecisionTrace:
    symbol: str
    decision: str
    score: float
    confidence: float
    probability: float
    risk_level: str
    price: float
    robot_enabled: bool
    accepted: bool
    high_risk_override: bool
    reject_reasons: tuple[str, ...]

    @property
    def primary_reason(self) -> str:
        return self.reject_reasons[0] if self.reject_reasons else "accepted"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reject_reasons"] = list(self.reject_reasons)
        payload["primary_reason"] = self.primary_reason
        return payload

    def to_text(self) -> str:
        if self.accepted:
            suffix = "işleme uygun aday"
            if self.high_risk_override:
                suffix += " (yüksek risk override)"
            return f"{self.symbol}: {suffix}"

        labels = {
            "robot_disabled": "robot kapalı",
            "decision": f"karar={self.decision or 'yok'}",
            "score": "puan eşiği sağlanmadı",
            "confidence": "güven eşiği sağlanmadı",
            "probability": "olasılık eşiği sağlanmadı",
            "risk": f"risk={self.risk_level or 'yok'} kabul edilmiyor",
            "open_position": "açık pozisyon var",
            "invalid_symbol": "sembol yok",
            "invalid_price": "fiyat geçersiz",
        }
        reasons = [labels.get(reason, reason) for reason in self.reject_reasons]
        return f"{self.symbol or '?'}: " + ", ".join(reasons)


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def build_decision_trace(
    row: dict[str, Any],
    robot,
    *,
    robot_enabled: bool | None = None,
) -> DecisionTrace:
    state = robot.get_state()
    effective_enabled = bool(state.get("enabled", False))
    if robot_enabled is not None:
        effective_enabled = bool(robot_enabled and effective_enabled)

    symbol = str(row.get("Kod", "") or "").strip()
    decision = str(row.get("Karar", "") or "").strip()
    score = _safe_float(row.get("Puan"))
    confidence = _safe_float(row.get("Güven"))
    probability = _safe_float(row.get("Başarı Göstergesi %"))
    risk_level = str(row.get("Risk", "") or "").strip()
    price = _safe_float(row.get("Fiyat"))

    high_risk_override = bool(
        robot.config.high_risk_override_enabled
        and risk_level == "Yüksek"
        and score >= robot.config.high_risk_override_min_score
        and confidence >= robot.config.high_risk_override_min_confidence
        and probability >= robot.config.high_risk_override_min_probability
    )

    reasons: list[str] = []
    if not effective_enabled:
        reasons.append("robot_disabled")
    if not symbol:
        reasons.append("invalid_symbol")
    if price <= 0:
        reasons.append("invalid_price")
    if decision not in robot.config.allowed_decisions:
        reasons.append("decision")
    if score < robot.config.minimum_score:
        reasons.append("score")
    if confidence < robot.config.minimum_confidence:
        reasons.append("confidence")
    if probability < robot.config.minimum_probability:
        reasons.append("probability")

    risk_allowed = (
        not robot.config.allowed_risks
        or risk_level in robot.config.allowed_risks
        or high_risk_override
    )
    if not risk_allowed:
        reasons.append("risk")

    if symbol and robot.has_open_position(symbol):
        reasons.append("open_position")

    return DecisionTrace(
        symbol=symbol,
        decision=decision,
        score=score,
        confidence=confidence,
        probability=probability,
        risk_level=risk_level,
        price=price,
        robot_enabled=effective_enabled,
        accepted=not reasons,
        high_risk_override=high_risk_override,
        reject_reasons=tuple(reasons),
    )
