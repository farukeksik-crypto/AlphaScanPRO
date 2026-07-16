from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def rsi(series: pd.Series, length: int = 14) -> pd.Series:
    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(
        alpha=1 / length,
        adjust=False,
        min_periods=length,
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / length,
        adjust=False,
        min_periods=length,
    ).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)

    return 100 - (100 / (1 + rs))


def macd(
    series: pd.Series,
    fast_length: int = 12,
    slow_length: int = 26,
    signal_length: int = 9,
):
    fast = ema(series, fast_length)
    slow = ema(series, slow_length)

    line = fast - slow
    signal = ema(line, signal_length)
    histogram = line - signal

    return line, signal, histogram


def atr(
    frame: pd.DataFrame,
    length: int = 14,
) -> pd.Series:
    high = frame["High"]
    low = frame["Low"]
    close = frame["Close"]

    true_range = pd.concat(
        [
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)

    return true_range.ewm(
        alpha=1 / length,
        adjust=False,
        min_periods=length,
    ).mean()


def adx(
    frame: pd.DataFrame,
    length: int = 14,
):
    high = frame["High"]
    low = frame["Low"]
    close = frame["Close"]

    true_range = pd.concat(
        [
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr_value = true_range.ewm(
        alpha=1 / length,
        adjust=False,
        min_periods=length,
    ).mean()

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(
        np.where(
            (up_move > down_move) & (up_move > 0),
            up_move,
            0.0,
        ),
        index=frame.index,
    )

    minus_dm = pd.Series(
        np.where(
            (down_move > up_move) & (down_move > 0),
            down_move,
            0.0,
        ),
        index=frame.index,
    )

    plus_di = (
        100
        * plus_dm.ewm(
            alpha=1 / length,
            adjust=False,
            min_periods=length,
        ).mean()
        / atr_value
    )

    minus_di = (
        100
        * minus_dm.ewm(
            alpha=1 / length,
            adjust=False,
            min_periods=length,
        ).mean()
        / atr_value
    )

    denominator = (plus_di + minus_di).replace(0, np.nan)

    dx = (
        (plus_di - minus_di).abs()
        / denominator
        * 100
    )

    adx_value = dx.ewm(
        alpha=1 / length,
        adjust=False,
        min_periods=length,
    ).mean()

    return plus_di, minus_di, adx_value


def bollinger_bands(
    series: pd.Series,
    length: int = 20,
    standard_deviation: float = 2.0,
):
    middle = series.rolling(length).mean()
    deviation = series.rolling(length).std(ddof=0)

    upper = middle + deviation * standard_deviation
    lower = middle - deviation * standard_deviation

    return upper, middle, lower


def vwap(frame: pd.DataFrame) -> pd.Series:
    typical_price = (
        frame["High"]
        + frame["Low"]
        + frame["Close"]
    ) / 3

    cumulative_volume = frame["Volume"].cumsum()

    return (
        typical_price.mul(frame["Volume"]).cumsum()
        / cumulative_volume.replace(0, np.nan)
    )