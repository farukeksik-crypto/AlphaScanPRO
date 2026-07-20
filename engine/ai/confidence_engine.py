from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import math


@dataclass
class ConfidenceWeights:
    technical: float = 30.0
    backtest: float = 20.0
    robot: float = 15.0
    participation: float = 10.0
    market_regime: float = 10.0
    volume_quality: float = 5.0
    volatility: float = 5.0
    liquidity: float = 5.0

    def total(self) -> float:
        return (
            self.technical
            + self.backtest
            + self.robot
            + self.participation
            + self.market_regime
            + self.volume_quality
            + self.volatility
            + self.liquidity
        )


@dataclass
class ConfidenceConfig:
    weights: ConfidenceWeights = field(default_factory=ConfidenceWeights)
    minimum_sample_size: int = 20
    strong_sample_size: int = 50
    maximum_acceptable_drawdown: float = 15.0


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, value))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
        if math.isnan(numeric) or math.isinf(numeric):
            return default
        return numeric
    except (TypeError, ValueError):
        return default


def _scale(value: float, source_min: float, source_max: float) -> float:
    if source_max <= source_min:
        return 0.0
    normalized = (value - source_min) / (source_max - source_min)
    return _clamp(normalized * 100.0)


def _technical_score(signal: dict[str, Any]) -> tuple[float, list[str]]:
    raw_score = _safe_float(signal.get("Puan", signal.get("score", 0)))
    decision = str(signal.get("Karar", signal.get("decision", ""))).upper()

    score = _clamp(raw_score)

    if decision == "NET AL":
        score = min(100.0, score + 5.0)
    elif decision == "AL ADAY":
        score = max(0.0, score - 5.0)
    elif decision in {"IZLE", "İZLE"}:
        score = max(0.0, score - 15.0)
    elif decision == "BEKLE":
        score = max(0.0, score - 30.0)

    reasons = [f"Teknik skor {raw_score:.1f}"]
    if decision:
        reasons.append(f"Karar: {decision}")

    return score, reasons


def _backtest_score(
    stats: dict[str, Any],
    config: ConfidenceConfig,
) -> tuple[float, list[str]]:
    if not stats:
        return 50.0, ["Backtest geçmişi yok; nötr puan kullanıldı"]

    trades = int(_safe_float(stats.get("Toplam İşlem", stats.get("trades", 0))))
    win_rate = _safe_float(stats.get("Başarı Oranı %", stats.get("win_rate", 0)))
    profit_factor = _safe_float(stats.get("Kâr Faktörü", stats.get("profit_factor", 0)))
    max_drawdown = _safe_float(stats.get("Maksimum Düşüş %", stats.get("max_drawdown", 0)))
    health_score = _safe_float(stats.get("Sağlık Puanı", stats.get("health_score", 0)))

    sample_component = (
        100.0
        if trades >= config.strong_sample_size
        else _scale(trades, 0, config.strong_sample_size)
    )
    win_component = _scale(win_rate, 35.0, 70.0)
    pf_component = _scale(profit_factor, 0.75, 2.0)
    dd_component = 100.0 - _scale(
        max_drawdown,
        0.0,
        config.maximum_acceptable_drawdown * 1.5,
    )

    score = (
        sample_component * 0.20
        + win_component * 0.25
        + pf_component * 0.30
        + dd_component * 0.15
        + (_clamp(health_score) if health_score > 0 else 50.0) * 0.10
    )

    reasons = [
        f"Backtest işlemi: {trades}",
        f"Başarı oranı: %{win_rate:.1f}",
        f"Kâr faktörü: {profit_factor:.2f}",
        f"Maksimum düşüş: %{max_drawdown:.1f}",
    ]
    return _clamp(score), reasons


def _robot_score(
    stats: dict[str, Any],
    config: ConfidenceConfig,
) -> tuple[float, list[str]]:
    if not stats:
        return 50.0, ["Robot geçmişi yok; nötr puan kullanıldı"]

    trades = int(_safe_float(stats.get("trades", stats.get("Toplam İşlem", 0))))
    win_rate = _safe_float(stats.get("win_rate", stats.get("Başarı Oranı %", 0)))
    profit_factor = _safe_float(stats.get("profit_factor", stats.get("Kâr Faktörü", 0)))
    total_return = _safe_float(stats.get("return_pct", stats.get("Toplam Getiri %", 0)))

    sample_component = (
        100.0
        if trades >= config.strong_sample_size
        else _scale(trades, 0, config.strong_sample_size)
    )
    win_component = _scale(win_rate, 35.0, 70.0)
    pf_component = _scale(profit_factor, 0.75, 2.0)
    return_component = _scale(total_return, -5.0, 15.0)

    score = (
        sample_component * 0.25
        + win_component * 0.30
        + pf_component * 0.30
        + return_component * 0.15
    )

    reasons = [
        f"Robot işlemi: {trades}",
        f"Robot başarı oranı: %{win_rate:.1f}",
        f"Robot kâr faktörü: {profit_factor:.2f}",
        f"Robot getirisi: %{total_return:.1f}",
    ]
    return _clamp(score), reasons


def _participation_score(
    participation: dict[str, Any] | None,
) -> tuple[float, list[str]]:
    if not participation:
        return 50.0, ["Katılım bilgisi yok; nötr puan kullanıldı"]

    compliant = bool(
        participation.get("uygun", participation.get("compliant", False))
    )
    purification = participation.get(
        "arindirma",
        participation.get("purification_pct"),
    )

    if not compliant:
        return 0.0, ["Katılım kriterlerine uygun değil"]

    if purification is None:
        return 80.0, ["Katılım endeksinde; arındırma oranı bilinmiyor"]

    purification_value = _safe_float(purification)
    score = 100.0 - _scale(purification_value, 0.0, 10.0)

    reasons = [
        "Katılım kriterlerine uygun",
        f"Arındırma oranı: %{purification_value:.2f}",
    ]
    return _clamp(score), reasons


def _market_regime_score(
    regime: dict[str, Any] | None,
) -> tuple[float, list[str]]:
    if not regime:
        return 50.0, ["Piyasa rejimi bilgisi yok; nötr puan kullanıldı"]

    trend = str(regime.get("trend", "")).lower()
    risk = str(regime.get("risk", "")).lower()
    benchmark_above_ema200 = regime.get("above_ema200")
    volatility = str(regime.get("volatility", "")).lower()

    score = 50.0
    reasons: list[str] = []

    if trend in {"strong_up", "güçlü yükseliş", "guclu yukselis"}:
        score += 30
        reasons.append("Piyasa güçlü yükselişte")
    elif trend in {"up", "yükseliş", "yukselis"}:
        score += 20
        reasons.append("Piyasa yükselişte")
    elif trend in {"sideways", "yatay"}:
        score -= 5
        reasons.append("Piyasa yatay")
    elif trend in {"down", "düşüş", "dusus"}:
        score -= 25
        reasons.append("Piyasa düşüşte")
    elif trend in {"strong_down", "güçlü düşüş", "guclu dusus"}:
        score -= 40
        reasons.append("Piyasa güçlü düşüşte")

    if benchmark_above_ema200 is True:
        score += 10
        reasons.append("Ana endeks EMA200 üzerinde")
    elif benchmark_above_ema200 is False:
        score -= 15
        reasons.append("Ana endeks EMA200 altında")

    if risk in {"low", "düşük", "dusuk"}:
        score += 10
    elif risk in {"high", "yüksek", "yuksek"}:
        score -= 20

    if volatility in {"high", "yüksek", "yuksek"}:
        score -= 10
        reasons.append("Volatilite yüksek")

    return _clamp(score), reasons


def _quality_score(
    value: Any,
    default: float = 50.0,
) -> tuple[float, list[str]]:
    if value is None:
        return default, ["Veri yok; nötr puan kullanıldı"]

    if isinstance(value, dict):
        raw = value.get("score", value.get("value", default))
        note = value.get("reason")
        score = _clamp(_safe_float(raw, default))
        return score, [str(note)] if note else []

    return _clamp(_safe_float(value, default)), []


def calculate_confidence(
    *,
    signal: dict[str, Any],
    backtest_stats: dict[str, Any] | None = None,
    robot_stats: dict[str, Any] | None = None,
    participation: dict[str, Any] | None = None,
    market_regime: dict[str, Any] | None = None,
    volume_quality: Any = None,
    volatility_quality: Any = None,
    liquidity_quality: Any = None,
    config: ConfidenceConfig | None = None,
) -> dict[str, Any]:
    config = config or ConfidenceConfig()
    weights = config.weights

    if weights.total() <= 0:
        raise ValueError("Güven puanı ağırlıklarının toplamı sıfır olamaz.")

    technical, technical_reasons = _technical_score(signal)
    backtest, backtest_reasons = _backtest_score(backtest_stats or {}, config)
    robot, robot_reasons = _robot_score(robot_stats or {}, config)
    participation_score, participation_reasons = _participation_score(participation)
    regime, regime_reasons = _market_regime_score(market_regime)
    volume, volume_reasons = _quality_score(volume_quality)
    volatility, volatility_reasons = _quality_score(volatility_quality)
    liquidity, liquidity_reasons = _quality_score(liquidity_quality)

    components = {
        "technical": {
            "score": technical,
            "weight": weights.technical,
            "reasons": technical_reasons,
        },
        "backtest": {
            "score": backtest,
            "weight": weights.backtest,
            "reasons": backtest_reasons,
        },
        "robot": {
            "score": robot,
            "weight": weights.robot,
            "reasons": robot_reasons,
        },
        "participation": {
            "score": participation_score,
            "weight": weights.participation,
            "reasons": participation_reasons,
        },
        "market_regime": {
            "score": regime,
            "weight": weights.market_regime,
            "reasons": regime_reasons,
        },
        "volume_quality": {
            "score": volume,
            "weight": weights.volume_quality,
            "reasons": volume_reasons,
        },
        "volatility": {
            "score": volatility,
            "weight": weights.volatility,
            "reasons": volatility_reasons,
        },
        "liquidity": {
            "score": liquidity,
            "weight": weights.liquidity,
            "reasons": liquidity_reasons,
        },
    }

    weighted_sum = sum(
        item["score"] * item["weight"] for item in components.values()
    )
    confidence = round(_clamp(weighted_sum / weights.total()), 1)

    if confidence >= 85:
        label = "Çok Güçlü"
    elif confidence >= 75:
        label = "Güçlü"
    elif confidence >= 65:
        label = "Orta"
    elif confidence >= 50:
        label = "Zayıf"
    else:
        label = "Riskli"

    positive_reasons: list[str] = []
    warning_reasons: list[str] = []

    for item in components.values():
        score = float(item["score"])
        reasons = [reason for reason in item["reasons"] if reason]

        if score >= 70:
            positive_reasons.extend(reasons)
        elif score < 45:
            warning_reasons.extend(reasons)

    return {
        "confidence": confidence,
        "label": label,
        "components": components,
        "positive_reasons": positive_reasons,
        "warning_reasons": warning_reasons,
    }