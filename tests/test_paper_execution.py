from __future__ import annotations

import pytest

from engine.paper_execution import (
    OrderSide,
    OrderStatus,
    OrderType,
    PaperBrokerConfig,
    PaperExecutionEngine,
)


def build_engine(
    *,
    starting_cash: float = 100_000,
    commission_rate: float = 0.001,
    slippage_rate: float = 0.0,
    allow_partial_fills: bool = True,
) -> PaperExecutionEngine:
    return PaperExecutionEngine(
        PaperBrokerConfig(
            starting_cash=starting_cash,
            commission_rate=commission_rate,
            slippage_rate=slippage_rate,
            allow_partial_fills=allow_partial_fills,
            default_liquidity_fraction=1.0,
        )
    )


def test_market_buy_fill_updates_cash_and_position() -> None:
    engine = build_engine()
    order = engine.submit_order(
        symbol="BTC/USDT",
        side="BUY",
        order_type="MARKET",
        quantity=10,
    )

    engine.process_order(order.order_id, market_price=100)

    assert order.status == OrderStatus.FILLED
    assert engine.positions["BTC/USDT"].quantity == 10
    assert engine.positions["BTC/USDT"].average_price == 100
    assert engine.cash == pytest.approx(98_999)


def test_limit_order_waits_then_fills() -> None:
    engine = build_engine()
    order = engine.submit_order(
        symbol="ETH/USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=5,
        limit_price=90,
    )

    engine.process_order(order.order_id, market_price=100)
    assert order.status == OrderStatus.NEW

    engine.process_order(order.order_id, market_price=89)
    assert order.status == OrderStatus.FILLED


def test_partial_fill() -> None:
    engine = build_engine()
    order = engine.submit_order(
        symbol="SOL/USDT",
        side="BUY",
        order_type="MARKET",
        quantity=10,
    )

    engine.process_order(
        order.order_id,
        market_price=50,
        available_liquidity=4,
    )

    assert order.status == OrderStatus.PARTIALLY_FILLED
    assert order.filled_quantity == 4
    assert order.remaining_quantity == 6


def test_sell_realized_pnl() -> None:
    engine = build_engine(commission_rate=0.0)
    buy = engine.submit_order(
        symbol="BTC/USDT",
        side="BUY",
        order_type="MARKET",
        quantity=2,
    )
    engine.process_order(buy.order_id, market_price=100)

    sell = engine.submit_order(
        symbol="BTC/USDT",
        side="SELL",
        order_type="MARKET",
        quantity=2,
    )
    engine.process_order(sell.order_id, market_price=110)

    position = engine.positions["BTC/USDT"]
    assert position.quantity == 0
    assert position.realized_pnl == 20


def test_slippage_applied() -> None:
    engine = build_engine(slippage_rate=0.01, commission_rate=0.0)
    order = engine.submit_order(
        symbol="BTC/USDT",
        side="BUY",
        order_type="MARKET",
        quantity=1,
    )

    engine.process_order(order.order_id, market_price=100)

    assert order.average_fill_price == pytest.approx(101)


def test_insufficient_cash_rejects_when_partial_disabled() -> None:
    engine = build_engine(
        starting_cash=100,
        allow_partial_fills=False,
    )
    order = engine.submit_order(
        symbol="BTC/USDT",
        side="BUY",
        order_type="MARKET",
        quantity=2,
    )

    engine.process_order(order.order_id, market_price=100)

    assert order.status == OrderStatus.REJECTED
    assert "Yetersiz" in order.reject_reason


def test_stop_loss_auto_exit() -> None:
    engine = build_engine(commission_rate=0.0)
    buy = engine.submit_order(
        symbol="BTC/USDT",
        side="BUY",
        order_type="MARKET",
        quantity=2,
        stop_loss=95,
    )
    engine.process_order(buy.order_id, market_price=100)

    processed = engine.process_price_update(
        symbol="BTC/USDT",
        market_price=94,
    )

    assert any(order.side == OrderSide.SELL for order in processed)
    assert engine.positions["BTC/USDT"].quantity == 0


def test_take_profit_auto_exit() -> None:
    engine = build_engine(commission_rate=0.0)
    buy = engine.submit_order(
        symbol="ETH/USDT",
        side="BUY",
        order_type="MARKET",
        quantity=3,
        take_profit=110,
    )
    engine.process_order(buy.order_id, market_price=100)

    engine.process_price_update(
        symbol="ETH/USDT",
        market_price=111,
    )

    assert engine.positions["ETH/USDT"].quantity == 0
    assert engine.positions["ETH/USDT"].realized_pnl == 33


def test_cancel_order() -> None:
    engine = build_engine()
    order = engine.submit_order(
        symbol="SOL/USDT",
        side="BUY",
        order_type="LIMIT",
        quantity=5,
        limit_price=20,
    )

    engine.cancel_order(order.order_id)

    assert order.status == OrderStatus.CANCELLED


def test_account_report() -> None:
    engine = build_engine(commission_rate=0.0)
    order = engine.submit_order(
        symbol="BTC/USDT",
        side="BUY",
        order_type="MARKET",
        quantity=1,
    )
    engine.process_order(order.order_id, market_price=100)
    engine.process_price_update(
        symbol="BTC/USDT",
        market_price=110,
    )

    report = engine.account_report()

    assert report["cash"] == 99_900
    assert report["market_value"] == 110
    assert report["equity"] == 100_010
    assert report["unrealized_pnl"] == 10
    assert len(report["orders"]) == 1
    assert len(report["fills"]) == 1
