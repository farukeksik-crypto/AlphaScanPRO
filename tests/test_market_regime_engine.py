from __future__ import annotations

import pandas as pd

from engine.market_regime_engine import MarketRegimeEngine


def _frame(
    close: float,
    ema20: float,
    ema50: float,
    ema200: float,
    rsi: float,
    adx: float,
    macd_hist: float,
    atr: float,
) -> pd.DataFrame:
    rows = []
    for index in range(30):
        slope = 1 + index * 0.001
        rows.append(
            {
                "close": close * slope,
                "ema20": ema20 * slope,
                "ema50": ema50,
                "ema200": ema200,
                "rsi": rsi,
                "adx": adx,
                "macd_hist": macd_hist,
                "atr": atr,
            }
        )
    return pd.DataFrame(rows)


def test_bull_regime() -> None:
    result = MarketRegimeEngine().analyze(
        _frame(120, 115, 105, 95, 58, 28, 2.0, 2.0)
    )
    assert result.regime in {"BULL", "RECOVERY"}
    assert result.allow_new_positions is True
    assert result.risk_multiplier > 0


def test_bear_regime() -> None:
    result = MarketRegimeEngine().analyze(
        _frame(80, 85, 95, 105, 30, 14, -2.0, 5.0)
    )
    assert result.regime in {"BEAR", "WEAK"}
    assert result.risk_multiplier <= 0.35


def test_missing_data_fallback() -> None:
    result = MarketRegimeEngine().analyze(pd.DataFrame())
    assert result.regime == "YETERSİZ VERİ"
    assert result.allow_new_positions is False
