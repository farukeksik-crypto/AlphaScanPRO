from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from engine.market_orchestrator import (
    OrchestratorSignal,
    PipelineResult,
    PipelineStage,
)
from engine.multi_asset_engine import AssetType
from engine.position_integration import PositionManagementIntegration
from engine.position_management import (
    ExitReason,
    PositionManagementConfig,
    PositionManagementEngine,
    PositionSide,
)


def dt():
    return datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)


class FakePaperTrading:
    def __init__(self):
        self.calls = []

    def submit_signal(self, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True, **kwargs}


class FakeOrchestrator:
    def __init__(self, result):
        self.result = result
        self.calls = []
        self.paper_trading_engine = FakePaperTrading()

    async def process_symbol(self, symbol, market_data, now):
        self.calls.append((symbol, market_data, now))
        return self.result


def make_pipeline_result(
    *,
    action="BUY",
    quantity=1,
    stage=PipelineStage.EXECUTED,
    execution_output=None,
):
    return PipelineResult(
        symbol="BTCUSDT",
        asset_type=AssetType.CRYPTO,
        stage=stage,
        started_at=dt(),
        finished_at=dt(),
        duration_ms=1.0,
        signal=OrchestratorSignal(
            symbol="BTCUSDT",
            action=action,
            quantity=quantity,
            reason="test",
            score=80,
        ),
        execution_output=execution_output,
    )


def test_synchronize_long_entry():
    result = make_pipeline_result(
        action="BUY",
        quantity=2,
        execution_output={"fill_price": 101, "quantity": 2},
    )
    orchestrator = FakeOrchestrator(result)
    integration = PositionManagementIntegration(
        orchestrator=orchestrator
    )
    synced = integration.synchronize_entry(
        result,
        market_price=100,
        timestamp=dt(),
    )
    position = integration.position_manager.get_position("BTCUSDT")
    assert synced is True
    assert position.side == PositionSide.LONG
    assert position.entry_price == 101
    assert position.quantity == 2


def test_synchronize_short_entry():
    result = make_pipeline_result(action="SELL", quantity=1)
    integration = PositionManagementIntegration(
        orchestrator=FakeOrchestrator(result)
    )
    integration.synchronize_entry(
        result,
        market_price=100,
        timestamp=dt(),
    )
    assert (
        integration.position_manager.get_position(
            "BTCUSDT"
        ).side == PositionSide.SHORT
    )


def test_non_executed_not_synced():
    result = make_pipeline_result(stage=PipelineStage.SKIPPED)
    integration = PositionManagementIntegration(
        orchestrator=FakeOrchestrator(result)
    )
    assert integration.synchronize_entry(
        result,
        market_price=100,
    ) is False


def test_duplicate_not_synced():
    result = make_pipeline_result()
    integration = PositionManagementIntegration(
        orchestrator=FakeOrchestrator(result)
    )
    assert integration.synchronize_entry(
        result,
        market_price=100,
    )
    assert integration.synchronize_entry(
        result,
        market_price=100,
    ) is False


def test_process_symbol_opens_position():
    async def run():
        result = make_pipeline_result()
        orchestrator = FakeOrchestrator(result)
        integration = PositionManagementIntegration(
            orchestrator=orchestrator
        )
        output = await integration.process_symbol(
            "BTCUSDT",
            market_data={"price": 100},
            now=dt(),
        )
        assert output.synchronized is True
        assert integration.entry_count == 1
    asyncio.run(run())


def test_process_symbol_requires_price():
    async def run():
        result = make_pipeline_result()
        integration = PositionManagementIntegration(
            orchestrator=FakeOrchestrator(result)
        )
        output = await integration.process_symbol(
            "BTCUSDT",
            market_data={},
            now=dt(),
        )
        assert output.error
        assert integration.error_count == 1
    asyncio.run(run())


def test_existing_position_evaluated():
    async def run():
        result = make_pipeline_result()
        manager = PositionManagementEngine(
            PositionManagementConfig(
                enable_partial_take_profit=False
            )
        )
        manager.open_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            quantity=1,
            entry_price=100,
            opened_at=dt(),
        )
        orchestrator = FakeOrchestrator(result)
        integration = PositionManagementIntegration(
            orchestrator=orchestrator,
            position_manager=manager,
        )
        output = await integration.process_symbol(
            "BTCUSDT",
            market_data={"price": 96},
            now=dt(),
        )
        assert output.exit_actions[0].reason == ExitReason.STOP_LOSS
        assert integration.exit_count == 1
        assert len(orchestrator.paper_trading_engine.calls) == 1
    asyncio.run(run())


def test_no_new_entry_while_position_open():
    async def run():
        result = make_pipeline_result()
        manager = PositionManagementEngine()
        manager.open_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            quantity=1,
            entry_price=100,
        )
        orchestrator = FakeOrchestrator(result)
        integration = PositionManagementIntegration(
            orchestrator=orchestrator,
            position_manager=manager,
        )
        await integration.process_symbol(
            "BTCUSDT",
            market_data={"price": 101},
            now=dt(),
        )
        assert orchestrator.calls == []
    asyncio.run(run())


def test_daily_risk_blocks_new_entry():
    async def run():
        result = make_pipeline_result()
        manager = PositionManagementEngine(
            PositionManagementConfig(
                daily_loss_limit_pct=0.04
            )
        )
        manager.start_trading_day(
            trading_date=dt().date(),
            starting_equity=10000,
        )
        manager.register_external_pnl(-500)
        orchestrator = FakeOrchestrator(result)
        integration = PositionManagementIntegration(
            orchestrator=orchestrator,
            position_manager=manager,
        )
        await integration.process_symbol(
            "BTCUSDT",
            market_data={"price": 100},
            now=dt(),
        )
        assert orchestrator.calls == []
    asyncio.run(run())


def test_exit_submission_payload():
    result = make_pipeline_result()
    paper = FakePaperTrading()
    manager = PositionManagementEngine(
        PositionManagementConfig(
            enable_partial_take_profit=False
        )
    )
    manager.open_position(
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        quantity=1,
        entry_price=100,
    )
    integration = PositionManagementIntegration(
        orchestrator=FakeOrchestrator(result),
        position_manager=manager,
        paper_trading_engine=paper,
    )
    actions = integration.evaluate_position(
        "BTCUSDT",
        market_price=96,
        timestamp=dt(),
    )
    assert actions[0].reason == ExitReason.STOP_LOSS
    assert paper.calls[0]["strategy"] == "POSITION_MANAGEMENT"
    assert paper.calls[0]["reason"] == "STOP_LOSS"


def test_process_many():
    async def run():
        result = make_pipeline_result()
        orchestrator = FakeOrchestrator(result)
        integration = PositionManagementIntegration(
            orchestrator=orchestrator
        )
        outputs = await integration.process_many(
            {
                "BTCUSDT": {"price": 100},
                "ETHUSDT": {"price": 200},
            },
            now=dt(),
        )
        assert len(outputs) == 2
        assert integration.processed_count == 2
    asyncio.run(run())


def test_sync_existing_positions():
    integration = PositionManagementIntegration(
        orchestrator=FakeOrchestrator(make_pipeline_result())
    )
    synced = integration.sync_existing_positions([
        {
            "symbol": "BTCUSDT",
            "quantity": 2,
            "entry_price": 100,
            "side": "LONG",
        },
        {
            "symbol": "ETHUSDT",
            "quantity": 3,
            "entry_price": 200,
            "side": "SHORT",
        },
    ])
    assert len(synced) == 2
    assert (
        integration.position_manager.get_position(
            "ETHUSDT"
        ).side == PositionSide.SHORT
    )


def test_sync_existing_skips_duplicate():
    integration = PositionManagementIntegration(
        orchestrator=FakeOrchestrator(make_pipeline_result())
    )
    integration.sync_existing_positions([
        {
            "symbol": "BTCUSDT",
            "quantity": 1,
            "entry_price": 100,
        }
    ])
    synced = integration.sync_existing_positions([
        {
            "symbol": "BTCUSDT",
            "quantity": 1,
            "entry_price": 100,
        }
    ])
    assert synced == []


def test_dashboard():
    integration = PositionManagementIntegration(
        orchestrator=FakeOrchestrator(make_pipeline_result())
    )
    data = integration.dashboard()
    assert "position_management" in data
    assert "last_results" in data
    assert data["processed_count"] == 0


def test_result_to_dict():
    async def run():
        integration = PositionManagementIntegration(
            orchestrator=FakeOrchestrator(make_pipeline_result())
        )
        result = await integration.process_symbol(
            "BTCUSDT",
            market_data={"price": 100},
            now=dt(),
        )
        data = result.to_dict()
        assert data["success"] is True
        assert data["symbol"] == "BTCUSDT"
    asyncio.run(run())
