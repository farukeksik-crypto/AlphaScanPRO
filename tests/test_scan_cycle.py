from __future__ import annotations

from engine.live_robot_core import LiveRobotCore, RobotConfig
from engine.paper_execution import PaperBrokerConfig, PaperExecutionEngine
from engine.portfolio_engine import PortfolioConfig, PortfolioEngine
from engine.risk_core import RiskConfig, RiskCore
from engine.robot_orchestrator import RobotPaperOrchestrator
from engine.scan_cycle import (
    ScanCycleEngine,
    StrategyAdapterConfig,
    StrategySignalAdapter,
)
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


def cycle_kwargs() -> dict:
    return {
        "initial_equity": 100_000,
        "starting_equity": 100_000,
        "current_equity": 100_000,
        "daily_trade_count": 0,
        "consecutive_losses": 0,
        "current_total_risk_pct": 0.0,
    }


def test_adapter_converts_turkish_scanner_row() -> None:
    adapter = StrategySignalAdapter(
        StrategyAdapterConfig(
            minimum_score=60,
            default_market="CRYPTO",
            requested_quantity=1_000,
        )
    )

    result = adapter.adapt(
        {
            "Kod": "BTC/USDT",
            "Karar": "NET AL",
            "Puan": 75,
            "Fiyat": 100,
            "Stop": 95,
            "Hedef": 110,
        }
    )

    assert result.accepted is True
    assert result.signal is not None
    assert result.signal.symbol == "BTC/USDT"
    assert result.signal.signal == "BUY"
    assert result.market_price == 100
    assert result.stop_price == 95
    assert result.take_profit == 110


def test_adapter_rejects_low_score() -> None:
    adapter = StrategySignalAdapter(
        StrategyAdapterConfig(minimum_score=60)
    )

    result = adapter.adapt(
        {
            "symbol": "ETH/USDT",
            "decision": "BUY",
            "score": 50,
            "price": 100,
        }
    )

    assert result.accepted is False
    assert result.code == "SCORE_TOO_LOW"


def test_adapter_rejects_non_buy_decision() -> None:
    adapter = StrategySignalAdapter()

    result = adapter.adapt(
        {
            "symbol": "SOL/USDT",
            "decision": "BEKLE",
            "score": 80,
            "price": 100,
        }
    )

    assert result.accepted is False
    assert result.code == "NON_BUY_DECISION"


def test_scan_cycle_executes_valid_signal() -> None:
    scanner = lambda: [
        {
            "Kod": "BTC/USDT",
            "Karar": "NET AL",
            "Puan": 75,
            "Fiyat": 100,
            "Stop": 95,
            "Hedef": 110,
        }
    ]
    engine = ScanCycleEngine(
        orchestrator=build_orchestrator(),
        scanner=scanner,
        adapter=StrategySignalAdapter(
            StrategyAdapterConfig(
                minimum_score=60,
                requested_quantity=1_000,
            )
        ),
    )

    result = engine.run_cycle(**cycle_kwargs())

    assert result.scanned_count == 1
    assert result.adapted_count == 1
    assert result.executed_count == 1
    assert result.rejected_count == 0


def test_scan_cycle_mixed_results() -> None:
    scanner = lambda: [
        {
            "symbol": "BTC/USDT",
            "decision": "BUY",
            "score": 75,
            "price": 100,
            "stop_price": 95,
            "take_profit": 110,
        },
        {
            "symbol": "ETH/USDT",
            "decision": "BEKLE",
            "score": 80,
            "price": 100,
        },
        {
            "symbol": "SOL/USDT",
            "decision": "BUY",
            "score": 40,
            "price": 100,
        },
    ]
    engine = ScanCycleEngine(
        orchestrator=build_orchestrator(),
        scanner=scanner,
    )

    result = engine.run_cycle(**cycle_kwargs())

    assert result.scanned_count == 3
    assert result.executed_count == 1
    assert result.rejected_count == 2
    assert result.errors == []


def test_cycle_report() -> None:
    scanner = lambda: [
        {
            "symbol": "BTC/USDT",
            "decision": "BUY",
            "score": 75,
            "price": 100,
            "stop_price": 95,
            "take_profit": 110,
        }
    ]
    engine = ScanCycleEngine(
        orchestrator=build_orchestrator(),
        scanner=scanner,
    )
    engine.run_cycle(**cycle_kwargs())

    report = engine.cycle_report()

    assert report["cycle_count"] == 1
    assert len(report["history"]) == 1
    assert "orchestrator" in report
    assert "paper_account" in report["orchestrator"]
