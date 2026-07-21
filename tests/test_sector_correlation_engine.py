from __future__ import annotations

import numpy as np
import pandas as pd

from engine.sector_correlation_engine import SectorCorrelationEngine


def _prices(seed: int, size: int = 80) -> pd.Series:
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.001, 0.01, size=size)
    return pd.Series(100 * np.cumprod(1 + returns))


def test_sector_limit_blocks_candidate() -> None:
    engine = SectorCorrelationEngine(max_sector_positions=2)
    positions = [
        {"symbol": "AKBNK", "sector": "BANKA"},
        {"symbol": "GARAN", "sector": "BANKA"},
    ]

    result = engine.check_candidate(
        symbol="YKBNK",
        sector="BANKA",
        open_positions=positions,
    )

    assert result.allowed is False
    assert result.sector_position_count == 2


def test_low_correlation_candidate_allowed() -> None:
    engine = SectorCorrelationEngine(
        max_sector_positions=3,
        correlation_limit=0.85,
        min_observations=30,
    )
    candidate = _prices(1)
    other = _prices(2)

    result = engine.check_candidate(
        symbol="AAA",
        sector="SANAYI",
        open_positions=[{"symbol": "BBB", "sector": "TEKNOLOJI"}],
        candidate_prices=candidate,
        position_price_map={"BBB": other},
    )

    assert result.allowed is True
    assert result.highest_correlation < 0.85


def test_high_correlation_candidate_blocked() -> None:
    engine = SectorCorrelationEngine(
        max_sector_positions=3,
        correlation_limit=0.80,
        min_observations=30,
    )
    candidate = _prices(4)
    nearly_same = candidate * 1.02

    result = engine.check_candidate(
        symbol="AAA",
        sector="SANAYI",
        open_positions=[{"symbol": "BBB", "sector": "TEKNOLOJI"}],
        candidate_prices=candidate,
        position_price_map={"BBB": nearly_same},
    )

    assert result.allowed is False
    assert result.highest_correlated_symbol == "BBB"
    assert result.highest_correlation >= 0.80


def test_correlation_matrix() -> None:
    engine = SectorCorrelationEngine(min_observations=20)
    matrix = engine.build_correlation_matrix(
        {
            "AAA": _prices(10),
            "BBB": _prices(11),
            "CCC": _prices(12),
        }
    )

    assert list(matrix.columns) == ["AAA", "BBB", "CCC"]
    assert matrix.shape == (3, 3)
