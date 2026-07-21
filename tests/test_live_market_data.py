from __future__ import annotations

import json

import pytest

from engine.live_market_data import (
    BINANCE_SPOT_TESTNET_WS_BASE,
    BinanceLiveMarketDataEngine,
    BinanceMarketDataParser,
    DepthUpdate,
    KlineUpdate,
    MarketDataConfig,
    MarketDataEventType,
    StreamSubscription,
    TickerUpdate,
    TradeTick,
)


class FakeTransport:
    def __init__(self) -> None:
        self.urls: list[str] = []
        self.messages: list[object] = []
        self.closed = 0
        self.fail_connect_count = 0
        self.fail_receive_count = 0

    def connect(self, url: str) -> None:
        if self.fail_connect_count > 0:
            self.fail_connect_count -= 1
            raise ConnectionError("connect fail")
        self.urls.append(url)

    def receive(self):
        if self.fail_receive_count > 0:
            self.fail_receive_count -= 1
            raise ConnectionError("receive fail")
        if not self.messages:
            return None
        return self.messages.pop(0)

    def close(self) -> None:
        self.closed += 1


def trade_payload() -> dict:
    return {
        "e": "trade",
        "E": 1000,
        "s": "BTCUSDT",
        "p": "101.5",
        "q": "0.25",
        "T": 999,
        "m": True,
    }


def kline_payload(closed: bool = False) -> dict:
    return {
        "e": "kline",
        "E": 1000,
        "s": "BTCUSDT",
        "k": {
            "t": 1,
            "T": 60_000,
            "s": "BTCUSDT",
            "i": "1m",
            "o": "100",
            "c": "105",
            "h": "110",
            "l": "95",
            "v": "12.5",
            "n": 20,
            "x": closed,
        },
    }


def ticker_payload() -> dict:
    return {
        "e": "24hrTicker",
        "E": 1000,
        "s": "ETHUSDT",
        "P": "2.5",
        "c": "2050",
        "o": "2000",
        "h": "2100",
        "l": "1950",
        "v": "1000",
    }


def depth_payload() -> dict:
    return {
        "e": "depthUpdate",
        "E": 1000,
        "s": "SOLUSDT",
        "U": 10,
        "u": 12,
        "b": [["100", "2"], ["99", "3"]],
        "a": [["101", "1"], ["102", "4"]],
    }


def test_stream_subscription_trade() -> None:
    sub = StreamSubscription("BTC/USDT", "trade")
    assert sub.stream_name() == "btcusdt@trade"


def test_stream_subscription_kline() -> None:
    sub = StreamSubscription("ETH/USDT", "kline", "1h")
    assert sub.stream_name() == "ethusdt@kline_1h"


def test_kline_requires_interval() -> None:
    with pytest.raises(ValueError):
        StreamSubscription("BTCUSDT", "kline").stream_name()


def test_parse_trade() -> None:
    event = BinanceMarketDataParser().parse(trade_payload())
    assert event.event_type == MarketDataEventType.TRADE
    assert isinstance(event.payload, TradeTick)
    assert event.payload.price == 101.5


def test_parse_json_bytes() -> None:
    event = BinanceMarketDataParser().parse(
        json.dumps(trade_payload()).encode("utf-8")
    )
    assert event.symbol == "BTCUSDT"


def test_parse_combined_stream() -> None:
    wrapped = {
        "stream": "btcusdt@trade",
        "data": trade_payload(),
    }
    event = BinanceMarketDataParser().parse(wrapped)
    assert event.event_type == MarketDataEventType.TRADE


def test_parse_kline() -> None:
    event = BinanceMarketDataParser().parse(kline_payload(True))
    assert isinstance(event.payload, KlineUpdate)
    assert event.payload.closed is True
    assert event.payload.close == 105


def test_parse_ticker() -> None:
    event = BinanceMarketDataParser().parse(ticker_payload())
    assert isinstance(event.payload, TickerUpdate)
    assert event.payload.last_price == 2050


def test_parse_depth() -> None:
    event = BinanceMarketDataParser().parse(depth_payload())
    assert isinstance(event.payload, DepthUpdate)
    assert event.payload.bids[0] == (100.0, 2.0)


def test_unknown_event() -> None:
    event = BinanceMarketDataParser().parse({"e": "other", "s": "X"})
    assert event.event_type == MarketDataEventType.UNKNOWN


def test_single_stream_url() -> None:
    engine = BinanceLiveMarketDataEngine(
        transport=FakeTransport(),
    )
    engine.subscribe(StreamSubscription("BTCUSDT", "trade"))
    assert engine.stream_url() == (
        BINANCE_SPOT_TESTNET_WS_BASE + "/ws/btcusdt@trade"
    )


def test_combined_stream_url() -> None:
    engine = BinanceLiveMarketDataEngine(
        transport=FakeTransport(),
    )
    engine.subscribe_many(
        [
            StreamSubscription("BTCUSDT", "trade"),
            StreamSubscription("ETHUSDT", "kline", "1m"),
        ]
    )
    url = engine.stream_url()
    assert "/stream?streams=" in url
    assert "btcusdt@trade/ethusdt@kline_1m" in url


def test_duplicate_subscription_ignored() -> None:
    engine = BinanceLiveMarketDataEngine(
        transport=FakeTransport(),
    )
    sub = StreamSubscription("BTCUSDT", "trade")
    engine.subscribe(sub)
    engine.subscribe(sub)
    assert len(engine.subscriptions) == 1


def test_connect_and_disconnect() -> None:
    transport = FakeTransport()
    engine = BinanceLiveMarketDataEngine(transport=transport)
    engine.subscribe(StreamSubscription("BTCUSDT", "trade"))
    engine.connect()
    assert engine.connected is True
    engine.disconnect()
    assert engine.connected is False
    assert transport.closed == 1


def test_process_trade_updates_state() -> None:
    engine = BinanceLiveMarketDataEngine(
        transport=FakeTransport(),
    )
    event = engine.process_message(trade_payload())
    assert event.event_type == MarketDataEventType.TRADE
    assert engine.state.last_prices["BTCUSDT"] == 101.5


def test_process_kline_updates_state() -> None:
    engine = BinanceLiveMarketDataEngine(
        transport=FakeTransport(),
    )
    engine.process_message(kline_payload())
    assert engine.state.last_prices["BTCUSDT"] == 105
    assert "BTCUSDT:1m" in engine.state.klines


def test_process_ticker_updates_state() -> None:
    engine = BinanceLiveMarketDataEngine(
        transport=FakeTransport(),
    )
    engine.process_message(ticker_payload())
    assert engine.state.last_prices["ETHUSDT"] == 2050


def test_process_depth_updates_state() -> None:
    engine = BinanceLiveMarketDataEngine(
        transport=FakeTransport(),
    )
    engine.process_message(depth_payload())
    assert "SOLUSDT" in engine.state.depth


def test_callback_called() -> None:
    seen = []
    engine = BinanceLiveMarketDataEngine(
        transport=FakeTransport(),
    )
    engine.add_callback(seen.append)
    engine.process_message(trade_payload())
    assert len(seen) == 1


def test_run_once_receives_message() -> None:
    transport = FakeTransport()
    transport.messages.append(trade_payload())
    engine = BinanceLiveMarketDataEngine(transport=transport)
    engine.subscribe(StreamSubscription("BTCUSDT", "trade"))
    event = engine.run_once()
    assert event is not None
    assert event.event_type == MarketDataEventType.TRADE


def test_run_processes_max_messages() -> None:
    transport = FakeTransport()
    transport.messages.extend([trade_payload(), kline_payload()])
    engine = BinanceLiveMarketDataEngine(transport=transport)
    engine.subscribe(StreamSubscription("BTCUSDT", "trade"))
    assert engine.run(max_messages=2) == 2


def test_reconnect_after_receive_failure() -> None:
    transport = FakeTransport()
    transport.fail_receive_count = 1
    transport.messages.append(trade_payload())
    engine = BinanceLiveMarketDataEngine(
        transport=transport,
        config=MarketDataConfig(reconnect_attempts=2),
    )
    engine.subscribe(StreamSubscription("BTCUSDT", "trade"))
    assert engine.run(max_messages=1) == 1
    assert engine.reconnect_count == 1


def test_heartbeat_health() -> None:
    now = {"value": 100.0}
    engine = BinanceLiveMarketDataEngine(
        transport=FakeTransport(),
        config=MarketDataConfig(heartbeat_timeout_seconds=10),
        time_fn=lambda: now["value"],
    )
    engine.process_message(trade_payload())
    assert engine.heartbeat_ok() is True
    now["value"] = 111.0
    assert engine.heartbeat_ok() is False


def test_event_history_is_bounded() -> None:
    engine = BinanceLiveMarketDataEngine(
        transport=FakeTransport(),
        config=MarketDataConfig(max_events=2),
    )
    engine.process_message(trade_payload())
    engine.process_message(kline_payload())
    engine.process_message(ticker_payload())
    assert len(engine.state.events) == 2


def test_snapshot() -> None:
    engine = BinanceLiveMarketDataEngine(
        transport=FakeTransport(),
    )
    engine.process_message(trade_payload())
    snapshot = engine.state.snapshot()
    assert snapshot["last_prices"]["BTCUSDT"] == 101.5
    assert snapshot["event_count"] == 1


def test_health_report() -> None:
    transport = FakeTransport()
    engine = BinanceLiveMarketDataEngine(transport=transport)
    engine.subscribe(StreamSubscription("BTCUSDT", "trade"))
    engine.connect()
    report = engine.health_report()
    assert report["connected"] is True
    assert report["subscription_count"] == 1
    assert report["connection_count"] == 1
