from __future__ import annotations

from math import isfinite
from typing import Any, Mapping

import pandas as pd

from engine.signal_engine import evaluate
from engine.ai.confidence_engine import calculate_confidence


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if isfinite(number) else default


def _text(value: Any, default: str = "") -> str:
    result = str(value or default).strip()
    return result or default


def _label(score: float) -> str:
    if score >= 85:
        return "Çok Güçlü"
    if score >= 70:
        return "Güçlü"
    if score >= 55:
        return "Orta"
    if score >= 40:
        return "Zayıf"
    return "Riskli"


def _quality(score: float) -> str:
    if score >= 95:
        return "S"
    if score >= 90:
        return "A+"
    if score >= 85:
        return "A"
    if score >= 80:
        return "B+"
    if score >= 70:
        return "B"
    if score >= 60:
        return "C"
    return "D"


def _stars(score: float) -> str:
    if score >= 85:
        return "★★★★★"
    if score >= 70:
        return "★★★★☆"
    if score >= 55:
        return "★★★☆☆"
    if score >= 40:
        return "★★☆☆☆"
    return "★☆☆☆☆"


def _risk(confidence: float, risk_reward: float) -> str:
    if confidence >= 80 and risk_reward >= 2:
        return "Düşük"
    if confidence >= 60 and risk_reward >= 1.3:
        return "Orta"
    return "Yüksek"


def _probability(
    confidence: float,
    score: float,
    risk_reward: float,
    relative_strength: float | None,
) -> float:
    # Bu değer ilk sürümde kalibre edilmemiş bir başarı göstergesidir.
    value = confidence * 0.55 + score * 0.30
    value += min(max(risk_reward, 0), 3) / 3 * 10

    if relative_strength is not None:
        value += max(-5, min(5, relative_strength))

    return round(max(5, min(95, value)), 1)


def analyze_signal_payload(
    signal: Mapping[str, Any],
    *,
    participation: Mapping[str, Any] | None = None,
    relative_strength: float | None = None,
    volume_quality: float = 50,
    volatility_quality: float = 50,
    liquidity_quality: float = 50,
) -> dict[str, Any]:
    """Scanner/Robot gibi hazır sinyal sözlüklerini ortak analiz çıktısına çevirir."""

    score = _safe_float(signal.get("Puan", signal.get("score", 0)))
    decision = _text(signal.get("Karar", signal.get("decision", "BEKLE")))
    risk_reward = _safe_float(
        signal.get("R/K 1", signal.get("risk_reward1", 0))
    )

    confidence_result = calculate_confidence(
        signal={"Puan": score, "Karar": decision},
        participation=participation,
        volume_quality=_safe_float(volume_quality, 50),
        volatility_quality=_safe_float(volatility_quality, 50),
        liquidity_quality=_safe_float(liquidity_quality, 50),
    )

    if not isinstance(confidence_result, dict):
        confidence_result = {}

    confidence = _safe_float(
        confidence_result.get(
            "confidence",
            confidence_result.get("score", 0),
        )
    )
    confidence = round(max(0, min(100, confidence)), 1)
    confidence_label = _text(confidence_result.get("label"), _label(confidence))
    risk_level = _risk(confidence, risk_reward)

    relative_number = None
    if relative_strength is not None and not pd.isna(relative_strength):
        relative_number = _safe_float(relative_strength)

    probability = _probability(
        confidence,
        score,
        risk_reward,
        relative_number,
    )

    reasons = [
        f"{decision}: teknik puan {score:.0f}",
        f"güven {confidence:.0f}/100",
        f"risk {risk_level.lower()}",
    ]

    if relative_number is not None:
        if relative_number > 1:
            reasons.append("BIST'ten güçlü")
        elif relative_number < -1:
            reasons.append("BIST'ten zayıf")
        else:
            reasons.append("göreceli güç nötr")

    adx_value = signal.get("ADX", signal.get("adx"))
    if adx_value is not None and not pd.isna(adx_value):
        adx_number = _safe_float(adx_value)
        if adx_number >= 25:
            reasons.append("trend güçlü")
        elif adx_number < 18:
            reasons.append("trend zayıf")

    rsi_value = signal.get("RSI", signal.get("rsi"))
    if rsi_value is not None and not pd.isna(rsi_value):
        rsi_number = _safe_float(rsi_value)
        if rsi_number >= 70:
            reasons.append("RSI yüksek")
        elif rsi_number <= 35:
            reasons.append("RSI düşük")

    return {
        "confidence": confidence,
        "confidence_label": confidence_label,
        "confidence_stars": _stars(confidence),
        "quality": _quality(confidence),
        "risk_level": risk_level,
        "probability": probability,
        "summary": " • ".join(reasons),
        "confidence_breakdown": confidence_result.get("breakdown", {}),
        "confidence_raw": confidence_result,
    }


def analyze(
    frame: pd.DataFrame | None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Ham fiyat verisini Signal Engine üzerinden analiz eder."""

    signal = evaluate(frame)

    if not isinstance(signal, dict):
        return {
            "ok": False,
            "decision": "YETERSİZ VERİ",
            "summary": "Signal Engine geçerli sonuç döndürmedi.",
        }

    if not signal.get("ok", False):
        return {
            **signal,
            "confidence": 0.0,
            "confidence_label": "Riskli",
            "confidence_stars": "—",
            "risk_level": "Belirsiz",
            "probability": 0.0,
            "summary": _text(signal.get("reason"), "Analiz üretilemedi."),
        }

    enriched = analyze_signal_payload(signal, **kwargs)
    return {**signal, **enriched}
