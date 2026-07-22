from __future__ import annotations

import pandas as pd

from engine.multi_timeframe_intelligence import MultiTimeframeIntelligence


def regime(name: str, score: float, confidence: float = 80.0, allow: bool = True):
    return {"regime": name, "score": score, "confidence": confidence, "allow_new_positions": allow}


def test_aligned_bull_timeframes_allow_normal_risk():
    result = MultiTimeframeIntelligence().analyze_results({
        "15m": regime("RECOVERY", 70), "1h": regime("BULL", 85),
        "4h": regime("BULL", 88), "1d": regime("BULL", 90),
    })
    assert result.allow_new_positions is True
    assert result.dominant_regime == "BULL"
    assert result.conflict_level == "LOW"
    assert result.position_size_multiplier > 0.9


def test_higher_timeframes_bear_lock_new_trade():
    result = MultiTimeframeIntelligence().analyze_results({
        "15m": regime("BULL", 85), "1h": regime("RECOVERY", 70),
        "4h": regime("BEAR", 15, allow=False), "1d": regime("WEAK", 30, allow=False),
    })
    assert result.allow_new_positions is False
    assert result.position_size_multiplier == 0
    assert result.conflict_level == "HIGH"


def test_medium_confidence_reduces_size_and_raises_score():
    result = MultiTimeframeIntelligence().analyze_results({
        "15m": regime("RECOVERY", 68, 65), "1h": regime("RECOVERY", 70, 65),
        "4h": regime("BULL", 82, 65), "1d": regime("RECOVERY", 72, 65),
    })
    assert result.allow_new_positions is True
    assert result.position_size_multiplier <= 0.8
    assert result.minimum_entry_score_delta >= 3


def test_single_timeframe_is_not_enough():
    result = MultiTimeframeIntelligence().analyze_results({"1h": regime("BULL", 90)})
    assert result.allow_new_positions is False
    assert result.recommendation == "İŞLEM YOK"


def test_analyze_frames_accepts_raw_ohlcv():
    import numpy as np
    close = pd.Series([100 + i * 0.18 + np.sin(i / 4) * 2.0 for i in range(260)], dtype=float)
    frame = pd.DataFrame({
        "open": close - 0.1, "high": close + 0.5, "low": close - 0.5,
        "close": close, "volume": [1000 + i for i in range(260)],
    })
    result = MultiTimeframeIntelligence().analyze_frames({"1h": frame, "4h": frame, "1d": frame})
    assert len(result.timeframes) == 3
    assert result.confidence > 0
