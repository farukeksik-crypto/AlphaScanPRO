from __future__ import annotations

from datetime import datetime, time, timezone

import pytest

from engine.multi_asset_engine import (
    AssetType,
    MarketSession,
    MarketState,
    MultiAssetSymbolEngine,
    SymbolConfig,
)


def dt(hour: int, weekday_day: int = 20):
    return datetime(2026, 7, weekday_day, hour, 0, tzinfo=timezone.utc)


def test_crypto_default_session_always_open():
    config = SymbolConfig("BTCUSDT", AssetType.CRYPTO)
    assert config.session.always_open is True


def test_stock_default_session():
    config = SymbolConfig("BIMAS.IS", AssetType.STOCK)
    assert config.session.open_time == time(10, 0)
    assert config.session.close_time == time(18, 10)


def test_commodity_default_session():
    config = SymbolConfig("GC=F", AssetType.COMMODITY)
    assert config.session.weekdays == (0, 1, 2, 3, 4)


def test_symbol_validation():
    with pytest.raises(ValueError):
        SymbolConfig("", AssetType.CRYPTO)


def test_market_session_always_open():
    session = MarketSession(always_open=True)
    assert session.is_open(dt(3))


def test_market_session_weekday_open():
    session = MarketSession(
        open_time=time(10),
        close_time=time(18),
        weekdays=(0, 1, 2, 3, 4),
    )
    assert session.is_open(dt(12, 20))


def test_market_session_weekend_closed():
    session = MarketSession(
        open_time=time(10),
        close_time=time(18),
        weekdays=(0, 1, 2, 3, 4),
    )
    assert not session.is_open(dt(12, 25))


def test_add_symbol():
    engine = MultiAssetSymbolEngine()
    state = engine.add_symbol(SymbolConfig("BTCUSDT", AssetType.CRYPTO))
    assert state.config.symbol == "BTCUSDT"


def test_duplicate_symbol():
    engine = MultiAssetSymbolEngine()
    engine.add_symbol(SymbolConfig("BTCUSDT", AssetType.CRYPTO))
    with pytest.raises(ValueError):
        engine.add_symbol(SymbolConfig("BTCUSDT", AssetType.CRYPTO))


def test_add_symbols():
    engine = MultiAssetSymbolEngine()
    states = engine.add_symbols([
        SymbolConfig("BTCUSDT", AssetType.CRYPTO),
        SymbolConfig("BIMAS.IS", AssetType.STOCK),
    ])
    assert len(states) == 2


def test_remove_symbol():
    engine = MultiAssetSymbolEngine()
    engine.add_symbol(SymbolConfig("BTCUSDT", AssetType.CRYPTO))
    engine.remove_symbol("BTCUSDT")
    assert engine.list_states() == []


def test_get_state_normalizes_symbol():
    engine = MultiAssetSymbolEngine()
    engine.add_symbol(SymbolConfig("BTCUSDT", AssetType.CRYPTO))
    assert engine.get_state("btcusdt").config.symbol == "BTCUSDT"


def test_list_states_filter():
    engine = MultiAssetSymbolEngine()
    engine.add_symbols([
        SymbolConfig("BTCUSDT", AssetType.CRYPTO),
        SymbolConfig("ETHUSDT", AssetType.CRYPTO),
        SymbolConfig("BIMAS.IS", AssetType.STOCK),
    ])
    assert len(engine.list_states(asset_type=AssetType.CRYPTO)) == 2


def test_enable_disable():
    engine = MultiAssetSymbolEngine()
    engine.add_symbol(SymbolConfig("BTCUSDT", AssetType.CRYPTO))
    engine.disable_symbol("BTCUSDT")
    assert engine.get_state("BTCUSDT").config.enabled is False
    engine.enable_symbol("BTCUSDT")
    assert engine.get_state("BTCUSDT").config.enabled is True


def test_refresh_market_states():
    engine = MultiAssetSymbolEngine()
    engine.add_symbols([
        SymbolConfig("BTCUSDT", AssetType.CRYPTO),
        SymbolConfig("BIMAS.IS", AssetType.STOCK),
    ])
    states = engine.refresh_market_states(now=dt(12))
    assert states["BTCUSDT"] == MarketState.ACTIVE
    assert states["BIMAS.IS"] == MarketState.ACTIVE


def test_stock_closed_outside_session():
    engine = MultiAssetSymbolEngine()
    engine.add_symbol(SymbolConfig("BIMAS.IS", AssetType.STOCK))
    states = engine.refresh_market_states(now=dt(20))
    assert states["BIMAS.IS"] == MarketState.CLOSED


def test_active_states():
    engine = MultiAssetSymbolEngine()
    engine.add_symbols([
        SymbolConfig("BTCUSDT", AssetType.CRYPTO),
        SymbolConfig("BIMAS.IS", AssetType.STOCK),
    ])
    states = engine.active_states(now=dt(20))
    assert [state.config.symbol for state in states] == ["BTCUSDT"]


def test_update_price():
    engine = MultiAssetSymbolEngine()
    engine.add_symbol(SymbolConfig("BTCUSDT", AssetType.CRYPTO))
    state = engine.update_price("BTCUSDT", 100)
    assert state.last_price == 100


def test_update_position():
    engine = MultiAssetSymbolEngine()
    engine.add_symbol(SymbolConfig("BTCUSDT", AssetType.CRYPTO))
    state = engine.update_position("BTCUSDT", quantity=2, average_price=100)
    assert state.position_quantity == 2
    assert state.average_price == 100


def test_register_scan_and_decision():
    engine = MultiAssetSymbolEngine()
    engine.add_symbol(SymbolConfig("BTCUSDT", AssetType.CRYPTO))
    state = engine.register_scan(
        "BTCUSDT",
        signal="AL",
        decision="NET AL",
    )
    assert state.scan_count == 1
    assert state.decision_count == 1


def test_register_order():
    engine = MultiAssetSymbolEngine()
    engine.add_symbol(SymbolConfig("BTCUSDT", AssetType.CRYPTO))
    state = engine.register_order("BTCUSDT")
    assert state.order_count == 1


def test_process_active_symbols():
    engine = MultiAssetSymbolEngine()
    engine.add_symbols([
        SymbolConfig("BTCUSDT", AssetType.CRYPTO),
        SymbolConfig("BIMAS.IS", AssetType.STOCK),
    ])
    engine.register_handler(
        AssetType.CRYPTO,
        lambda state: f"crypto:{state.config.symbol}",
    )
    engine.register_handler(
        AssetType.STOCK,
        lambda state: f"stock:{state.config.symbol}",
    )
    result = engine.process_active_symbols(now=dt(12))
    assert result["BTCUSDT"] == "crypto:BTCUSDT"
    assert result["BIMAS.IS"] == "stock:BIMAS.IS"


def test_handler_error_registered():
    engine = MultiAssetSymbolEngine()
    engine.add_symbol(SymbolConfig("BTCUSDT", AssetType.CRYPTO))

    def fail(state):
        raise RuntimeError("boom")

    engine.register_handler(AssetType.CRYPTO, fail)
    engine.process_active_symbols(now=dt(12))
    state = engine.get_state("BTCUSDT")
    assert state.error_count == 1
    assert state.market_state == MarketState.ERROR


def test_grouped_symbols():
    engine = MultiAssetSymbolEngine()
    engine.add_symbols([
        SymbolConfig("BTCUSDT", AssetType.CRYPTO),
        SymbolConfig("BIMAS.IS", AssetType.STOCK),
        SymbolConfig("GC=F", AssetType.COMMODITY),
    ])
    groups = engine.grouped_symbols()
    assert groups["CRYPTO"] == ["BTCUSDT"]
    assert groups["STOCK"] == ["BIMAS.IS"]
    assert groups["COMMODITY"] == ["GC=F"]


def test_stats():
    engine = MultiAssetSymbolEngine()
    engine.add_symbols([
        SymbolConfig("BTCUSDT", AssetType.CRYPTO),
        SymbolConfig("BIMAS.IS", AssetType.STOCK),
        SymbolConfig("GC=F", AssetType.COMMODITY),
    ])
    engine.refresh_market_states(now=dt(12))
    engine.register_scan("BTCUSDT", decision="NET AL")
    engine.register_order("BTCUSDT")
    stats = engine.stats()
    assert stats.total_symbols == 3
    assert stats.crypto_symbols == 1
    assert stats.stock_symbols == 1
    assert stats.commodity_symbols == 1
    assert stats.total_scans == 1
    assert stats.total_decisions == 1
    assert stats.total_orders == 1


def test_dashboard():
    engine = MultiAssetSymbolEngine()
    engine.add_symbol(SymbolConfig("BTCUSDT", AssetType.CRYPTO))
    data = engine.dashboard()
    assert "stats" in data
    assert "groups" in data
    assert "symbols" in data
