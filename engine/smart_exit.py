from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SmartExitConfig:
    enabled: bool = True
    min_profit_pct: float = 0.50
    exit_score_threshold: int = 50
    watch_score_threshold: int = 40
    min_confirmations: int = 2

    rsi_overbought_level: float = 70.0
    weak_volume_ratio: float = 0.70

    rsi_reversal_points: int = 25
    macd_negative_points: int = 25
    ema20_break_points: int = 20
    weak_volume_points: int = 15
    adx_weakening_points: int = 15


@dataclass(frozen=True)
class SmartExitResult:
    should_exit: bool
    status: str
    score: int
    confirmations: int
    reasons: tuple[str, ...]
    profit_pct: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "should_exit": self.should_exit,
            "status": self.status,
            "score": self.score,
            "confirmations": self.confirmations,
            "reasons": list(self.reasons),
            "profit_pct": self.profit_pct,
        }


def evaluate_smart_exit(
    *,
    entry_price: float,
    current_price: float,
    current_rsi: float | None,
    previous_rsi: float | None,
    macd_hist: float | None,
    close_price: float | None,
    ema20: float | None,
    volume_ratio: float | None,
    current_adx: float | None,
    previous_adx: float | None,
    config: SmartExitConfig | None = None,
) -> SmartExitResult:
    cfg = config or SmartExitConfig()

    if entry_price <= 0:
        raise ValueError("entry_price sıfırdan büyük olmalıdır.")

    profit_pct = ((current_price / entry_price) - 1.0) * 100.0

    if not cfg.enabled:
        return SmartExitResult(
            should_exit=False,
            status="DISABLED",
            score=0,
            confirmations=0,
            reasons=(),
            profit_pct=profit_pct,
        )

    if profit_pct < cfg.min_profit_pct:
        return SmartExitResult(
            should_exit=False,
            status="PROFIT_FILTER",
            score=0,
            confirmations=0,
            reasons=(),
            profit_pct=profit_pct,
        )

    score = 0
    reasons: list[str] = []

    if (
        previous_rsi is not None
        and current_rsi is not None
        and previous_rsi >= cfg.rsi_overbought_level
        and current_rsi < previous_rsi
    ):
        score += cfg.rsi_reversal_points
        reasons.append("RSI aşırı alımdan aşağı döndü")

    if macd_hist is not None and macd_hist < 0:
        score += cfg.macd_negative_points
        reasons.append("MACD histogram negatif")

    if (
        close_price is not None
        and ema20 is not None
        and close_price < ema20
    ):
        score += cfg.ema20_break_points
        reasons.append("Fiyat EMA20 altında")

    if (
        volume_ratio is not None
        and volume_ratio < cfg.weak_volume_ratio
    ):
        score += cfg.weak_volume_points
        reasons.append("Hacim zayıfladı")

    if (
        current_adx is not None
        and previous_adx is not None
        and current_adx < previous_adx
    ):
        score += cfg.adx_weakening_points
        reasons.append("ADX zayıflıyor")

    confirmations = len(reasons)
    should_exit = (
        score >= cfg.exit_score_threshold
        and confirmations >= cfg.min_confirmations
    )

    if should_exit:
        status = "SMART_EXIT"
    elif score >= cfg.watch_score_threshold:
        status = "WATCH"
    else:
        status = "HOLD"

    return SmartExitResult(
        should_exit=should_exit,
        status=status,
        score=score,
        confirmations=confirmations,
        reasons=tuple(reasons),
        profit_pct=profit_pct,
    )
