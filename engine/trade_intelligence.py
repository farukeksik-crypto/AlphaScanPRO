from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class TradeIntelligenceResult:
    profit_pct: float
    holding_minutes: float
    mfe_pct: float
    mae_pct: float
    risk_pct: float
    reward_pct: float
    risk_reward: float
    entry_efficiency: float
    exit_efficiency: float
    trade_quality_score: float
    trade_grade: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, float(value)))


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _grade(score: float) -> str:
    if score >= 90:
        return "A+"
    if score >= 80:
        return "A"
    if score >= 70:
        return "B"
    if score >= 60:
        return "C"
    return "D"


def analyze_closed_trade(
    *,
    entry_price: float,
    exit_price: float,
    quantity: float,
    total_profit: float,
    opened_at: str | None,
    closed_at: str | None,
    highest_price: float | None = None,
    lowest_price: float | None = None,
    stop_price: float | None = None,
    target_price: float | None = None,
    technical_score: float = 0.0,
    confidence_score: float = 0.0,
) -> TradeIntelligenceResult:
    entry_price = float(entry_price)
    exit_price = float(exit_price)
    quantity = float(quantity)

    if entry_price <= 0:
        raise ValueError("entry_price sıfırdan büyük olmalıdır.")
    if exit_price <= 0:
        raise ValueError("exit_price sıfırdan büyük olmalıdır.")
    if quantity <= 0:
        raise ValueError("quantity sıfırdan büyük olmalıdır.")

    highest = max(
        entry_price,
        exit_price,
        float(highest_price) if highest_price not in (None, 0) else entry_price,
    )
    lowest = min(
        entry_price,
        exit_price,
        float(lowest_price) if lowest_price not in (None, 0) else entry_price,
    )

    invested_amount = entry_price * quantity
    profit_pct = (float(total_profit) / invested_amount) * 100.0
    mfe_pct = ((highest - entry_price) / entry_price) * 100.0
    mae_pct = ((lowest - entry_price) / entry_price) * 100.0

    stop = float(stop_price or 0.0)
    target = float(target_price or 0.0)

    risk_pct = (
        ((entry_price - stop) / entry_price) * 100.0
        if 0 < stop < entry_price
        else max(abs(mae_pct), 0.01)
    )
    reward_pct = (
        ((target - entry_price) / entry_price) * 100.0
        if target > entry_price
        else max(mfe_pct, 0.0)
    )
    risk_reward = reward_pct / risk_pct if risk_pct > 0 else 0.0

    adverse_usage = abs(min(mae_pct, 0.0)) / max(risk_pct, 0.01)
    entry_efficiency = _clamp(100.0 - adverse_usage * 100.0)

    gross_move_pct = ((exit_price - entry_price) / entry_price) * 100.0
    if mfe_pct > 0 and gross_move_pct > 0:
        exit_efficiency = _clamp((gross_move_pct / mfe_pct) * 100.0)
    elif gross_move_pct == 0:
        exit_efficiency = 50.0
    else:
        exit_efficiency = 0.0

    opened = _parse_datetime(opened_at)
    closed = _parse_datetime(closed_at)
    holding_minutes = 0.0
    if opened and closed and closed >= opened:
        holding_minutes = (closed - opened).total_seconds() / 60.0

    profitability_component = _clamp(50.0 + profit_pct * 8.0)
    risk_reward_component = _clamp(risk_reward * 30.0)

    quality_score = (
        profitability_component * 0.30
        + risk_reward_component * 0.20
        + entry_efficiency * 0.15
        + exit_efficiency * 0.15
        + _clamp(technical_score) * 0.10
        + _clamp(confidence_score) * 0.10
    )
    quality_score = round(_clamp(quality_score), 2)

    return TradeIntelligenceResult(
        profit_pct=round(profit_pct, 4),
        holding_minutes=round(holding_minutes, 2),
        mfe_pct=round(mfe_pct, 4),
        mae_pct=round(mae_pct, 4),
        risk_pct=round(risk_pct, 4),
        reward_pct=round(reward_pct, 4),
        risk_reward=round(risk_reward, 4),
        entry_efficiency=round(entry_efficiency, 2),
        exit_efficiency=round(exit_efficiency, 2),
        trade_quality_score=quality_score,
        trade_grade=_grade(quality_score),
    )
