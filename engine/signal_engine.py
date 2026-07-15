from __future__ import annotations

import pandas as pd

from engine.indicators import adx, atr, ema, macd, rsi


MIN_BARS = 220


def evaluate(frame: pd.DataFrame) -> dict:
    if frame is None or len(frame) < MIN_BARS:
        return {
            "ok": False,
            "decision": "YETERSIZ VERI",
            "score": 0.0,
            "reason": f"{len(frame) if frame is not None else 0} mum",
        }

    data = frame.copy()
    data["EMA20"] = ema(data["Close"], 20)
    data["EMA50"] = ema(data["Close"], 50)
    data["EMA200"] = ema(data["Close"], 200)
    data["RSI"] = rsi(data["Close"])
    data["MACD"], data["MACD_SIGNAL"], data["MACD_HIST"] = macd(data["Close"])
    data["ATR"] = atr(data)
    plus_di, minus_di, adx_value = adx(data)
    data["PLUS_DI"] = plus_di
    data["MINUS_DI"] = minus_di
    data["ADX"] = adx_value
    data["VOLUME_MA"] = data["Volume"].rolling(20).mean()

    row = data.iloc[-1]
    score = 0.0
    reasons = []

    if row["EMA50"] > row["EMA200"]:
        score += 24
        reasons.append("EMA50 > EMA200")
    if row["Close"] > row["EMA50"]:
        score += 14
        reasons.append("Fiyat EMA50 üstünde")
    if row["EMA20"] > row["EMA50"]:
        score += 10
        reasons.append("Kısa trend güçlü")
    if 42 <= row["RSI"] <= 65:
        score += 16
        reasons.append("RSI uygun")
    if row["MACD_HIST"] > 0:
        score += 14
        reasons.append("MACD pozitif")
    if row["ADX"] >= 18 and row["PLUS_DI"] > row["MINUS_DI"]:
        score += 12
        reasons.append("ADX yön onayı")
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

    price = float(row["Close"])
    atr_value = float(row["ATR"]) if pd.notna(row["ATR"]) else 0.0
    stop = price - atr_value * 2
    target = price + atr_value * 3

    return {
        "ok": True,
        "decision": decision,
        "score": round(score, 1),
        "price": round(price, 4),
        "stop": round(stop, 4),
        "target": round(target, 4),
        "rsi": round(float(row["RSI"]), 2),
        "adx": round(float(row["ADX"]), 2),
        "reason": ", ".join(reasons) if reasons else "Koşul yok",
    }
