from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from engine.binance_testnet_client import (
    BINANCE_SPOT_TESTNET_BASE_URL,
    BinanceCredentials,
    BinanceSpotTestnetClient,
)
from engine.exchange_layer import (
    ExchangeAuthenticationError,
    ExchangeConfig,
    ExchangeConnectionError,
    ExchangeMode,
    ExchangeOrderRequest,
    ExchangeOrderSide,
    ExchangeOrderStatus,
    ExchangeOrderType,
)


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.responses: list[object] = []

    def queue(self, payload: object) -> None:
        self.responses.append(payload)

    def request(self, **kwargs):
        self.calls.append(kwargs)
        if not self.responses:
            return {}
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def build_client(
    transport: FakeTransport | None = None,
) -> BinanceSpotTestnetClient:
    return BinanceSpotTestnetClient(
        ExchangeConfig(
            mode=ExchangeMode.TESTNET,
            exchange_name="BINANCE",
            recv_window_ms=5_000,
            max_retries=0,
        ),
        credentials=BinanceCredentials(
            api_key="test-key",
            api_secret="test-secret",
        ),
        transport=transport or FakeTransport(),
        time_ms_fn=lambda: 1_700_000_000_000,
    )


def test_credentials_required() -> None:
    credentials = BinanceCredentials("", "")

    with pytest.raises(ExchangeAuthenticationError):
        credentials.validate()


def test_connect_uses_ping() -> None:
    transport = FakeTransport()
    transport.queue({})
    client = build_client(transport)

    assert client.connect() is True
    assert client.connected is True
    assert transport.calls[0]["url"] == (
        BINANCE_SPOT_TESTNET_BASE_URL + "/api/v3/ping"
    )


def test_public_price_request() -> None:
    transport = FakeTransport()
    transport.queue({"price": "123.45"})
    client = build_client(transport)

    price = client.get_price("BTC/USDT")

    assert price == 123.45
    assert "symbol=BTCUSDT" in transport.calls[0]["url"]


def test_signed_request_contains_header_timestamp_and_signature() -> None:
    transport = FakeTransport()
    transport.queue({})
    transport.queue(
        {
            "balances": [
                {"asset": "USDT", "free": "1000", "locked": "0"}
            ]
        }
    )
    client = build_client(transport)
    client.connect()

    balances = client.get_balances()

    call = transport.calls[-1]
    parsed = urlparse(call["url"])
    params = parse_qs(parsed.query)

    assert balances[0].asset == "USDT"
    assert call["headers"]["X-MBX-APIKEY"] == "test-key"
    assert params["timestamp"] == ["1700000000000"]
    assert params["recvWindow"] == ["5000"]
    assert "signature" in params


def test_market_order_mapping() -> None:
    transport = FakeTransport()
    transport.queue({})
    transport.queue(
        {
            "symbol": "BTCUSDT",
            "orderId": 123,
            "clientOrderId": "client-1",
            "status": "FILLED",
            "side": "BUY",
            "type": "MARKET",
            "origQty": "2",
            "executedQty": "2",
            "cummulativeQuoteQty": "200",
            "fills": [
                {"commission": "0.1"},
                {"commission": "0.1"},
            ],
        }
    )
    client = build_client(transport)
    client.connect()

    request = ExchangeOrderRequest(
        symbol="BTC/USDT",
        side=ExchangeOrderSide.BUY,
        order_type=ExchangeOrderType.MARKET,
        quantity=2,
        client_order_id="client-1",
    )
    order = client.place_order(request)

    assert order.exchange_order_id == "123"
    assert order.status == ExchangeOrderStatus.FILLED
    assert order.average_price == 100
    assert order.commission == pytest.approx(0.2)


def test_test_order_endpoint() -> None:
    transport = FakeTransport()
    transport.queue({})
    transport.queue({})
    client = build_client(transport)
    client.connect()

    request = ExchangeOrderRequest(
        symbol="ETH/USDT",
        side=ExchangeOrderSide.BUY,
        order_type=ExchangeOrderType.LIMIT,
        quantity=1,
        price=2000,
    )

    assert client.test_order(request) is True
    assert "/api/v3/order/test?" in transport.calls[-1]["url"]
    assert "timeInForce=GTC" in transport.calls[-1]["url"]


def test_get_symbol_order() -> None:
    transport = FakeTransport()
    transport.queue({})
    transport.queue(
        {
            "symbol": "BTCUSDT",
            "orderId": 99,
            "clientOrderId": "abc",
            "status": "NEW",
            "side": "BUY",
            "type": "LIMIT",
            "origQty": "1",
            "executedQty": "0",
            "price": "100",
        }
    )
    client = build_client(transport)
    client.connect()

    order = client.get_symbol_order(
        symbol="BTC/USDT",
        exchange_order_id="99",
    )

    assert order.exchange_order_id == "99"
    assert order.status == ExchangeOrderStatus.NEW
    assert "symbol=BTCUSDT" in transport.calls[-1]["url"]


def test_cancel_symbol_order() -> None:
    transport = FakeTransport()
    transport.queue({})
    transport.queue(
        {
            "symbol": "BTCUSDT",
            "orderId": 99,
            "clientOrderId": "abc",
            "status": "CANCELED",
            "side": "BUY",
            "type": "LIMIT",
            "origQty": "1",
            "executedQty": "0",
            "price": "100",
        }
    )
    client = build_client(transport)
    client.connect()

    order = client.cancel_symbol_order(
        symbol="BTC/USDT",
        exchange_order_id="99",
    )

    assert order.status == ExchangeOrderStatus.UNKNOWN
    assert transport.calls[-1]["method"] == "DELETE"


def test_connection_required_for_account() -> None:
    client = build_client()

    with pytest.raises(ExchangeConnectionError):
        client.get_balances()


def test_environment_credentials(monkeypatch) -> None:
    monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "env-key")
    monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "env-secret")

    credentials = BinanceCredentials.from_env()

    assert credentials.api_key == "env-key"
    assert credentials.api_secret == "env-secret"
