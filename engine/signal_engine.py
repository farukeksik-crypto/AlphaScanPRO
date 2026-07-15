from __future__ import annotations

import pandas as pd

from engine.indicators import adx, atr, ema, macd, rsi
from engine.score_engine import calculate_score


MIN_BARS = 220


def evaluate(frame: pd.DataFrame) -> dict:
    if frame is None or len(frame) < MIN_BARS:
        return {
            "ok": False,
            "decision": "YETERSIZ VERI",
            "quality": "D",
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

    score_result = calculate_score(row)
    score = score_result["score"]
    decision = score_result["decision"]
    quality = score_result["quality"]

    price = float(row["Close"])
    atr_value = float(row["ATR"]) if pd.notna(row["ATR"]) else 0.0
    stop = price - atr_value * 2
    target = price + atr_value * 3

    return {
        "ok": True,
        "decision": decision,
        "quality": quality,
        "score": round(score, 1),
        "price": round(price, 4),
        "stop": round(stop, 4),
        "target": round(target, 4),
        "rsi": round(float(row["RSI"]), 2),
        "adx": round(float(row["ADX"]), 2),
        "reason": score_result["reason"],
    }