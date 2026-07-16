from __future__ import annotations

from typing import Any

import pandas as pd

from engine.indicators import (
    adx,
    atr,
    bollinger_bands,
    ema,
    macd,
    rsi,
    vwap,
)
from engine.signal_engine import evaluate


MIN_CHART_BARS = 50


def prepare_chart_data(frame: pd.DataFrame) -> dict[str, Any]:
    """
    Grafik ekranı için fiyat verilerini ve teknik göstergeleri hazırlar.
    """

    if frame is None or frame.empty:
        return {
            "ok": False,
            "error": "Grafik için veri bulunamadı.",
            "data": pd.DataFrame(),
            "signal": {},
        }

    if len(frame) < MIN_CHART_BARS:
        return {
            "ok": False,
            "error": (
                f"Grafik için yetersiz veri: {len(frame)} mum var. "
                f"En az {MIN_CHART_BARS} mum gerekli."
            ),
            "data": pd.DataFrame(),
            "signal": {},
        }

    data = frame.copy()
    data = data[~data.index.duplicated(keep="last")].sort_index()

    required_columns = [
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in data.columns
    ]

    if missing_columns:
        return {
            "ok": False,
            "error": (
                "Eksik grafik sütunları: "
                + ", ".join(missing_columns)
            ),
            "data": pd.DataFrame(),
            "signal": {},
        }

    for column in required_columns:
        data[column] = pd.to_numeric(
            data[column],
            errors="coerce",
        )

    data = data.dropna(
        subset=["Open", "High", "Low", "Close"]
    )

    if data.empty:
        return {
            "ok": False,
            "error": "Geçerli fiyat verisi bulunamadı.",
            "data": pd.DataFrame(),
            "signal": {},
        }

    # Trend göstergeleri
    data["EMA20"] = ema(data["Close"], 20)
    data["EMA50"] = ema(data["Close"], 50)
    data["EMA200"] = ema(data["Close"], 200)

    # Momentum göstergeleri
    data["RSI"] = rsi(data["Close"])

    (
        data["MACD"],
        data["MACD_SIGNAL"],
        data["MACD_HIST"],
    ) = macd(data["Close"])

    # Volatilite ve trend gücü
    data["ATR"] = atr(data)

    plus_di, minus_di, adx_value = adx(data)

    data["PLUS_DI"] = plus_di
    data["MINUS_DI"] = minus_di
    data["ADX"] = adx_value

    # Bollinger
    (
        data["BOLLINGER_UPPER"],
        data["BOLLINGER_MIDDLE"],
        data["BOLLINGER_LOWER"],
    ) = bollinger_bands(data["Close"])

    # VWAP
    data["VWAP"] = vwap(data)

    # Hacim ortalaması
    data["VOLUME_MA20"] = (
        data["Volume"]
        .rolling(20)
        .mean()
    )

    signal = evaluate(data)

    latest = data.iloc[-1]

    latest_values = {
        "price": _safe_float(latest.get("Close")),
        "ema20": _safe_float(latest.get("EMA20")),
        "ema50": _safe_float(latest.get("EMA50")),
        "ema200": _safe_float(latest.get("EMA200")),
        "vwap": _safe_float(latest.get("VWAP")),
        "rsi": _safe_float(latest.get("RSI")),
        "adx": _safe_float(latest.get("ADX")),
        "atr": _safe_float(latest.get("ATR")),
        "macd": _safe_float(latest.get("MACD")),
        "macd_signal": _safe_float(
            latest.get("MACD_SIGNAL")
        ),
        "volume": _safe_float(latest.get("Volume")),
        "volume_ma20": _safe_float(
            latest.get("VOLUME_MA20")
        ),
    }

    return {
        "ok": True,
        "error": None,
        "data": data,
        "signal": signal,
        "latest": latest_values,
    }


def _safe_float(value) -> float | None:
    if value is None:
        return None

    if pd.isna(value):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None