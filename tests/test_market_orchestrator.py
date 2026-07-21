from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from engine.market_orchestrator import (
    OrchestratorSignal,
    PipelineStage,
    UnifiedMarketOrchestrator,
)
from engine.multi_asset_engine import AssetType, MarketState, SymbolConfig


class FakePaperTrading:
    def __init__(self):
        self.calls = []

    def submit_signal(self, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True, **kwargs}


def dt():
    return datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)


def make_orchestrator(scanner=None, decision=None, risk=None, paper=None):
    orchestrator = UnifiedMarketOrchestrator(
        scanner=scanner,
        decision_engine=decision,
        risk_engine=risk,
        paper_trading_engine=paper,
    )
    orchestrator.add_symbol(SymbolConfig("BTCUSDT", AssetType.CRYPTO))
    orchestrator.multi_asset_engine.refresh_market_states(now=dt())
    return orchestrator


def test_signal_validation():
    with pytest.raises(ValueError):
        OrchestratorSignal("", "BUY")
    with pytest.raises(ValueError):
        OrchestratorSignal("BTCUSDT", "BAD")


def test_default_hold_without_components():
    async def run():
        orchestrator = make_orchestrator()
        result = await orchestrator.process_symbol(
            "BTCUSDT",
            market_data={"price": 100},
            now=dt(),
        )
        assert result.stage == PipelineStage.SKIPPED
    asyncio.run(run())


def test_scanner_and_decision_execution():
    async def run():
        paper = FakePaperTrading()
        orchestrator = make_orchestrator(
            scanner=lambda state, data: {"score": 80},
            decision=lambda state, scan, data: {
                "action": "BUY",
                "score": 80,
                "reason": "NET AL",
                "quantity": 2,
            },
            risk=lambda state, signal, data: {
                "approved": True,
                "quantity": 1.5,
            },
            paper=paper,
        )
        result = await orchestrator.process_symbol(
            "BTCUSDT",
            market_data={"price": 100},
            now=dt(),
        )
        assert result.stage == PipelineStage.EXECUTED
        assert paper.calls[0]["quantity"] == 1.5
        assert paper.calls[0]["action"] == "BUY"
    asyncio.run(run())


def test_string_decision_mapping():
    async def run():
        paper = FakePaperTrading()
        orchestrator = make_orchestrator(
            scanner=lambda state, data: "x",
            decision=lambda state, scan, data: "NET AL",
            risk=lambda state, signal, data: {
                "approved": True,
                "quantity": 1,
            },
            paper=paper,
        )
        result = await orchestrator.process_symbol(
            "BTCUSDT",
            market_data={"price": 100},
            now=dt(),
        )
        assert result.signal.action == "BUY"
    asyncio.run(run())


def test_hold_skips_risk_and_execution():
    async def run():
        calls = []
        orchestrator = make_orchestrator(
            scanner=lambda state, data: {},
            decision=lambda state, scan, data: "BEKLE",
            risk=lambda state, signal, data: calls.append("risk"),
            paper=FakePaperTrading(),
        )
        result = await orchestrator.process_symbol(
            "BTCUSDT",
            market_data={"price": 100},
            now=dt(),
        )
        assert result.stage == PipelineStage.SKIPPED
        assert calls == []
    asyncio.run(run())


def test_risk_rejection():
    async def run():
        paper = FakePaperTrading()
        orchestrator = make_orchestrator(
            scanner=lambda state, data: {},
            decision=lambda state, scan, data: {
                "action": "BUY",
                "quantity": 1,
            },
            risk=lambda state, signal, data: {"approved": False},
            paper=paper,
        )
        result = await orchestrator.process_symbol(
            "BTCUSDT",
            market_data={"price": 100},
            now=dt(),
        )
        assert result.stage == PipelineStage.SKIPPED
        assert paper.calls == []
    asyncio.run(run())


def test_zero_quantity_skips():
    async def run():
        orchestrator = make_orchestrator(
            scanner=lambda state, data: {},
            decision=lambda state, scan, data: {
                "action": "BUY",
                "quantity": 0,
            },
            risk=lambda state, signal, data: True,
            paper=FakePaperTrading(),
        )
        result = await orchestrator.process_symbol(
            "BTCUSDT",
            market_data={"price": 100},
            now=dt(),
        )
        assert result.stage == PipelineStage.SKIPPED
    asyncio.run(run())


def test_missing_price_error():
    async def run():
        orchestrator = make_orchestrator(
            scanner=lambda state, data: {},
            decision=lambda state, scan, data: {
                "action": "BUY",
                "quantity": 1,
            },
            risk=lambda state, signal, data: True,
            paper=FakePaperTrading(),
        )
        result = await orchestrator.process_symbol(
            "BTCUSDT",
            market_data={},
            now=dt(),
        )
        assert result.stage == PipelineStage.ERROR
        assert "market price" in result.error
    asyncio.run(run())


def test_scanner_error_isolated():
    async def run():
        def fail(state, data):
            raise RuntimeError("boom")

        orchestrator = make_orchestrator(scanner=fail)
        result = await orchestrator.process_symbol(
            "BTCUSDT",
            market_data={"price": 100},
            now=dt(),
        )
        assert result.stage == PipelineStage.ERROR
        assert orchestrator.multi_asset_engine.get_state(
            "BTCUSDT"
        ).market_state == MarketState.ERROR
    asyncio.run(run())


def test_async_components():
    async def run():
        async def scanner(state, data):
            return {"score": 70}

        async def decision(state, scan, data):
            return {
                "action": "BUY",
                "quantity": 1,
                "reason": "async",
            }

        async def risk(state, signal, data):
            return {"approved": True, "quantity": 1}

        paper = FakePaperTrading()
        orchestrator = make_orchestrator(
            scanner=scanner,
            decision=decision,
            risk=risk,
            paper=paper,
        )
        result = await orchestrator.process_symbol(
            "BTCUSDT",
            market_data={"price": 100},
            now=dt(),
        )
        assert result.stage == PipelineStage.EXECUTED
    asyncio.run(run())


def test_disabled_symbol_skipped():
    async def run():
        orchestrator = make_orchestrator()
        orchestrator.multi_asset_engine.disable_symbol("BTCUSDT")
        result = await orchestrator.process_symbol(
            "BTCUSDT",
            market_data={"price": 100},
            now=dt(),
        )
        assert result.stage == PipelineStage.SKIPPED
    asyncio.run(run())


def test_process_many_error_isolation():
    async def run():
        paper = FakePaperTrading()

        def scanner(state, data):
            if state.config.symbol == "ETHUSDT":
                raise RuntimeError("eth error")
            return {}

        orchestrator = UnifiedMarketOrchestrator(
            scanner=scanner,
            decision_engine=lambda state, scan, data: {
                "action": "BUY",
                "quantity": 1,
            },
            risk_engine=lambda state, signal, data: True,
            paper_trading_engine=paper,
        )
        orchestrator.add_symbols([
            SymbolConfig("BTCUSDT", AssetType.CRYPTO),
            SymbolConfig("ETHUSDT", AssetType.CRYPTO),
        ])
        orchestrator.multi_asset_engine.refresh_market_states(now=dt())

        results = await orchestrator.process_many(
            {
                "BTCUSDT": {"price": 100},
                "ETHUSDT": {"price": 200},
            },
            now=dt(),
        )
        assert results["BTCUSDT"].stage == PipelineStage.EXECUTED
        assert results["ETHUSDT"].stage == PipelineStage.ERROR
    asyncio.run(run())


def test_stock_and_commodity_symbols():
    orchestrator = UnifiedMarketOrchestrator()
    orchestrator.add_symbols([
        SymbolConfig("BIMAS.IS", AssetType.STOCK),
        SymbolConfig("GC=F", AssetType.COMMODITY),
    ])
    assert len(orchestrator.multi_asset_engine.list_states()) == 2


def test_state_counters_update():
    async def run():
        orchestrator = make_orchestrator(
            scanner=lambda state, data: {},
            decision=lambda state, scan, data: "BEKLE",
        )
        await orchestrator.process_symbol(
            "BTCUSDT",
            market_data={"price": 100},
            now=dt(),
        )
        state = orchestrator.multi_asset_engine.get_state("BTCUSDT")
        assert state.scan_count == 1
        assert state.decision_count == 1
    asyncio.run(run())


def test_metrics_update():
    async def run():
        orchestrator = make_orchestrator(
            scanner=lambda state, data: {},
            decision=lambda state, scan, data: "BEKLE",
        )
        await orchestrator.process_symbol(
            "BTCUSDT",
            market_data={"price": 100},
            now=dt(),
        )
        metrics = orchestrator.metrics["BTCUSDT"]
        assert metrics.processed_count == 1
        assert metrics.skipped_count == 1
    asyncio.run(run())


def test_metrics_summary():
    async def run():
        orchestrator = make_orchestrator(
            scanner=lambda state, data: {},
            decision=lambda state, scan, data: "BEKLE",
        )
        await orchestrator.process_symbol(
            "BTCUSDT",
            market_data={"price": 100},
            now=dt(),
        )
        summary = orchestrator.metrics_summary()
        assert summary["total_processed"] == 1
        assert summary["total_skipped"] == 1
    asyncio.run(run())


def test_dashboard():
    async def run():
        orchestrator = make_orchestrator(
            scanner=lambda state, data: {},
            decision=lambda state, scan, data: "BEKLE",
        )
        await orchestrator.process_symbol(
            "BTCUSDT",
            market_data={"price": 100},
            now=dt(),
        )
        data = orchestrator.dashboard()
        assert "summary" in data
        assert "multi_asset" in data
        assert "metrics" in data
        assert "last_results" in data
    asyncio.run(run())


def test_pipeline_result_to_dict():
    async def run():
        orchestrator = make_orchestrator(
            scanner=lambda state, data: {},
            decision=lambda state, scan, data: "BEKLE",
        )
        result = await orchestrator.process_symbol(
            "BTCUSDT",
            market_data={"price": 100},
            now=dt(),
        )
        data = result.to_dict()
        assert data["symbol"] == "BTCUSDT"
        assert data["success"] is True
    asyncio.run(run())
