from __future__ import annotations

from typing import Any

import pandas as pd


def calculate_score(row: pd.Series) -> dict[str, Any]:
    score = 0.0
    reasons: list[str] = []

    if pd.notna(row.get("EMA50")) and pd.notna(row.get("EMA200")):
        if row["EMA50"] > row["EMA200"]:
            score += 24
            reasons.append("EMA50 > EMA200")

    if pd.notna(row.get("Close")) and pd.notna(row.get("EMA50")):
        if row["Close"] > row["EMA50"]:
            score += 14
            reasons.append("Fiyat EMA50 üstünde")

    if pd.notna(row.get("EMA20")) and pd.notna(row.get("EMA50")):
        if row["EMA20"] > row["EMA50"]:
            score += 10
            reasons.append("Kısa trend güçlü")

    if pd.notna(row.get("RSI")):
        if 42 <= row["RSI"] <= 65:
            score += 16
            reasons.append("RSI uygun")

    if pd.notna(row.get("MACD_HIST")):
        if row["MACD_HIST"] > 0:
            score += 14
            reasons.append("MACD pozitif")

    adx_valid = all(
        pd.notna(row.get(column))
        for column in ("ADX", "PLUS_DI", "MINUS_DI")
    )

    if adx_valid:
        if row["ADX"] >= 18 and row["PLUS_DI"] > row["MINUS_DI"]:
            score += 12
            reasons.append("ADX yön onayı")

    volume_valid = all(
        pd.notna(row.get(column))
        for column in ("Volume", "VOLUME_MA")
    )

    if volume_valid and row["VOLUME_MA"] > 0:
        if row["Volume"] >= row["VOLUME_MA"] * 0.85:
            score += 10
            reasons.append("Hacim yeterli")

    score = min(score, 100.0)

    if score >= 75:
        decision = "NET AL"
    elif score >= 62:
        decision = "AL ADAY"
    elif score >= 50:
        decision = "IZLE"
    else:
        decision = "BEKLE"

    if score >= 90:
        quality = "A+"
    elif score >= 80:
        quality = "A"
    elif score >= 70:
        quality = "B"
    elif score >= 60:
        quality = "C"
    else:
        quality = "D"

    return {
        "score": round(score, 1),
        "decision": decision,
        "quality": quality,
        "reasons": reasons,
        "reason": ", ".join(reasons) if reasons else "Koşul yok",
    }