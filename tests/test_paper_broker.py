from __future__ import annotations

import pytest

from engine.paper_broker import (
    PaperBroker,
    PaperBrokerConfig,
    PaperOrderRequest,
    PaperOrderSide,
    PaperOrderStatus,
    PaperOrderType,
)


def make_broker(**kwargs):
    data = {
        "starting_cash": 10_000.0,
        "commission_rate": 0.001,
        "slippage_rate": 0.0,
    }
    data.update(kwargs)
    return PaperBroker(PaperBrokerConfig(**data))


def test_config_validation():
    with pytest.raises(ValueError):
        PaperBrokerConfig(starting_cash=-1)
    with pytest.raises(ValueError):
        PaperBrokerConfig(commission_rate=1)
    with pytest.raises(ValueError):
        PaperBrokerConfig(slippage_rate=-1)
    with pytest.raises(ValueError):
        PaperBrokerConfig(max_fill_ratio=0)


def test_request_normalization():
    request = PaperOrderRequest(
        symbol=" btcusdt ",
        side="BUY",
        order_type="MARKET",
        quantity=1,
    )
    assert request.symbol == "BTCUSDT"
    assert request.side == PaperOrderSide.BUY


def test_invalid_quantity():
    with pytest.raises(ValueError):
        PaperOrderRequest(
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
            quantity=0,
        )


def test_limit_requires_price():
    with pytest.raises(ValueError):
        PaperOrderRequest(
            symbol="BTCUSDT",
            side="BUY",
            order_type="LIMIT",
            quantity=1,
        )


def test_market_buy_fill():
    broker = make_broker()
    order = broker.submit_order(
        PaperOrderRequest(
            symbol="BTCUSDT",
            side="BUY",
            order_type="MARKET",
            quantity=2,
        ),
        market_price=100,
    )
    assert order.status == PaperOrderStatus.FILLED
    assert broker.position("BTCUSDT") == 2
    assert broker.cash == pytest.approx(9799.8)


def test_market_buy_slippage():
    broker = make_broker(slippage_rate=0.01)
    order = broker.submit_order(
        PaperOrderRequest("BTCUSDT", "BUY", "MARKET", 1),
        market_price=100,
    )
    assert order.average_fill_price == pytest.approx(101)


def test_market_sell_slippage():
    broker = make_broker(slippage_rate=0.01)
    broker.submit_order(
        PaperOrderRequest("BTCUSDT", "BUY", "MARKET", 2),
        market_price=100,
    )
    order = broker.submit_order(
        PaperOrderRequest("BTCUSDT", "SELL", "MARKET", 1),
        market_price=100,
    )
    assert order.average_fill_price == pytest.approx(99)


def test_market_requires_price():
    broker = make_broker()
    order = broker.submit_order(
        PaperOrderRequest("BTCUSDT", "BUY", "MARKET", 1)
    )
    assert order.status == PaperOrderStatus.REJECTED


def test_limit_buy_waits():
    broker = make_broker()
    order = broker.submit_order(
        PaperOrderRequest("BTCUSDT", "BUY", "LIMIT", 1, limit_price=95),
        market_price=100,
    )
    assert order.status == PaperOrderStatus.OPEN


def test_limit_buy_fills():
    broker = make_broker()
    order = broker.submit_order(
        PaperOrderRequest("BTCUSDT", "BUY", "LIMIT", 1, limit_price=100),
        market_price=99,
    )
    assert order.status == PaperOrderStatus.FILLED
    assert order.average_fill_price == pytest.approx(99)


def test_limit_sell_waits():
    broker = make_broker()
    broker.submit_order(
        PaperOrderRequest("BTCUSDT", "BUY", "MARKET", 1),
        market_price=100,
    )
    order = broker.submit_order(
        PaperOrderRequest("BTCUSDT", "SELL", "LIMIT", 1, limit_price=110),
        market_price=105,
    )
    assert order.status == PaperOrderStatus.OPEN


def test_limit_sell_fills():
    broker = make_broker()
    broker.submit_order(
        PaperOrderRequest("BTCUSDT", "BUY", "MARKET", 1),
        market_price=100,
    )
    order = broker.submit_order(
        PaperOrderRequest("BTCUSDT", "SELL", "LIMIT", 1, limit_price=105),
        market_price=110,
    )
    assert order.status == PaperOrderStatus.FILLED
    assert order.average_fill_price == pytest.approx(110)


def test_partial_fill_from_liquidity():
    broker = make_broker()
    order = broker.submit_order(
        PaperOrderRequest("BTCUSDT", "BUY", "MARKET", 10),
        market_price=100,
        available_liquidity=4,
    )
    assert order.status == PaperOrderStatus.PARTIALLY_FILLED
    assert order.filled_quantity == 4
    assert order.remaining_quantity == 6


def test_continue_partial_fill():
    broker = make_broker()
    order = broker.submit_order(
        PaperOrderRequest("BTCUSDT", "BUY", "LIMIT", 10, limit_price=100),
        market_price=100,
        available_liquidity=4,
    )
    broker.process_order(order.order_id, market_price=99, available_liquidity=6)
    assert order.status == PaperOrderStatus.FILLED
    assert order.filled_quantity == 10


def test_partial_fill_disabled():
    broker = make_broker(allow_partial_fills=False)
    order = broker.submit_order(
        PaperOrderRequest("BTCUSDT", "BUY", "MARKET", 10),
        market_price=100,
        available_liquidity=4,
    )
    assert order.status == PaperOrderStatus.OPEN
    assert order.filled_quantity == 0


def test_max_fill_ratio():
    broker = make_broker(max_fill_ratio=0.5)
    order = broker.submit_order(
        PaperOrderRequest("BTCUSDT", "BUY", "MARKET", 10),
        market_price=100,
    )
    assert order.status == PaperOrderStatus.PARTIALLY_FILLED
    assert order.filled_quantity == 5


def test_insufficient_cash_rejects():
    broker = make_broker(starting_cash=10, allow_partial_fills=False)
    order = broker.submit_order(
        PaperOrderRequest("BTCUSDT", "BUY", "MARKET", 1),
        market_price=100,
    )
    assert order.status == PaperOrderStatus.REJECTED


def test_insufficient_cash_partial():
    broker = make_broker(starting_cash=100)
    order = broker.submit_order(
        PaperOrderRequest("BTCUSDT", "BUY", "MARKET", 2),
        market_price=100,
    )
    assert order.status == PaperOrderStatus.PARTIALLY_FILLED
    assert order.filled_quantity < 1


def test_sell_without_position_rejects():
    broker = make_broker()
    order = broker.submit_order(
        PaperOrderRequest("BTCUSDT", "SELL", "MARKET", 1),
        market_price=100,
    )
    assert order.status == PaperOrderStatus.REJECTED


def test_sell_partial_to_available_position():
    broker = make_broker()
    broker.submit_order(
        PaperOrderRequest("BTCUSDT", "BUY", "MARKET", 1),
        market_price=100,
    )
    order = broker.submit_order(
        PaperOrderRequest("BTCUSDT", "SELL", "MARKET", 2),
        market_price=110,
    )
    assert order.status == PaperOrderStatus.PARTIALLY_FILLED
    assert order.filled_quantity == 1
    assert broker.position("BTCUSDT") == 0


def test_short_selling_enabled():
    broker = make_broker(allow_short_selling=True)
    order = broker.submit_order(
        PaperOrderRequest("BTCUSDT", "SELL", "MARKET", 1),
        market_price=100,
    )
    assert order.status == PaperOrderStatus.FILLED
    assert broker.position("BTCUSDT") == -1


def test_cancel_open_order():
    broker = make_broker()
    order = broker.submit_order(
        PaperOrderRequest("BTCUSDT", "BUY", "LIMIT", 1, limit_price=90),
        market_price=100,
    )
    broker.cancel_order(order.order_id)
    assert order.status == PaperOrderStatus.CANCELLED


def test_cancel_filled_order_no_change():
    broker = make_broker()
    order = broker.submit_order(
        PaperOrderRequest("BTCUSDT", "BUY", "MARKET", 1),
        market_price=100,
    )
    broker.cancel_order(order.order_id)
    assert order.status == PaperOrderStatus.FILLED


def test_duplicate_client_order_id():
    broker = make_broker()
    request = PaperOrderRequest(
        "BTCUSDT",
        "BUY",
        "MARKET",
        1,
        client_order_id="abc",
    )
    first = broker.submit_order(request, market_price=100)
    second = broker.submit_order(request, market_price=200)
    assert first.order_id == second.order_id
    assert len(broker.orders()) == 1


def test_open_orders():
    broker = make_broker()
    broker.submit_order(
        PaperOrderRequest("BTCUSDT", "BUY", "LIMIT", 1, limit_price=90),
        market_price=100,
    )
    assert len(broker.open_orders()) == 1


def test_fills_list():
    broker = make_broker()
    broker.submit_order(
        PaperOrderRequest("BTCUSDT", "BUY", "MARKET", 1),
        market_price=100,
    )
    assert len(broker.fills()) == 1


def test_equity():
    broker = make_broker()
    broker.submit_order(
        PaperOrderRequest("BTCUSDT", "BUY", "MARKET", 1),
        market_price=100,
    )
    assert broker.equity({"BTCUSDT": 120}) == pytest.approx(10019.9)


def test_dashboard():
    broker = make_broker()
    broker.submit_order(
        PaperOrderRequest("BTCUSDT", "BUY", "MARKET", 1),
        market_price=100,
    )
    data = broker.dashboard({"BTCUSDT": 110})
    assert data["order_count"] == 1
    assert data["fill_count"] == 1
    assert "FILLED" in data["status_counts"]


def test_order_to_dict():
    broker = make_broker()
    order = broker.submit_order(
        PaperOrderRequest("BTCUSDT", "BUY", "MARKET", 1),
        market_price=100,
    )
    data = order.to_dict()
    assert data["symbol"] == "BTCUSDT"
    assert data["fills"][0]["quantity"] == 1


def test_negative_liquidity():
    broker = make_broker()
    with pytest.raises(ValueError):
        broker.submit_order(
            PaperOrderRequest("BTCUSDT", "BUY", "MARKET", 1),
            market_price=100,
            available_liquidity=-1,
        )


def test_process_terminal_order():
    broker = make_broker()
    order = broker.submit_order(
        PaperOrderRequest("BTCUSDT", "BUY", "MARKET", 1),
        market_price=100,
    )
    same = broker.process_order(order.order_id, market_price=120)
    assert same.status == PaperOrderStatus.FILLED
    assert len(same.fills) == 1


def test_average_fill_price():
    broker = make_broker()
    order = broker.submit_order(
        PaperOrderRequest("BTCUSDT", "BUY", "LIMIT", 2, limit_price=110),
        market_price=100,
        available_liquidity=1,
    )
    broker.process_order(order.order_id, market_price=110, available_liquidity=1)
    assert order.average_fill_price == pytest.approx(105)


def test_commission_total():
    broker = make_broker()
    order = broker.submit_order(
        PaperOrderRequest("BTCUSDT", "BUY", "MARKET", 2),
        market_price=100,
    )
    assert order.total_commission == pytest.approx(0.2)


def test_position_symbol_normalization():
    broker = make_broker()
    broker.submit_order(
        PaperOrderRequest("BTCUSDT", "BUY", "MARKET", 1),
        market_price=100,
    )
    assert broker.position(" btcusdt ") == 1
