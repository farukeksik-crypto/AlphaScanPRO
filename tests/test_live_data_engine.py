from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from engine.live_data_engine import (
    BinanceTradeParser,
    ConnectionState,
    InMemoryMarketTransport,
    LiveDataEngine,
    LiveDataHealth,
    MarketTick,
    OhlcAggregator,
    ReconnectPolicy,
)


def dt(minute: int, second: int = 0) -> datetime:
    return datetime(2026, 7, 21, 12, minute, second, tzinfo=timezone.utc)


def payload(symbol="BTCUSDT", price="100", qty="2", minute=0, second=0):
    timestamp = int(dt(minute, second).timestamp() * 1000)
    return {"s": symbol, "p": price, "q": qty, "T": timestamp}


def test_market_tick_validation():
    with pytest.raises(ValueError):
        MarketTick("", 1, 0, dt(0))
    with pytest.raises(ValueError):
        MarketTick("BTCUSDT", 0, 0, dt(0))
    with pytest.raises(ValueError):
        MarketTick("BTCUSDT", 1, -1, dt(0))


def test_tick_normalization():
    tick = MarketTick("btcusdt", 100, 2, dt(0))
    assert tick.symbol == "BTCUSDT"


def test_parser_plain_payload():
    tick = BinanceTradeParser.parse(payload())
    assert tick.symbol == "BTCUSDT"
    assert tick.price == 100
    assert tick.quantity == 2


def test_parser_combined_stream():
    tick = BinanceTradeParser.parse({"stream": "x", "data": payload()})
    assert tick.source == "BINANCE"


def test_parser_missing_fields():
    with pytest.raises(ValueError):
        BinanceTradeParser.parse({"q": "1"})


def test_reconnect_policy_validation():
    with pytest.raises(ValueError):
        ReconnectPolicy(initial_delay=-1)
    with pytest.raises(ValueError):
        ReconnectPolicy(initial_delay=2, max_delay=1)


def test_reconnect_delay():
    policy = ReconnectPolicy(initial_delay=1, max_delay=5, multiplier=2)
    assert policy.delay_for_attempt(1) == 1
    assert policy.delay_for_attempt(3) == 4
    assert policy.delay_for_attempt(4) == 5


def test_ohlc_first_tick():
    agg = OhlcAggregator(60)
    agg.add_tick(MarketTick("BTCUSDT", 100, 2, dt(0)))
    bar = agg.current_bar("BTCUSDT")
    assert bar.open == 100
    assert bar.volume == 2
    assert bar.tick_count == 1


def test_ohlc_updates():
    agg = OhlcAggregator(60)
    agg.add_tick(MarketTick("BTCUSDT", 100, 1, dt(0, 1)))
    agg.add_tick(MarketTick("BTCUSDT", 120, 2, dt(0, 2)))
    agg.add_tick(MarketTick("BTCUSDT", 90, 3, dt(0, 3)))
    bar = agg.current_bar("BTCUSDT")
    assert (bar.open, bar.high, bar.low, bar.close) == (100, 120, 90, 90)
    assert bar.volume == 6
    assert bar.tick_count == 3


def test_ohlc_closes_on_new_bucket():
    agg = OhlcAggregator(60)
    agg.add_tick(MarketTick("BTCUSDT", 100, 1, dt(0)))
    closed = agg.add_tick(MarketTick("BTCUSDT", 110, 1, dt(1)))
    assert len(closed) == 1
    assert closed[0].is_closed is True
    assert agg.current_bar("BTCUSDT").open == 110


def test_ohlc_multi_symbol():
    agg = OhlcAggregator(60)
    agg.add_tick(MarketTick("BTCUSDT", 100, 1, dt(0)))
    agg.add_tick(MarketTick("ETHUSDT", 200, 1, dt(0)))
    assert agg.current_bar("BTCUSDT").close == 100
    assert agg.current_bar("ETHUSDT").close == 200


def test_ohlc_flush():
    agg = OhlcAggregator(60)
    agg.add_tick(MarketTick("BTCUSDT", 100, 1, dt(0)))
    bars = agg.flush()
    assert len(bars) == 1
    assert agg.current_bar("BTCUSDT") is None


def test_health_stale():
    health = LiveDataHealth(last_tick_at=dt(0))
    assert health.is_stale(now=dt(0) + timedelta(seconds=31), stale_after=30)
    assert not health.is_stale(now=dt(0) + timedelta(seconds=29), stale_after=30)


def test_engine_requires_symbols():
    transport = InMemoryMarketTransport([])
    with pytest.raises(ValueError):
        LiveDataEngine(symbols=[], transport=transport)


def test_process_message():
    async def run():
        transport = InMemoryMarketTransport([])
        engine = LiveDataEngine(symbols=["BTCUSDT"], transport=transport)
        tick = await engine.process_message(payload())
        assert tick is not None
        assert engine.health.received_ticks == 1
        assert engine.latest_ticks["BTCUSDT"].price == 100
    asyncio.run(run())


def test_process_invalid_message():
    async def run():
        engine = LiveDataEngine(
            symbols=["BTCUSDT"],
            transport=InMemoryMarketTransport([]),
        )
        tick = await engine.process_message({"bad": "data"})
        assert tick is None
        assert engine.health.parse_errors == 1
    asyncio.run(run())


def test_unknown_symbol_ignored():
    async def run():
        engine = LiveDataEngine(
            symbols=["BTCUSDT"],
            transport=InMemoryMarketTransport([]),
        )
        tick = await engine.process_message(payload(symbol="ETHUSDT"))
        assert tick is None
        assert engine.health.received_ticks == 0
    asyncio.run(run())


def test_tick_handler():
    async def run():
        seen = []
        engine = LiveDataEngine(
            symbols=["BTCUSDT"],
            transport=InMemoryMarketTransport([]),
        )
        engine.add_tick_handler(lambda tick: seen.append(tick.symbol))
        await engine.process_message(payload())
        assert seen == ["BTCUSDT"]
    asyncio.run(run())


def test_async_tick_handler():
    async def run():
        seen = []

        async def handler(tick):
            seen.append(tick.price)

        engine = LiveDataEngine(
            symbols=["BTCUSDT"],
            transport=InMemoryMarketTransport([]),
        )
        engine.add_tick_handler(handler)
        await engine.process_message(payload())
        assert seen == [100]
    asyncio.run(run())


def test_bar_handler():
    async def run():
        seen = []
        engine = LiveDataEngine(
            symbols=["BTCUSDT"],
            transport=InMemoryMarketTransport([]),
        )
        engine.add_bar_handler(lambda bar: seen.append(bar.close))
        await engine.process_message(payload(minute=0, price="100"))
        await engine.process_message(payload(minute=1, price="110"))
        assert seen == [100]
    asyncio.run(run())


def test_run_once():
    async def run():
        transport = InMemoryMarketTransport([payload(), payload(price="101")])
        engine = LiveDataEngine(symbols=["BTCUSDT"], transport=transport)
        await engine.run_once()
        assert engine.health.received_ticks == 2
        assert engine.latest_ticks["BTCUSDT"].price == 101
        assert transport.closed is True
    asyncio.run(run())


def test_run_once_state():
    async def run():
        transport = InMemoryMarketTransport([payload()])
        engine = LiveDataEngine(symbols=["BTCUSDT"], transport=transport)
        await engine.run_once()
        assert engine.health.state == ConnectionState.DISCONNECTED
        assert engine.health.connected_at is not None
    asyncio.run(run())


def test_dashboard():
    async def run():
        engine = LiveDataEngine(
            symbols=["ETHUSDT", "BTCUSDT"],
            transport=InMemoryMarketTransport([]),
        )
        await engine.process_message(payload())
        data = engine.dashboard()
        assert data["symbols"] == ["BTCUSDT", "ETHUSDT"]
        assert "health" in data
        assert "latest_ticks" in data
        assert "ohlc" in data
    asyncio.run(run())


def test_transport_connect_error():
    async def run():
        transport = InMemoryMarketTransport([], connect_error=RuntimeError("x"))
        engine = LiveDataEngine(symbols=["BTCUSDT"], transport=transport)
        with pytest.raises(RuntimeError):
            await engine.run_once()
    asyncio.run(run())


def test_run_forever_max_attempts():
    async def run():
        transport = InMemoryMarketTransport([], connect_error=RuntimeError("x"))
        engine = LiveDataEngine(
            symbols=["BTCUSDT"],
            transport=transport,
            reconnect_policy=ReconnectPolicy(
                initial_delay=0,
                max_delay=0,
                multiplier=1,
                max_attempts=2,
            ),
        )
        await engine.run_forever()
        assert engine.health.connection_errors == 2
        assert engine.health.state == ConnectionState.STOPPED
    asyncio.run(run())
