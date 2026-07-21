from __future__ import annotations

from datetime import datetime, timezone

import pytest

from engine.paper_broker import PaperOrderStatus, PaperOrderType
from engine.paper_trading_engine import (
    PaperTradingConfig,
    PaperTradingEngine,
)


def ts(hour: int) -> datetime:
    return datetime(2026, 7, 21, hour, tzinfo=timezone.utc)


def make_engine(**kwargs) -> PaperTradingEngine:
    config = PaperTradingConfig(
        starting_cash=10_000,
        commission_rate=0.001,
        slippage_rate=0.0,
        **kwargs,
    )
    return PaperTradingEngine(config)


def test_config_broker_config():
    config = PaperTradingConfig(starting_cash=5_000)
    assert config.broker_config().starting_cash == 5_000


def test_buy_signal_fills():
    engine = make_engine()
    result = engine.submit_signal(
        symbol="BTCUSDT",
        action="BUY",
        quantity=1,
        market_price=100,
        timestamp=ts(10),
    )
    assert result.success
    assert result.order.status == PaperOrderStatus.FILLED


def test_invalid_action():
    engine = make_engine()
    with pytest.raises(ValueError):
        engine.submit_signal(
            symbol="BTCUSDT",
            action="HOLD",
            quantity=1,
            market_price=100,
        )


def test_buy_updates_portfolio():
    engine = make_engine()
    engine.submit_signal(
        symbol="BTCUSDT",
        action="BUY",
        quantity=2,
        market_price=100,
        timestamp=ts(10),
    )
    position = engine.portfolio.get_position("BTCUSDT")
    assert position.quantity == 2


def test_buy_opens_trade_state():
    engine = make_engine()
    engine.submit_signal(
        symbol="BTCUSDT",
        action="BUY",
        quantity=1,
        market_price=100,
        reason="NET AL",
        strategy="alpha",
        timestamp=ts(10),
    )
    trade = engine.open_trades["BTCUSDT"]
    assert trade.side == "LONG"
    assert trade.entry_reason == "NET AL"


def test_second_buy_averages_open_trade():
    engine = make_engine()
    engine.submit_signal(
        symbol="BTCUSDT",
        action="BUY",
        quantity=1,
        market_price=100,
        timestamp=ts(10),
    )
    engine.submit_signal(
        symbol="BTCUSDT",
        action="BUY",
        quantity=1,
        market_price=120,
        timestamp=ts(11),
    )
    trade = engine.open_trades["BTCUSDT"]
    assert trade.quantity == 2
    assert trade.entry_price == pytest.approx(110)


def test_sell_closes_trade_and_journals():
    engine = make_engine()
    engine.submit_signal(
        symbol="BTCUSDT",
        action="BUY",
        quantity=1,
        market_price=100,
        reason="Giriş",
        timestamp=ts(10),
    )
    result = engine.submit_signal(
        symbol="BTCUSDT",
        action="SELL",
        quantity=1,
        market_price=120,
        reason="Hedef",
        timestamp=ts(12),
    )
    assert result.journal_trade is not None
    assert result.journal_trade.net_pnl == pytest.approx(19.78)
    assert len(engine.journal.trades()) == 1
    assert "BTCUSDT" not in engine.open_trades


def test_partial_sell_keeps_open_trade():
    engine = make_engine()
    engine.submit_signal(
        symbol="BTCUSDT",
        action="BUY",
        quantity=2,
        market_price=100,
        timestamp=ts(10),
    )
    engine.submit_signal(
        symbol="BTCUSDT",
        action="SELL",
        quantity=1,
        market_price=110,
        timestamp=ts(12),
    )
    assert engine.open_trades["BTCUSDT"].quantity == 1
    assert len(engine.journal.trades()) == 1


def test_limit_order_stays_open():
    engine = make_engine()
    result = engine.submit_signal(
        symbol="BTCUSDT",
        action="BUY",
        quantity=1,
        market_price=100,
        order_type=PaperOrderType.LIMIT,
        limit_price=90,
        timestamp=ts(10),
    )
    assert result.order.status == PaperOrderStatus.OPEN
    assert len(engine.broker.open_orders()) == 1


def test_process_open_limit_order():
    engine = make_engine()
    result = engine.submit_signal(
        symbol="BTCUSDT",
        action="BUY",
        quantity=1,
        market_price=100,
        order_type=PaperOrderType.LIMIT,
        limit_price=95,
        timestamp=ts(10),
    )
    result2 = engine.process_open_order(
        result.order.order_id,
        market_price=94,
        reason="Limit gerçekleşti",
        timestamp=ts(11),
    )
    assert result2.order.status == PaperOrderStatus.FILLED
    assert "BTCUSDT" in engine.open_trades


def test_partial_fill_flow():
    engine = make_engine()
    result = engine.submit_signal(
        symbol="BTCUSDT",
        action="BUY",
        quantity=2,
        market_price=100,
        available_liquidity=1,
        timestamp=ts(10),
    )
    assert result.order.status == PaperOrderStatus.PARTIALLY_FILLED
    assert engine.open_trades["BTCUSDT"].quantity == 1


def test_mark_to_market():
    engine = make_engine()
    engine.submit_signal(
        symbol="BTCUSDT",
        action="BUY",
        quantity=1,
        market_price=100,
        timestamp=ts(10),
    )
    snapshot = engine.mark_to_market(
        {"BTCUSDT": 120},
        timestamp=ts(11),
    )
    assert snapshot["equity"] == pytest.approx(10019.9)


def test_cancel_order():
    engine = make_engine()
    result = engine.submit_signal(
        symbol="BTCUSDT",
        action="BUY",
        quantity=1,
        market_price=100,
        order_type=PaperOrderType.LIMIT,
        limit_price=90,
    )
    order = engine.cancel_order(result.order.order_id)
    assert order.status == PaperOrderStatus.CANCELLED


def test_dashboard():
    engine = make_engine()
    engine.submit_signal(
        symbol="BTCUSDT",
        action="BUY",
        quantity=1,
        market_price=100,
        timestamp=ts(10),
    )
    data = engine.dashboard()
    assert "broker" in data
    assert "portfolio" in data
    assert "journal" in data
    assert "open_trades" in data


def test_short_open_when_enabled():
    engine = make_engine(allow_short_selling=True)
    result = engine.submit_signal(
        symbol="BTCUSDT",
        action="SELL",
        quantity=1,
        market_price=100,
        timestamp=ts(10),
    )
    assert result.success
    assert engine.open_trades["BTCUSDT"].side == "SHORT"


def test_short_close_journal():
    engine = make_engine(allow_short_selling=True)
    engine.submit_signal(
        symbol="BTCUSDT",
        action="SELL",
        quantity=1,
        market_price=100,
        timestamp=ts(10),
    )
    result = engine.submit_signal(
        symbol="BTCUSDT",
        action="BUY",
        quantity=1,
        market_price=80,
        timestamp=ts(12),
    )
    assert result.journal_trade is not None
    assert result.journal_trade.side == "SHORT"
    assert result.journal_trade.net_pnl == pytest.approx(19.82)


def test_result_to_dict():
    engine = make_engine()
    result = engine.submit_signal(
        symbol="BTCUSDT",
        action="BUY",
        quantity=1,
        market_price=100,
        timestamp=ts(10),
    )
    data = result.to_dict()
    assert data["success"] is True
    assert data["order"]["symbol"] == "BTCUSDT"


def test_duplicate_fill_protection():
    engine = make_engine()
    result = engine.submit_signal(
        symbol="BTCUSDT",
        action="BUY",
        quantity=1,
        market_price=100,
        timestamp=ts(10),
    )
    engine._process_fills(
        result.fills,
        reason="x",
        strategy="x",
        metadata={},
        timestamp=ts(11),
    )
    assert engine.portfolio.trade_count == 1
