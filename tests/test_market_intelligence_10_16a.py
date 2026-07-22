from __future__ import annotations

import numpy as np
import pandas as pd

from engine.market_regime_engine import MarketRegimeEngine


def _ohlcv(up: bool = True, volatility: float = 1.0, rows: int = 260) -> pd.DataFrame:
    trend = np.linspace(100, 150 if up else 65, rows)
    wave = np.sin(np.arange(rows) / 5) * volatility
    close = trend + wave
    return pd.DataFrame({
        "Open": close - 0.2,
        "High": close + volatility,
        "Low": close - volatility,
        "Close": close,
        "Volume": np.linspace(1000, 1600, rows),
    })


def test_raw_ohlcv_is_prepared_and_analyzed() -> None:
    result = MarketRegimeEngine().analyze_market_data(_ohlcv(up=True))
    assert result.regime in {"BULL", "RECOVERY"}
    assert result.recommendation in {"NORMAL", "TEMKİNLİ"}
    assert result.trend_strength > 0
    assert result.liquidity_score > 0


def test_extreme_volatility_reduces_risk() -> None:
    engine = MarketRegimeEngine()
    normal = engine.analyze_market_data(_ohlcv(up=True, volatility=1.0))
    extreme = engine.analyze_market_data(_ohlcv(up=True, volatility=12.0))
    assert extreme.volatility_level in {"HIGH", "EXTREME"}
    assert extreme.risk_multiplier <= normal.risk_multiplier


def test_result_dictionary_contains_intelligence_fields() -> None:
    data = MarketRegimeEngine().analyze_market_data(_ohlcv()).to_dict()
    for key in ("volatility_level", "trend_strength", "momentum_score", "liquidity_score", "recommendation"):
        assert key in data


def test_missing_raw_data_is_safe() -> None:
    result = MarketRegimeEngine().analyze_market_data(pd.DataFrame())
    assert result.regime == "YETERSİZ VERİ"
    assert result.allow_new_positions is False
