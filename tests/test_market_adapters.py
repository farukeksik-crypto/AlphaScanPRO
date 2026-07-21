from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from engine.market_adapters import (
    AdapterOrchestratorBridge,
    AdapterState,
    BinanceMarketAdapter,
    MarketAdapterRegistry,
    MarketDataSnapshot,
    YahooCommodityMarketAdapter,
    YahooStockMarketAdapter,
)
from engine.multi_asset_engine import AssetType, SymbolConfig


def dt():
    return datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)


class FakeOrchestrator:
    def __init__(self):
        self.calls = []

    async def process_symbol(self, symbol, market_data, now):
        self.calls.append((symbol, market_data, now))
        return {"symbol": symbol, "stage": "EXECUTED"}


def test_snapshot_validation():
    with pytest.raises(ValueError):
        MarketDataSnapshot("", AssetType.CRYPTO, 1, dt(), "x")
    with pytest.raises(ValueError):
        MarketDataSnapshot("BTCUSDT", AssetType.CRYPTO, 0, dt(), "x")


def test_snapshot_to_market_data():
    snapshot = MarketDataSnapshot(
        "BTCUSDT",
        AssetType.CRYPTO,
        100,
        dt(),
        "BINANCE",
    )
    data = snapshot.to_market_data()
    assert data["price"] == 100
    assert data["asset_type"] == "CRYPTO"


def test_binance_adapter():
    async def run():
        adapter = BinanceMarketAdapter(lambda config: {"price": 100})
        config = SymbolConfig("BTCUSDT", AssetType.CRYPTO)
        snapshot = await adapter.fetch_snapshot(config)
        assert snapshot.price == 100
        assert adapter.health.success_count == 1
    asyncio.run(run())


def test_stock_adapter():
    async def run():
        adapter = YahooStockMarketAdapter(lambda config: {"close": 500})
        config = SymbolConfig("BIMAS.IS", AssetType.STOCK)
        snapshot = await adapter.fetch_snapshot(config)
        assert snapshot.price == 500
        assert snapshot.source == "YAHOO_STOCK"
    asyncio.run(run())


def test_commodity_adapter():
    async def run():
        adapter = YahooCommodityMarketAdapter(lambda config: 2400)
        config = SymbolConfig("GC=F", AssetType.COMMODITY)
        snapshot = await adapter.fetch_snapshot(config)
        assert snapshot.price == 2400
    asyncio.run(run())


def test_asset_type_mismatch():
    async def run():
        adapter = BinanceMarketAdapter(lambda config: 100)
        config = SymbolConfig("BIMAS.IS", AssetType.STOCK)
        with pytest.raises(ValueError):
            await adapter.fetch_snapshot(config)
    asyncio.run(run())


def test_async_fetcher():
    async def run():
        async def fetcher(config):
            return {"price": 100, "volume": 10}

        adapter = BinanceMarketAdapter(fetcher)
        snapshot = await adapter.fetch_snapshot(
            SymbolConfig("BTCUSDT", AssetType.CRYPTO)
        )
        assert snapshot.volume == 10
    asyncio.run(run())


def test_failure_health():
    async def run():
        def fail(config):
            raise RuntimeError("boom")

        adapter = BinanceMarketAdapter(fail)
        with pytest.raises(RuntimeError):
            await adapter.fetch_snapshot(
                SymbolConfig("BTCUSDT", AssetType.CRYPTO)
            )
        assert adapter.health.failure_count == 1
        assert adapter.health.state == AdapterState.DEGRADED
    asyncio.run(run())


def test_reconnect():
    async def run():
        adapter = BinanceMarketAdapter(lambda config: 100)
        await adapter.connect()
        await adapter.reconnect()
        assert adapter.health.reconnect_count == 1
        assert adapter.health.state == AdapterState.CONNECTED
    asyncio.run(run())


def test_registry_register_get():
    registry = MarketAdapterRegistry()
    adapter = BinanceMarketAdapter(lambda config: 100)
    registry.register(adapter)
    assert registry.get(AssetType.CRYPTO) is adapter


def test_registry_unregister():
    registry = MarketAdapterRegistry()
    registry.register(BinanceMarketAdapter(lambda config: 100))
    registry.unregister(AssetType.CRYPTO)
    with pytest.raises(KeyError):
        registry.get(AssetType.CRYPTO)


def test_registry_connect_disconnect_all():
    async def run():
        registry = MarketAdapterRegistry()
        crypto = BinanceMarketAdapter(lambda config: 100)
        stock = YahooStockMarketAdapter(lambda config: 200)
        registry.register(crypto)
        registry.register(stock)
        await registry.connect_all()
        assert crypto.health.state == AdapterState.CONNECTED
        assert stock.health.state == AdapterState.CONNECTED
        await registry.disconnect_all()
        assert crypto.health.state == AdapterState.DISCONNECTED
        assert stock.health.state == AdapterState.DISCONNECTED
    asyncio.run(run())


def test_registry_fetch():
    async def run():
        registry = MarketAdapterRegistry()
        registry.register(BinanceMarketAdapter(lambda config: 100))
        snapshot = await registry.fetch(
            SymbolConfig("BTCUSDT", AssetType.CRYPTO)
        )
        assert snapshot.price == 100
    asyncio.run(run())


def test_registry_fetch_many_error_isolation():
    async def run():
        registry = MarketAdapterRegistry()
        registry.register(
            BinanceMarketAdapter(
                lambda config: (
                    (_ for _ in ()).throw(RuntimeError("bad"))
                    if config.symbol == "ETHUSDT"
                    else 100
                )
            )
        )
        results = await registry.fetch_many([
            SymbolConfig("BTCUSDT", AssetType.CRYPTO),
            SymbolConfig("ETHUSDT", AssetType.CRYPTO),
        ])
        assert isinstance(results["BTCUSDT"], MarketDataSnapshot)
        assert isinstance(results["ETHUSDT"], Exception)
    asyncio.run(run())


def test_registry_dashboard():
    registry = MarketAdapterRegistry()
    registry.register(BinanceMarketAdapter(lambda config: 100))
    data = registry.dashboard()
    assert data["adapter_count"] == 1
    assert "CRYPTO" in data["adapters"]


def test_bridge_process_config():
    async def run():
        registry = MarketAdapterRegistry()
        registry.register(BinanceMarketAdapter(lambda config: 100))
        orchestrator = FakeOrchestrator()
        bridge = AdapterOrchestratorBridge(
            registry=registry,
            orchestrator=orchestrator,
        )
        result = await bridge.process_config(
            SymbolConfig("BTCUSDT", AssetType.CRYPTO)
        )
        assert result["stage"] == "EXECUTED"
        assert bridge.processed_count == 1
        assert orchestrator.calls[0][1]["price"] == 100
    asyncio.run(run())


def test_bridge_process_many():
    async def run():
        registry = MarketAdapterRegistry()
        registry.register(BinanceMarketAdapter(lambda config: 100))
        registry.register(YahooStockMarketAdapter(lambda config: 500))
        orchestrator = FakeOrchestrator()
        bridge = AdapterOrchestratorBridge(
            registry=registry,
            orchestrator=orchestrator,
        )
        results = await bridge.process_many([
            SymbolConfig("BTCUSDT", AssetType.CRYPTO),
            SymbolConfig("BIMAS.IS", AssetType.STOCK),
        ])
        assert len(results) == 2
        assert bridge.processed_count == 2
    asyncio.run(run())


def test_bridge_error_count():
    async def run():
        registry = MarketAdapterRegistry()
        registry.register(
            BinanceMarketAdapter(
                lambda config: (_ for _ in ()).throw(RuntimeError("bad"))
            )
        )
        bridge = AdapterOrchestratorBridge(
            registry=registry,
            orchestrator=FakeOrchestrator(),
        )
        results = await bridge.process_many([
            SymbolConfig("BTCUSDT", AssetType.CRYPTO)
        ])
        assert isinstance(results["BTCUSDT"], Exception)
        assert bridge.error_count == 1
    asyncio.run(run())


def test_bridge_dashboard():
    registry = MarketAdapterRegistry()
    registry.register(BinanceMarketAdapter(lambda config: 100))
    bridge = AdapterOrchestratorBridge(
        registry=registry,
        orchestrator=FakeOrchestrator(),
    )
    data = bridge.dashboard()
    assert "registry" in data
    assert data["processed_count"] == 0
