from __future__ import annotations

import pytest

from engine.exchange_layer import (
    BinanceExchangeAdapter,
    ExchangeConfig,
    ExchangeConnectionError,
    ExchangeMode,
    ExchangeOrderError,
    ExchangeOrderRequest,
    ExchangeOrderSide,
    ExchangeOrderStatus,
    ExchangeOrderType,
    ExchangeRateLimitError,
    ExchangeRouter,
    InMemoryExchangeAdapter,
    RetryExecutor,
)


def build_adapter() -> InMemoryExchangeAdapter:
    adapter = InMemoryExchangeAdapter(
        ExchangeConfig(
            mode=ExchangeMode.TESTNET,
            max_retries=2,
            retry_delay_seconds=0.0,
        ),
        starting_balances={"USDT": 10_000},
        prices={"BTC/USDT": 100},
    )
    adapter.connect()
    return adapter


def test_live_mode_requires_explicit_permission() -> None:
    with pytest.raises(ValueError):
        ExchangeConfig(
            mode=ExchangeMode.LIVE,
            allow_live_trading=False,
        ).validate()


def test_connection_required() -> None:
    adapter = InMemoryExchangeAdapter()

    with pytest.raises(ExchangeConnectionError):
        adapter.get_balances()


def test_market_buy_order_fills() -> None:
    adapter = build_adapter()
    request = ExchangeOrderRequest(
        symbol="BTC/USDT",
        side=ExchangeOrderSide.BUY,
        order_type=ExchangeOrderType.MARKET,
        quantity=10,
    )

    order = adapter.place_order(request)

    assert order.status == ExchangeOrderStatus.FILLED
    assert order.filled_quantity == 10
    assert order.average_price == 100
    assert adapter.balances["USDT"].free == 9_000
    assert adapter.positions["BTC/USDT"].quantity == 10


def test_market_sell_order_fills() -> None:
    adapter = build_adapter()
    buy = ExchangeOrderRequest(
        symbol="BTC/USDT",
        side=ExchangeOrderSide.BUY,
        order_type=ExchangeOrderType.MARKET,
        quantity=10,
    )
    adapter.place_order(buy)
    adapter.update_price("BTC/USDT", 110)

    sell = ExchangeOrderRequest(
        symbol="BTC/USDT",
        side=ExchangeOrderSide.SELL,
        order_type=ExchangeOrderType.MARKET,
        quantity=4,
    )
    order = adapter.place_order(sell)

    assert order.status == ExchangeOrderStatus.FILLED
    assert adapter.positions["BTC/USDT"].quantity == 6
    assert adapter.balances["USDT"].free == 9_440


def test_insufficient_balance_rejects_order() -> None:
    adapter = build_adapter()
    request = ExchangeOrderRequest(
        symbol="BTC/USDT",
        side=ExchangeOrderSide.BUY,
        order_type=ExchangeOrderType.MARKET,
        quantity=200,
    )

    order = adapter.place_order(request)

    assert order.status == ExchangeOrderStatus.REJECTED
    assert "Yetersiz" in order.raw["reject_reason"]


def test_order_lookup() -> None:
    adapter = build_adapter()
    order = adapter.place_order(
        ExchangeOrderRequest(
            symbol="BTC/USDT",
            side=ExchangeOrderSide.BUY,
            order_type=ExchangeOrderType.MARKET,
            quantity=1,
        )
    )

    fetched = adapter.get_order(order.exchange_order_id)

    assert fetched.exchange_order_id == order.exchange_order_id


def test_missing_order_raises() -> None:
    adapter = build_adapter()

    with pytest.raises(ExchangeOrderError):
        adapter.get_order("missing")


def test_retry_executor_retries_rate_limit() -> None:
    attempts = {"count": 0}

    def operation() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ExchangeRateLimitError("rate limit")
        return "OK"

    retry = RetryExecutor(max_retries=2, delay_seconds=0.0)

    assert retry.run(operation) == "OK"
    assert attempts["count"] == 3


def test_binance_testnet_environment() -> None:
    adapter = BinanceExchangeAdapter(
        ExchangeConfig(
            mode=ExchangeMode.TESTNET,
            exchange_name="BINANCE",
        )
    )

    assert adapter.environment_name == "BINANCE_TESTNET"


def test_router_switches_active_adapter() -> None:
    router = ExchangeRouter()
    testnet = BinanceExchangeAdapter(
        ExchangeConfig(mode=ExchangeMode.TESTNET)
    )
    paper = InMemoryExchangeAdapter(
        ExchangeConfig(mode=ExchangeMode.PAPER)
    )

    router.register("testnet", testnet, make_active=True)
    router.register("paper", paper)
    router.set_active("paper")

    assert router.active() is paper
    assert router.report()["active"] == "PAPER"
