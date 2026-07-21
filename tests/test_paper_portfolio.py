from __future__ import annotations

from datetime import datetime, timezone

import pytest

from engine.paper_broker import PaperFill, PaperOrderSide
from engine.paper_portfolio import PaperPortfolio


def fill(
    *,
    fill_id: str,
    symbol: str = "BTCUSDT",
    side: str = "BUY",
    quantity: float = 1.0,
    price: float = 100.0,
    commission: float = 0.0,
    day: int = 1,
) -> PaperFill:
    return PaperFill(
        fill_id=fill_id,
        order_id=f"order-{fill_id}",
        symbol=symbol,
        side=PaperOrderSide(side),
        quantity=quantity,
        price=price,
        commission=commission,
        created_at=datetime(2026, 7, day, 12, 0, tzinfo=timezone.utc),
    )


def test_negative_starting_cash():
    with pytest.raises(ValueError):
        PaperPortfolio(-1)


def test_initial_state():
    portfolio = PaperPortfolio(10_000)
    assert portfolio.cash == 10_000
    assert portfolio.equity == 10_000
    assert portfolio.trade_count == 0


def test_buy_creates_position():
    portfolio = PaperPortfolio(10_000)
    portfolio.apply_fill(fill(fill_id="1", quantity=2, price=100))
    position = portfolio.get_position("BTCUSDT")
    assert position is not None
    assert position.quantity == 2
    assert position.average_cost == 100
    assert portfolio.cash == 9800


def test_weighted_average_cost():
    portfolio = PaperPortfolio(10_000)
    portfolio.apply_fill(fill(fill_id="1", quantity=1, price=100))
    portfolio.apply_fill(fill(fill_id="2", quantity=3, price=200))
    position = portfolio.get_position("BTCUSDT")
    assert position.average_cost == pytest.approx(175)


def test_commission_reduces_cash():
    portfolio = PaperPortfolio(10_000)
    portfolio.apply_fill(fill(fill_id="1", commission=1))
    assert portfolio.cash == 9899


def test_duplicate_fill_ignored():
    portfolio = PaperPortfolio(10_000)
    item = fill(fill_id="1")
    portfolio.apply_fill(item)
    portfolio.apply_fill(item)
    assert portfolio.trade_count == 1
    assert portfolio.cash == 9900


def test_partial_sell_realized_profit():
    portfolio = PaperPortfolio(10_000)
    portfolio.apply_fill(fill(fill_id="1", quantity=2, price=100))
    portfolio.apply_fill(fill(fill_id="2", side="SELL", quantity=1, price=130))
    position = portfolio.get_position("BTCUSDT")
    assert position.quantity == 1
    assert position.realized_pnl == pytest.approx(30)
    assert portfolio.gross_realized_pnl == pytest.approx(30)


def test_full_sell_resets_cost():
    portfolio = PaperPortfolio(10_000)
    portfolio.apply_fill(fill(fill_id="1", quantity=1, price=100))
    portfolio.apply_fill(fill(fill_id="2", side="SELL", quantity=1, price=110))
    position = portfolio.get_position("BTCUSDT")
    assert position.quantity == 0
    assert position.average_cost == 0


def test_sell_more_opens_short():
    portfolio = PaperPortfolio(10_000)
    portfolio.apply_fill(fill(fill_id="1", quantity=1, price=100))
    portfolio.apply_fill(fill(fill_id="2", side="SELL", quantity=2, price=120))
    position = portfolio.get_position("BTCUSDT")
    assert position.quantity == -1
    assert position.average_cost == 120
    assert position.realized_pnl == pytest.approx(20)


def test_short_average_cost():
    portfolio = PaperPortfolio(10_000)
    portfolio.apply_fill(fill(fill_id="1", side="SELL", quantity=1, price=100))
    portfolio.apply_fill(fill(fill_id="2", side="SELL", quantity=3, price=200))
    position = portfolio.get_position("BTCUSDT")
    assert position.quantity == -4
    assert position.average_cost == pytest.approx(175)


def test_close_short_profit():
    portfolio = PaperPortfolio(10_000)
    portfolio.apply_fill(fill(fill_id="1", side="SELL", quantity=2, price=100))
    portfolio.apply_fill(fill(fill_id="2", side="BUY", quantity=1, price=80))
    position = portfolio.get_position("BTCUSDT")
    assert position.quantity == -1
    assert position.realized_pnl == pytest.approx(20)


def test_buy_more_than_short_opens_long():
    portfolio = PaperPortfolio(10_000)
    portfolio.apply_fill(fill(fill_id="1", side="SELL", quantity=1, price=100))
    portfolio.apply_fill(fill(fill_id="2", side="BUY", quantity=2, price=80))
    position = portfolio.get_position("BTCUSDT")
    assert position.quantity == 1
    assert position.average_cost == 80
    assert position.realized_pnl == pytest.approx(20)


def test_update_market_price():
    portfolio = PaperPortfolio(10_000)
    portfolio.apply_fill(fill(fill_id="1", quantity=2, price=100))
    portfolio.update_market_price("btcusdt", 120)
    position = portfolio.get_position("BTCUSDT")
    assert position.last_price == 120
    assert position.market_value == 240


def test_invalid_market_price():
    portfolio = PaperPortfolio(10_000)
    portfolio.apply_fill(fill(fill_id="1"))
    with pytest.raises(ValueError):
        portfolio.update_market_price("BTCUSDT", 0)


def test_unknown_market_price_symbol_ignored():
    portfolio = PaperPortfolio(10_000)
    portfolio.update_market_price("ETHUSDT", 100)
    assert portfolio.get_position("ETHUSDT") is None


def test_unrealized_profit_long():
    portfolio = PaperPortfolio(10_000)
    portfolio.apply_fill(fill(fill_id="1", quantity=2, price=100))
    portfolio.update_market_price("BTCUSDT", 120)
    assert portfolio.unrealized_pnl == pytest.approx(40)


def test_unrealized_profit_short():
    portfolio = PaperPortfolio(10_000)
    portfolio.apply_fill(fill(fill_id="1", side="SELL", quantity=2, price=100))
    portfolio.update_market_price("BTCUSDT", 80)
    assert portfolio.unrealized_pnl == pytest.approx(40)


def test_positions_value():
    portfolio = PaperPortfolio(10_000)
    portfolio.apply_fill(fill(fill_id="1", quantity=2, price=100))
    portfolio.update_market_price("BTCUSDT", 110)
    assert portfolio.positions_value == 220


def test_equity():
    portfolio = PaperPortfolio(10_000)
    portfolio.apply_fill(fill(fill_id="1", quantity=2, price=100))
    portfolio.update_market_price("BTCUSDT", 110)
    assert portfolio.equity == pytest.approx(10_020)


def test_total_return():
    portfolio = PaperPortfolio(10_000)
    portfolio.apply_fill(fill(fill_id="1", quantity=1, price=100))
    portfolio.update_market_price("BTCUSDT", 120)
    assert portfolio.total_return == pytest.approx(20)
    assert portfolio.total_return_pct == pytest.approx(0.2)


def test_zero_starting_cash_return_pct():
    portfolio = PaperPortfolio(0)
    assert portfolio.total_return_pct == 0


def test_net_realized_pnl_after_commission():
    portfolio = PaperPortfolio(10_000)
    portfolio.apply_fill(fill(fill_id="1", quantity=1, price=100, commission=1))
    portfolio.apply_fill(fill(fill_id="2", side="SELL", quantity=1, price=120, commission=2))
    assert portfolio.gross_realized_pnl == pytest.approx(20)
    assert portfolio.net_realized_pnl == pytest.approx(17)
    assert portfolio.total_commission == pytest.approx(3)


def test_record_equity():
    portfolio = PaperPortfolio(10_000)
    point = portfolio.record_equity(
        timestamp=datetime(2026, 7, 1, 10, tzinfo=timezone.utc)
    )
    assert point.equity == 10_000
    assert len(portfolio.equity_history()) == 1


def test_peak_equity():
    portfolio = PaperPortfolio(10_000)
    portfolio.apply_fill(fill(fill_id="1", quantity=1, price=100))
    portfolio.update_market_price("BTCUSDT", 150)
    portfolio.record_equity()
    assert portfolio.peak_equity == pytest.approx(10_050)


def test_current_drawdown():
    portfolio = PaperPortfolio(10_000)
    portfolio.apply_fill(fill(fill_id="1", quantity=1, price=100))
    portfolio.update_market_price("BTCUSDT", 150)
    portfolio.record_equity()
    portfolio.update_market_price("BTCUSDT", 50)
    assert portfolio.current_drawdown == pytest.approx(100 / 10_050)


def test_max_drawdown():
    portfolio = PaperPortfolio(10_000)
    portfolio.apply_fill(fill(fill_id="1", quantity=1, price=100))
    portfolio.update_market_price("BTCUSDT", 150)
    portfolio.record_equity()
    portfolio.update_market_price("BTCUSDT", 50)
    portfolio.record_equity()
    portfolio.update_market_price("BTCUSDT", 120)
    portfolio.record_equity()
    assert portfolio.max_drawdown == pytest.approx(100 / 10_050)


def test_apply_fills():
    portfolio = PaperPortfolio(10_000)
    portfolio.apply_fills([
        fill(fill_id="1", symbol="BTCUSDT"),
        fill(fill_id="2", symbol="ETHUSDT"),
    ])
    assert portfolio.trade_count == 2
    assert len(portfolio.positions) == 2


def test_update_market_prices():
    portfolio = PaperPortfolio(10_000)
    portfolio.apply_fills([
        fill(fill_id="1", symbol="BTCUSDT"),
        fill(fill_id="2", symbol="ETHUSDT"),
    ])
    portfolio.update_market_prices({"BTCUSDT": 120, "ETHUSDT": 130})
    assert portfolio.get_position("BTCUSDT").last_price == 120
    assert portfolio.get_position("ETHUSDT").last_price == 130


def test_active_positions():
    portfolio = PaperPortfolio(10_000)
    portfolio.apply_fill(fill(fill_id="1"))
    assert len(portfolio.active_positions()) == 1
    portfolio.apply_fill(fill(fill_id="2", side="SELL"))
    assert len(portfolio.active_positions()) == 0


def test_daily_performance_created():
    portfolio = PaperPortfolio(10_000)
    portfolio.apply_fill(fill(fill_id="1", day=1))
    records = portfolio.daily_performance()
    assert len(records) == 1
    assert records[0].trade_count == 1


def test_daily_performance_multiple_days():
    portfolio = PaperPortfolio(10_000)
    portfolio.apply_fill(fill(fill_id="1", day=1))
    portfolio.apply_fill(fill(fill_id="2", day=2))
    assert len(portfolio.daily_performance()) == 2


def test_snapshot():
    portfolio = PaperPortfolio(10_000)
    portfolio.apply_fill(fill(fill_id="1"))
    portfolio.update_market_price("BTCUSDT", 120)
    data = portfolio.snapshot()
    assert data["equity"] == pytest.approx(10_020)
    assert data["active_position_count"] == 1
    assert "BTCUSDT" in data["positions"]


def test_position_to_dict():
    portfolio = PaperPortfolio(10_000)
    position = portfolio.apply_fill(fill(fill_id="1"))
    portfolio.update_market_price("BTCUSDT", 120)
    data = position.to_dict()
    assert data["market_value"] == 120
    assert data["unrealized_pnl"] == 20


def test_equity_point_to_dict():
    portfolio = PaperPortfolio(10_000)
    point = portfolio.record_equity()
    data = point.to_dict()
    assert data["equity"] == 10_000
    assert "timestamp" in data


def test_daily_performance_to_dict():
    portfolio = PaperPortfolio(10_000)
    portfolio.apply_fill(fill(fill_id="1"))
    data = portfolio.daily_performance()[0].to_dict()
    assert data["trade_count"] == 1
    assert "return_pct" in data
