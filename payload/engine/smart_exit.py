from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class SmartExitAction(str, Enum):
    HOLD = "HOLD"
    TRAIL = "TRAIL"
    PARTIAL_EXIT = "PARTIAL_EXIT"
    FULL_EXIT = "FULL_EXIT"


@dataclass(frozen=True)
class SmartExitConfig:
    enabled: bool = True
    min_profit_pct: float = 0.50
    watch_score_threshold: int = 35
    partial_exit_score_threshold: int = 50
    full_exit_score_threshold: int = 70
    exit_score_threshold: int | None = None
    min_confirmations: int = 2
    full_exit_min_confirmations: int = 3

    rsi_overbought_level: float = 70.0
    rsi_weak_level: float = 50.0
    weak_volume_ratio: float = 0.70
    weak_adx_level: float = 18.0

    rsi_reversal_points: int = 25
    rsi_weak_points: int = 10
    macd_negative_points: int = 25
    ema20_break_points: int = 20
    weak_volume_points: int = 10
    adx_weakening_points: int = 10
    adx_weak_points: int = 10
    profit_protection_points: int = 10
    partial_tp_protection_points: int = 10

    def __post_init__(self) -> None:
        if self.exit_score_threshold is not None:
            object.__setattr__(
                self,
                "partial_exit_score_threshold",
                int(self.exit_score_threshold),
            )
        thresholds = (
            self.watch_score_threshold,
            self.partial_exit_score_threshold,
            self.full_exit_score_threshold,
        )
        if thresholds != tuple(sorted(thresholds)):
            raise ValueError("Smart Exit eşikleri küçükten büyüğe sıralanmalıdır.")
        if self.min_confirmations < 1:
            raise ValueError("min_confirmations en az 1 olmalıdır.")
        if self.full_exit_min_confirmations < self.min_confirmations:
            raise ValueError(
                "full_exit_min_confirmations, min_confirmations değerinden küçük olamaz."
            )


@dataclass(frozen=True)
class SmartExitResult:
    should_exit: bool
    action: SmartExitAction
    status: str
    score: int
    confirmations: int
    reasons: tuple[str, ...]
    profit_pct: float

    @property
    def should_partial_exit(self) -> bool:
        return self.action == SmartExitAction.PARTIAL_EXIT

    @property
    def should_full_exit(self) -> bool:
        return self.action == SmartExitAction.FULL_EXIT

    def as_dict(self) -> dict[str, Any]:
        return {
            "should_exit": self.should_exit,
            "action": self.action.value,
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
    break_even_active: bool = False,
    trailing_active: bool = False,
    partial_stage: int = 0,
    config: SmartExitConfig | None = None,
) -> SmartExitResult:
    """Piyasa zayıflamasını puanlayıp HOLD/TRAIL/KISMİ/TAM çıkış kararı üretir.

    Skor yükseldikçe pozisyondan çıkma gereği artar. Motor yalnızca kârdaki
    işlemlerde aktif olur; stop, break-even ve hedef kontrollerinin önüne geçmez.
    """
    cfg = config or SmartExitConfig()

    if entry_price <= 0 or current_price <= 0:
        raise ValueError("entry_price ve current_price sıfırdan büyük olmalıdır.")

    profit_pct = ((current_price / entry_price) - 1.0) * 100.0

    def result(action: SmartExitAction, score: int, reasons: list[str]) -> SmartExitResult:
        return SmartExitResult(
            should_exit=action in (
                SmartExitAction.PARTIAL_EXIT,
                SmartExitAction.FULL_EXIT,
            ),
            action=action,
            status=(
                "SMART_EXIT"
                if action in (
                    SmartExitAction.PARTIAL_EXIT,
                    SmartExitAction.FULL_EXIT,
                )
                else action.value
            ),
            score=min(100, max(0, int(score))),
            confirmations=len(reasons),
            reasons=tuple(reasons),
            profit_pct=profit_pct,
        )

    if not cfg.enabled:
        return result(SmartExitAction.HOLD, 0, [])

    if profit_pct < cfg.min_profit_pct:
        base = result(SmartExitAction.HOLD, 0, [])
        return SmartExitResult(
            should_exit=False,
            action=base.action,
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
    elif current_rsi is not None and current_rsi < cfg.rsi_weak_level:
        score += cfg.rsi_weak_points
        reasons.append("RSI güç eşiğinin altında")

    if macd_hist is not None and macd_hist < 0:
        score += cfg.macd_negative_points
        reasons.append("MACD histogram negatif")

    if close_price is not None and ema20 is not None and close_price < ema20:
        score += cfg.ema20_break_points
        reasons.append("Fiyat EMA20 altında")

    if volume_ratio is not None and volume_ratio < cfg.weak_volume_ratio:
        score += cfg.weak_volume_points
        reasons.append("Hacim zayıfladı")

    if (
        current_adx is not None
        and previous_adx is not None
        and current_adx < previous_adx
    ):
        score += cfg.adx_weakening_points
        reasons.append("ADX zayıflıyor")

    if current_adx is not None and current_adx < cfg.weak_adx_level:
        score += cfg.adx_weak_points
        reasons.append("Trend gücü düşük")

    # Kâr koruma bağlamı, teknik bozulma varsa kararı bir kademe sıkılaştırır.
    if reasons and (break_even_active or trailing_active):
        score += cfg.profit_protection_points
        reasons.append("Kâr koruma modu aktif")

    if reasons and partial_stage > 0:
        score += cfg.partial_tp_protection_points
        reasons.append(f"TP{partial_stage} sonrası kalan pozisyon korunuyor")

    confirmations = len(reasons)
    if (
        score >= cfg.full_exit_score_threshold
        and confirmations >= cfg.full_exit_min_confirmations
    ):
        action = SmartExitAction.FULL_EXIT
    elif (
        score >= cfg.partial_exit_score_threshold
        and confirmations >= cfg.min_confirmations
    ):
        action = SmartExitAction.PARTIAL_EXIT
    elif score >= cfg.watch_score_threshold:
        action = SmartExitAction.TRAIL
    else:
        action = SmartExitAction.HOLD

    return result(action, score, reasons)
