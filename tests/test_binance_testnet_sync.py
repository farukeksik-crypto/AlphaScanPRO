from __future__ import annotations

import pytest

from engine.binance_testnet_sync import (
    BalanceSnapshot,
    BinanceTestnetSyncConfig,
    BinanceTestnetSyncManager,
    OpenOrderSnapshot,
    SyncEventType,
    SyncState,
)


class Clock:
    def __init__(self):
        self.value = 1000.0

    def now(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class FakeClient:
    def __init__(self):
        self.fail_ping = False
        self.fail_account = False
        self.fail_orders = False
        self.fail_trades = False
        self.ping_calls = 0

    def ping(self):
        self.ping_calls += 1
        if self.fail_ping:
            raise RuntimeError("ping failed")
        return {}

    def get_server_time(self):
        if self.fail_ping:
            raise RuntimeError("server failed")
        return {"serverTime": 123456789}

    def get_account(self, **kwargs):
        if self.fail_account:
            raise RuntimeError("account failed")
        return {
            "balances": [
                {"asset": "USDT", "free": "100", "locked": "5"},
                {"asset": "BTC", "free": "0.1", "locked": "0"},
                {"asset": "ZERO", "free": "0", "locked": "0"},
            ]
        }

    def get_open_orders(self, **kwargs):
        if self.fail_orders:
            raise RuntimeError("orders failed")
        return [
            {
                "symbol": kwargs.get("symbol", "BTCUSDT"),
                "orderId": 1,
                "clientOrderId": "abc",
                "side": "BUY",
                "type": "LIMIT",
                "status": "NEW",
                "price": "100",
                "origQty": "2",
                "executedQty": "0.5",
                "updateTime": 123,
            }
        ]

    def get_my_trades(self, **kwargs):
        if self.fail_trades:
            raise RuntimeError("trades failed")
        return [
            {
                "id": 10,
                "orderId": 1,
                "price": "100",
                "qty": "0.5",
                "quoteQty": "50",
                "commission": "0.01",
                "commissionAsset": "USDT",
                "isBuyer": True,
                "time": 123,
            }
        ]


def manager(**kwargs):
    clock = Clock()
    config = BinanceTestnetSyncConfig(
        enabled=True,
        reconnect_delay_seconds=0,
        **kwargs,
    )
    item = BinanceTestnetSyncManager(
        client=FakeClient(),
        config=config,
        time_fn=clock.now,
        sleep_fn=lambda _: None,
    )
    return item, clock


def test_config_validation_poll() -> None:
    with pytest.raises(ValueError):
        BinanceTestnetSyncConfig(poll_interval_seconds=0).validate()


def test_config_validation_reconnect() -> None:
    with pytest.raises(ValueError):
        BinanceTestnetSyncConfig(max_reconnect_attempts=0).validate()


def test_balance_total() -> None:
    item = BalanceSnapshot("USDT", 10, 5)
    assert item.total == 15


def test_open_order_remaining() -> None:
    item = OpenOrderSnapshot(
        "BTCUSDT", "1", None, "BUY", "LIMIT", "NEW", 100, 2, 0.5
    )
    assert item.remaining_quantity == 1.5


def test_symbol_normalize() -> None:
    assert BinanceTestnetSyncManager.normalize_symbol("btc/usdt") == "BTCUSDT"


def test_connect_disabled() -> None:
    config = BinanceTestnetSyncConfig(enabled=False)
    item = BinanceTestnetSyncManager(client=FakeClient(), config=config)
    assert item.connect() is False
    assert item.state == SyncState.DISCONNECTED


def test_connect_success() -> None:
    item, _ = manager()
    assert item.connect() is True
    assert item.state == SyncState.CONNECTED


def test_connect_failure() -> None:
    item, _ = manager()
    item.client.fail_ping = True
    assert item.connect() is False
    assert item.state == SyncState.ERROR


def test_reconnect_success() -> None:
    item, _ = manager()
    assert item.reconnect() is True
    assert item.state == SyncState.CONNECTED


def test_reconnect_failure() -> None:
    item, _ = manager(max_reconnect_attempts=2)
    item.client.fail_ping = True
    assert item.reconnect() is False
    assert item.state == SyncState.ERROR


def test_heartbeat_skips_recent() -> None:
    item, _ = manager()
    item.connect()
    calls = item.client.ping_calls
    assert item.heartbeat() is True
    assert item.client.ping_calls == calls


def test_heartbeat_force() -> None:
    item, _ = manager()
    item.connect()
    calls = item.client.ping_calls
    assert item.heartbeat(force=True) is True
    assert item.client.ping_calls == calls + 1


def test_heartbeat_failure() -> None:
    item, _ = manager()
    item.connect()
    item.client.fail_ping = True
    assert item.heartbeat(force=True) is False
    assert item.state == SyncState.DEGRADED


def test_sync_account() -> None:
    item, _ = manager()
    result = item.sync_account()
    assert len(result) == 2
    assert item.balances["USDT"].total == 105


def test_sync_account_excludes_zero() -> None:
    item, _ = manager()
    item.sync_account()
    assert "ZERO" not in item.balances


def test_sync_open_orders() -> None:
    item, _ = manager()
    result = item.sync_open_orders("BTC/USDT")
    assert len(result) == 1
    assert "BTCUSDT:1" in item.open_orders


def test_sync_trades() -> None:
    item, _ = manager()
    result = item.sync_trades(symbol="BTCUSDT")
    assert len(result) == 1
    assert "BTCUSDT:10" in item.trades


def test_sync_trades_deduplicate() -> None:
    item, _ = manager()
    item.sync_trades(symbol="BTCUSDT")
    item.sync_trades(symbol="BTCUSDT")
    assert len(item.trades) == 1


def test_sync_all() -> None:
    item, _ = manager()
    result = item.sync_all(symbol="BTCUSDT")
    assert result["failures"] == 0
    assert result["state"] == "CONNECTED"


def test_sync_all_degraded() -> None:
    item, _ = manager()
    item.client.fail_orders = True
    result = item.sync_all(symbol="BTCUSDT")
    assert result["failures"] == 1
    assert item.state == SyncState.DEGRADED


def test_sync_all_error() -> None:
    item, _ = manager()
    item.client.fail_orders = True
    item.client.fail_trades = True
    result = item.sync_all(symbol="BTCUSDT")
    assert result["failures"] == 2
    assert item.state == SyncState.ERROR


def test_sync_all_disabled() -> None:
    item, _ = manager()
    item.disable()
    with pytest.raises(RuntimeError):
        item.sync_all(symbol="BTCUSDT")


def test_apply_order_update_new() -> None:
    item, _ = manager()
    result = item.apply_order_update(
        {
            "symbol": "BTCUSDT",
            "orderId": 1,
            "side": "BUY",
            "type": "LIMIT",
            "status": "NEW",
            "price": "100",
            "origQty": "1",
            "executedQty": "0",
        }
    )
    assert result["status"] == "NEW"
    assert "BTCUSDT:1" in item.open_orders


def test_apply_order_update_filled_removes() -> None:
    item, _ = manager()
    item.apply_order_update(
        {
            "symbol": "BTCUSDT",
            "orderId": 1,
            "side": "BUY",
            "type": "LIMIT",
            "status": "NEW",
            "price": "100",
            "origQty": "1",
            "executedQty": "0",
        }
    )
    item.apply_order_update(
        {
            "symbol": "BTCUSDT",
            "orderId": 1,
            "side": "BUY",
            "type": "LIMIT",
            "status": "FILLED",
            "price": "100",
            "origQty": "1",
            "executedQty": "1",
        }
    )
    assert "BTCUSDT:1" not in item.open_orders


def test_callback() -> None:
    item, _ = manager()
    events = []
    item.register_callback(events.append)
    item.sync_account()
    assert events[-1].event_type == SyncEventType.ACCOUNT


def test_callback_unregister() -> None:
    item, _ = manager()
    events = []
    item.register_callback(events.append)
    item.unregister_callback(events.append)
    item.sync_account()
    assert events == []


def test_callback_error_isolated() -> None:
    item, _ = manager()

    def broken(_):
        raise RuntimeError("boom")

    item.register_callback(broken)
    item.sync_account()
    assert item.events[-1].success is True


def test_event_limit() -> None:
    item, _ = manager(max_events=2)
    item.sync_account()
    item.sync_open_orders()
    item.sync_trades(symbol="BTCUSDT")
    assert len(item.events) == 2


def test_is_stale_initial() -> None:
    item, _ = manager()
    assert item.is_stale() is True


def test_is_stale_after_sync() -> None:
    item, clock = manager(stale_after_seconds=10)
    item.sync_all(symbol="BTCUSDT")
    assert item.is_stale() is False
    clock.advance(11)
    assert item.is_stale() is True


def test_health_report() -> None:
    item, _ = manager()
    report = item.health_report()
    assert report["enabled"] is True
    assert "state" in report


def test_dashboard_payload() -> None:
    item, _ = manager()
    item.sync_all(symbol="BTCUSDT")
    data = item.dashboard_payload()
    assert "health" in data
    assert "balances" in data
    assert "open_orders" in data
    assert "recent_trades" in data
    assert "recent_events" in data


def test_enable_disable() -> None:
    item, _ = manager()
    item.disable()
    assert item.config.enabled is False
    item.enable()
    assert item.config.enabled is True


def test_order_key() -> None:
    assert BinanceTestnetSyncManager.order_key("BTCUSDT", "1") == "BTCUSDT:1"


def test_trade_key() -> None:
    assert BinanceTestnetSyncManager.trade_key("BTCUSDT", "10") == "BTCUSDT:10"
