from __future__ import annotations

from engine.portfolio_engine import (
    PortfolioConfig,
    PortfolioEngine,
    PortfolioPosition,
)
from engine.risk_core import RiskConfig, RiskCore
from engine.trade_gate import TradeCandidate, UnifiedTradeGate


def build_gate(
    positions: list[PortfolioPosition] | None = None,
) -> UnifiedTradeGate:
    risk_core = RiskCore(
        RiskConfig(
            risk_per_trade_pct=1.0,
            max_daily_loss_pct=3.0,
            max_daily_trades=8,
            max_consecutive_losses=3,
            max_open_positions=5,
            max_total_risk_pct=5.0,
            min_stop_distance_pct=0.1,
            max_stop_distance_pct=15.0,
            equity_floor_pct=80.0,
        )
    )
    portfolio = PortfolioEngine(
        PortfolioConfig(
            max_open_positions=5,
            max_asset_weight_pct=25.0,
            max_market_weight_pct=70.0,
            max_sector_weight_pct=35.0,
            max_total_exposure_pct=95.0,
            max_correlated_positions=2,
            correlation_threshold=0.80,
        ),
        positions=positions or [],
    )
    return UnifiedTradeGate(
        risk_core=risk_core,
        portfolio_engine=portfolio,
    )


def candidate() -> TradeCandidate:
    return TradeCandidate(
        symbol="BTC/USDT",
        market="CRYPTO",
        quantity=10,
        entry_price=100,
        current_price=100,
        stop_price=95,
        sector="MAJOR",
        signal_score=70,
        minimum_signal_score=60,
    )


def default_kwargs() -> dict:
    return {
        "initial_equity": 100_000,
        "starting_equity": 100_000,
        "current_equity": 100_000,
        "daily_trade_count": 1,
        "consecutive_losses": 0,
        "current_total_risk_pct": 1.0,
        "available_cash": 50_000,
        "correlations": {},
    }


def test_signal_rejection() -> None:
    gate = build_gate()
    item = candidate()
    item.signal_score = 50

    result = gate.evaluate_trade(candidate=item, **default_kwargs())

    assert result.allowed is False
    assert result.code == "SIGNAL_SCORE_TOO_LOW"
    assert result.stage == "signal"


def test_risk_rejection() -> None:
    gate = build_gate()
    kwargs = default_kwargs()
    kwargs["current_equity"] = 96_000

    result = gate.evaluate_trade(candidate=candidate(), **kwargs)

    assert result.allowed is False
    assert result.code == "DAILY_LOSS_LIMIT"
    assert result.stage.startswith("risk:")


def test_portfolio_rejection() -> None:
    positions = [
        PortfolioPosition(
            symbol="ETH/USDT",
            market="CRYPTO",
            quantity=100,
            entry_price=100,
            current_price=100,
            stop_price=95,
            sector="SMART_CONTRACT",
        ),
        PortfolioPosition(
            symbol="SOL/USDT",
            market="CRYPTO",
            quantity=100,
            entry_price=100,
            current_price=100,
            stop_price=95,
            sector="LAYER1",
        ),
    ]
    gate = build_gate(positions=positions)
    item = candidate()
    item.symbol = "BNB/USDT"
    item.sector = "SMART_CONTRACT"

    kwargs = default_kwargs()
    kwargs["correlations"] = {
        "ETH/USDT": 0.90,
        "SOL/USDT": 0.88,
    }

    result = gate.evaluate_trade(candidate=item, **kwargs)

    assert result.allowed is False
    assert result.code == "CORRELATION_LIMIT"
    assert result.stage == "portfolio:correlation"


def test_approval_uses_risk_sized_quantity() -> None:
    gate = build_gate()
    item = candidate()
    item.quantity = 1_000

    result = gate.evaluate_trade(candidate=item, **default_kwargs())

    assert result.allowed is True
    assert result.code == "APPROVED"
    assert result.details["approved_quantity"] == 200
    assert result.details["original_quantity"] == 1_000


def test_approve_and_register() -> None:
    gate = build_gate()

    result = gate.approve_and_register(
        candidate=candidate(),
        **default_kwargs(),
    )

    assert result.allowed is True
    positions = gate.portfolio_engine.list_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "BTC/USDT"


def test_gate_report() -> None:
    gate = build_gate()

    report = gate.gate_report(
        equity=100_000,
        cash=100_000,
    )

    assert "risk_config" in report
    assert "portfolio" in report
    assert report["portfolio"]["position_count"] == 0
