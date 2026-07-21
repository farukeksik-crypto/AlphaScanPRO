from __future__ import annotations

from engine.live_robot_core import (
    LiveRobotCore,
    RobotConfig,
    SignalEvent,
    TradeLifecycleStatus,
)
from engine.paper_execution import (
    PaperBrokerConfig,
    PaperExecutionEngine,
)
from engine.portfolio_engine import PortfolioConfig, PortfolioEngine
from engine.risk_core import RiskConfig, RiskCore
from engine.robot_orchestrator import RobotPaperOrchestrator
from engine.trade_gate import UnifiedTradeGate


def build_orchestrator() -> RobotPaperOrchestrator:
    robot = LiveRobotCore(
        RobotConfig(
            max_queue_size=20,
            max_task_retries=2,
            markets=("CRYPTO",),
        )
    )
    robot.start()

    risk = RiskCore(
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
        )
    )
    gate = UnifiedTradeGate(
        risk_core=risk,
        portfolio_engine=portfolio,
    )
    paper = PaperExecutionEngine(
        PaperBrokerConfig(
            starting_cash=100_000,
            commission_rate=0.001,
            slippage_rate=0.0,
            allow_partial_fills=True,
        )
    )
    return RobotPaperOrchestrator(
        robot=robot,
        trade_gate=gate,
        paper_engine=paper,
    )


def kwargs() -> dict:
    return {
        "market_price": 100,
        "stop_price": 95,
        "requested_quantity": 1_000,
        "initial_equity": 100_000,
        "starting_equity": 100_000,
        "current_equity": 100_000,
        "daily_trade_count": 0,
        "consecutive_losses": 0,
        "current_total_risk_pct": 0.0,
        "minimum_signal_score": 60,
        "sector": "MAJOR",
        "take_profit": 110,
    }


def buy_signal(score: float = 75) -> SignalEvent:
    return SignalEvent(
        symbol="BTC/USDT",
        market="CRYPTO",
        signal="BUY",
        score=score,
    )


def test_end_to_end_signal_execution() -> None:
    orchestrator = build_orchestrator()

    result = orchestrator.process_signal(
        signal=buy_signal(),
        **kwargs(),
    )

    assert result.accepted is True
    assert result.code == "EXECUTED"
    assert result.stage == "completed"

    order = result.details["order"]
    trade = result.details["trade"]

    assert order["status"] == "FILLED"
    assert order["filled_quantity"] == 200
    assert trade["status"] == "OPEN"
    assert trade["quantity"] == 200


def test_signal_rejected_by_trade_gate() -> None:
    orchestrator = build_orchestrator()

    result = orchestrator.process_signal(
        signal=buy_signal(score=50),
        **kwargs(),
    )

    assert result.accepted is False
    assert result.code == "SIGNAL_SCORE_TOO_LOW"
    assert result.stage == "signal"
    assert len(orchestrator.paper_engine.orders) == 0


def test_non_buy_signal_rejected() -> None:
    orchestrator = build_orchestrator()
    signal = SignalEvent(
        symbol="BTC/USDT",
        market="CRYPTO",
        signal="SELL",
        score=80,
    )

    result = orchestrator.process_signal(
        signal=signal,
        **kwargs(),
    )

    assert result.accepted is False
    assert result.code == "UNSUPPORTED_SIGNAL"


def test_partial_fill_updates_lifecycle_quantity() -> None:
    orchestrator = build_orchestrator()

    result = orchestrator.process_signal(
        signal=buy_signal(),
        available_liquidity=50,
        **kwargs(),
    )

    assert result.accepted is True
    assert result.details["order"]["status"] == "PARTIALLY_FILLED"
    assert result.details["trade"]["quantity"] == 50


def test_stop_loss_closes_trade() -> None:
    orchestrator = build_orchestrator()
    result = orchestrator.process_signal(
        signal=buy_signal(),
        **kwargs(),
    )
    trade_id = result.details["trade"]["trade_id"]

    events = orchestrator.process_price_update(
        symbol="BTC/USDT",
        market_price=94,
    )

    trade = orchestrator.robot.trades[trade_id]
    assert len(events) == 1
    assert trade.status == TradeLifecycleStatus.CLOSED
    assert orchestrator.paper_engine.positions["BTC/USDT"].quantity == 0


def test_combined_report() -> None:
    orchestrator = build_orchestrator()
    orchestrator.process_signal(
        signal=buy_signal(),
        **kwargs(),
    )

    report = orchestrator.combined_report()

    assert "robot" in report
    assert "paper_account" in report
    assert "portfolio" in report
    assert "orchestrator_history" in report
    assert report["robot"]["status"] == "RUNNING"
    assert report["paper_account"]["equity"] > 0
