from __future__ import annotations

import pytest

from engine.portfolio_engine import (
    PortfolioConfig,
    PortfolioEngine,
    PortfolioPosition,
)


def sample_positions() -> list[PortfolioPosition]:
    return [
        PortfolioPosition(
            symbol="BTC/USDT",
            market="CRYPTO",
            quantity=0.10,
            entry_price=50_000,
            current_price=52_000,
            stop_price=48_000,
            sector="MAJOR",
        ),
        PortfolioPosition(
            symbol="ETH/USDT",
            market="CRYPTO",
            quantity=2,
            entry_price=3_000,
            current_price=3_100,
            stop_price=2_800,
            sector="SMART_CONTRACT",
        ),
    ]


def test_position_metrics() -> None:
    position = sample_positions()[0]

    assert position.market_value == 5_200
    assert position.cost_value == 5_000
    assert position.unrealized_pnl == 200
    assert position.risk_amount == 200


def test_exposure_and_weights() -> None:
    engine = PortfolioEngine(positions=sample_positions())

    assert engine.total_market_value() == 11_400
    assert engine.total_unrealized_pnl() == 400
    assert engine.total_risk_amount() == 600
    assert engine.exposure_by_market()["CRYPTO"] == 11_400

    weights = engine.weights(equity=100_000)
    assert weights["total_exposure_pct"] == 11.4


def test_asset_and_market_limits() -> None:
    engine = PortfolioEngine(
        PortfolioConfig(
            max_asset_weight_pct=10,
            max_market_weight_pct=15,
            max_sector_weight_pct=20,
            max_total_exposure_pct=30,
        ),
        positions=sample_positions(),
    )

    asset_block = engine.check_capacity(
        equity=100_000,
        candidate=PortfolioPosition(
            symbol="BTC/USDT",
            market="CRYPTO",
            quantity=100,
            entry_price=100,
            current_price=100,
            sector="MAJOR",
        ),
    )

    market_block = engine.check_capacity(
        equity=100_000,
        candidate=PortfolioPosition(
            symbol="SOL/USDT",
            market="CRYPTO",
            quantity=50,
            entry_price=100,
            current_price=100,
            sector="SMART_CONTRACT",
        ),
    )

    assert asset_block.code == "MAX_ASSET_WEIGHT"
    assert market_block.code == "MAX_MARKET_WEIGHT"


def test_sector_and_total_exposure_limits() -> None:
    engine = PortfolioEngine(
        PortfolioConfig(
            max_asset_weight_pct=50,
            max_market_weight_pct=100,
            max_sector_weight_pct=10,
            max_total_exposure_pct=15,
        ),
        positions=sample_positions(),
    )

    sector_block = engine.check_capacity(
        equity=100_000,
        candidate=PortfolioPosition(
            symbol="BNB/USDT",
            market="CRYPTO",
            quantity=80,
            entry_price=100,
            current_price=100,
            sector="SMART_CONTRACT",
        ),
    )

    total_block = engine.check_capacity(
        equity=100_000,
        candidate=PortfolioPosition(
            symbol="XAUUSD",
            market="COMMODITY",
            quantity=50,
            entry_price=100,
            current_price=100,
            sector="METAL",
        ),
    )

    assert sector_block.code == "MAX_SECTOR_WEIGHT"
    assert total_block.code == "MAX_TOTAL_EXPOSURE"


def test_correlation_limit() -> None:
    engine = PortfolioEngine(
        PortfolioConfig(
            max_correlated_positions=2,
            correlation_threshold=0.80,
        ),
        positions=sample_positions(),
    )

    decision = engine.check_correlation(
        candidate_symbol="SOL/USDT",
        correlations={
            "BTC/USDT": 0.91,
            "ETH/USDT": 0.88,
        },
    )

    assert decision.allowed is False
    assert decision.code == "CORRELATION_LIMIT"


def test_candidate_approval_and_report() -> None:
    engine = PortfolioEngine(
        PortfolioConfig(
            max_open_positions=5,
            max_asset_weight_pct=25,
            max_market_weight_pct=70,
            max_sector_weight_pct=35,
            max_total_exposure_pct=95,
            max_correlated_positions=2,
        ),
        positions=sample_positions(),
    )

    candidate = PortfolioPosition(
        symbol="GC=F",
        market="COMMODITY",
        quantity=1,
        entry_price=2_000,
        current_price=2_000,
        stop_price=1_950,
        sector="METAL",
    )

    result = engine.evaluate_candidate(
        equity=100_000,
        candidate=candidate,
        correlations={
            "BTC/USDT": 0.10,
            "ETH/USDT": 0.12,
        },
    )
    report = engine.portfolio_report(
        equity=100_000,
        cash=88_600,
    )

    assert result["allowed"] is True
    assert result["stage"] == "approved"
    assert report["position_count"] == 2
    assert report["weights"]["total_exposure_pct"] == 11.4


def test_add_remove_and_validation() -> None:
    engine = PortfolioEngine()
    engine.add_position(sample_positions()[0])

    assert len(engine.list_positions()) == 1
    assert engine.remove_position("BTC/USDT") == 1
    assert len(engine.list_positions()) == 0

    with pytest.raises(ValueError):
        engine.add_position(
            PortfolioPosition(
                symbol="",
                market="CRYPTO",
                quantity=1,
                entry_price=100,
                current_price=100,
            )
        )
