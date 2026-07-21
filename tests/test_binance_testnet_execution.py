from __future__ import annotations

import pytest

from engine.binance_testnet_execution import (
    BinanceTestnetExecutionConfig,
    BinanceTestnetExecutionEngine,
    BinanceTestnetRuntimeBridge,
    SymbolRules,
    TestnetOrderStatus,
)
from engine.robot_runtime import RuntimeAction, StrategyDecision


class FakeClient:
    def __init__(self):
        self.created = []
        self.queried = []
        self.canceled = []

    def create_order(self, **kwargs):
        self.created.append(kwargs)
        return {
            "symbol": kwargs["symbol"],
            "orderId": 123,
            "clientOrderId": "abc",
            "status": "NEW",
            "executedQty": "0",
            "cummulativeQuoteQty": "0",
        }

    def get_order(self, **kwargs):
        self.queried.append(kwargs)
        return {
            "symbol": kwargs["symbol"],
            "orderId": kwargs.get("orderId", 123),
            "status": "FILLED",
            "executedQty": "0.5",
            "cummulativeQuoteQty": "50",
        }

    def cancel_order(self, **kwargs):
        self.canceled.append(kwargs)
        return {
            "symbol": kwargs["symbol"],
            "orderId": kwargs.get("orderId", 123),
            "status": "CANCELED",
        }

    def get_symbol_info(self, symbol):
        return {
            "symbol": symbol,
            "filters": [
                {
                    "filterType": "LOT_SIZE",
                    "minQty": "0.001",
                    "maxQty": "1000",
                    "stepSize": "0.001",
                },
                {
                    "filterType": "MIN_NOTIONAL",
                    "minNotional": "10",
                },
                {
                    "filterType": "PRICE_FILTER",
                    "tickSize": "0.01",
                },
            ],
        }


class FakeRuntime:
    def __init__(self):
        self.execution = None


def make_decision(
    action=RuntimeAction.BUY,
    *,
    price=100.0,
    quantity=None,
    metadata=None,
):
    return StrategyDecision(
        symbol="BTCUSDT",
        action=action,
        score=80,
        reason="Test karar",
        quantity=quantity,
        price=price,
        metadata=metadata or {},
    )


def engine(**config_kwargs):
    config = BinanceTestnetExecutionConfig(
        enabled=True,
        dry_run=False,
        default_quote_order_value=50,
        max_quote_order_value=250,
        min_quote_order_value=10,
        **config_kwargs,
    )
    return BinanceTestnetExecutionEngine(
        client=FakeClient(),
        config=config,
    )


def test_config_validation() -> None:
    with pytest.raises(ValueError):
        BinanceTestnetExecutionConfig(
            min_quote_order_value=100,
            max_quote_order_value=50,
        ).validate()


def test_symbol_normalization() -> None:
    assert BinanceTestnetExecutionEngine.normalize_symbol("btc/usdt") == "BTCUSDT"


def test_quantity_normalization() -> None:
    rules = SymbolRules("BTCUSDT", min_qty=0.001, step_size=0.001)
    assert rules.normalize_quantity(0.1239) == pytest.approx(0.123)


def test_price_normalization() -> None:
    rules = SymbolRules("BTCUSDT", tick_size=0.01)
    assert rules.normalize_price(100.129) == pytest.approx(100.12)


def test_disabled_execution_skipped() -> None:
    config = BinanceTestnetExecutionConfig(
        enabled=False,
        require_explicit_enable=True,
    )
    item = BinanceTestnetExecutionEngine(
        client=FakeClient(),
        config=config,
    )
    result = item.execute(make_decision())
    assert result["status"] == "SKIPPED"


def test_hold_skipped() -> None:
    result = engine().execute(make_decision(RuntimeAction.HOLD))
    assert result["status"] == "SKIPPED"


def test_market_buy_order() -> None:
    item = engine()
    result = item.execute(make_decision())
    assert result["status"] == "NEW"
    assert item.client.created[0]["side"] == "BUY"
    assert item.client.created[0]["type"] == "MARKET"


def test_market_sell_order() -> None:
    item = engine()
    result = item.execute(make_decision(RuntimeAction.SELL))
    assert result["status"] == "NEW"
    assert item.client.created[0]["side"] == "SELL"


def test_limit_order() -> None:
    item = engine()
    result = item.execute(
        make_decision(
            metadata={"order_type": "LIMIT"},
            price=100.129,
        )
    )
    payload = item.client.created[0]
    assert payload["type"] == "LIMIT"
    assert payload["price"] == "100.12"
    assert result["normalized_price"] == pytest.approx(100.12)


def test_quote_value_to_quantity() -> None:
    item = engine()
    result = item.execute(make_decision(price=100))
    assert result["normalized_quantity"] == pytest.approx(0.5)


def test_explicit_quantity() -> None:
    item = engine()
    result = item.execute(make_decision(quantity=0.3339))
    assert result["normalized_quantity"] == pytest.approx(0.333)


def test_max_quote_cap() -> None:
    item = engine()
    result = item.execute(
        make_decision(
            metadata={"quote_order_value": 999},
            price=100,
        )
    )
    assert result["quote_order_value"] == 250


def test_min_quote_rejected() -> None:
    item = engine()
    result = item.execute(
        make_decision(
            metadata={"quote_order_value": 5},
        )
    )
    assert result["status"] == "ERROR"


def test_min_notional_rejected() -> None:
    item = engine()
    result = item.execute(
        make_decision(
            quantity=0.001,
            price=100,
        )
    )
    assert result["status"] == "ERROR"


def test_duplicate_open_order_rejected() -> None:
    item = engine()
    item.execute(make_decision())
    result = item.execute(make_decision())
    assert result["status"] == "REJECTED"


def test_dry_run_does_not_call_client() -> None:
    config = BinanceTestnetExecutionConfig(
        enabled=True,
        dry_run=True,
        default_quote_order_value=50,
    )
    client = FakeClient()
    item = BinanceTestnetExecutionEngine(client=client, config=config)
    result = item.execute(make_decision())
    assert result["status"] == "NEW"
    assert client.created == []


def test_price_from_kline_context() -> None:
    item = engine()
    decision = make_decision()
    decision.price = None
    result = item.execute(decision, {"kline": {"close": 100}})
    assert result["requested_price"] == 100


def test_price_from_snapshot_context() -> None:
    item = engine()
    decision = make_decision()
    decision.price = None
    result = item.execute(
        decision,
        {"market_snapshot": {"last_prices": {"BTCUSDT": 100}}},
    )
    assert result["requested_price"] == 100


def test_refresh_order() -> None:
    item = engine()
    item.execute(make_decision())
    response = item.refresh_order("BTCUSDT")
    assert response["status"] == "FILLED"
    assert "BTCUSDT" not in item.open_orders


def test_cancel_order() -> None:
    item = engine()
    item.execute(make_decision())
    response = item.cancel_open_order("BTCUSDT")
    assert response["status"] == "CANCELED"
    assert "BTCUSDT" not in item.open_orders


def test_symbol_rules_cache() -> None:
    item = engine()
    first = item.get_symbol_rules("BTCUSDT")
    second = item.get_symbol_rules("BTCUSDT")
    assert first is second


def test_orders_report() -> None:
    item = engine()
    item.execute(make_decision())
    assert len(item.orders_report(limit=1)) == 1


def test_health_report() -> None:
    item = engine()
    report = item.health_report()
    assert report["enabled"] is True
    assert report["dry_run"] is False


def test_enable_disable() -> None:
    item = engine()
    item.disable()
    assert item.config.enabled is False
    item.enable()
    assert item.config.enabled is True


def test_bridge_bind() -> None:
    runtime = FakeRuntime()
    item = engine()
    bridge = BinanceTestnetRuntimeBridge(
        runtime=runtime,
        execution_engine=item,
    )
    bridge.bind()
    assert runtime.execution is item


def test_bridge_bind_once() -> None:
    runtime = FakeRuntime()
    item = engine()
    bridge = BinanceTestnetRuntimeBridge(
        runtime=runtime,
        execution_engine=item,
    )
    bridge.bind()
    bridge.bind()
    assert runtime.execution is item


def test_bridge_dashboard() -> None:
    runtime = FakeRuntime()
    item = engine()
    bridge = BinanceTestnetRuntimeBridge(
        runtime=runtime,
        execution_engine=item,
    )
    data = bridge.dashboard()
    assert "health" in data
    assert "recent_orders" in data


def test_unknown_status_mapping() -> None:
    assert (
        BinanceTestnetExecutionEngine._map_status("SOMETHING")
        == TestnetOrderStatus.UNKNOWN
    )


def test_market_order_disabled() -> None:
    item = engine(allow_market_orders=False)
    result = item.execute(make_decision())
    assert result["status"] == "REJECTED"


def test_limit_order_disabled() -> None:
    item = engine(allow_limit_orders=False)
    result = item.execute(
        make_decision(metadata={"order_type": "LIMIT"})
    )
    assert result["status"] == "REJECTED"
