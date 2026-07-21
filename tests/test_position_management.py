from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from engine.position_management import (
    ExitReason,
    PositionManagementConfig,
    PositionManagementEngine,
    PositionSide,
)


def dt():
    return datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)


def test_config_validation():
    with pytest.raises(ValueError):
        PositionManagementConfig(stop_loss_pct=-1)
    with pytest.raises(ValueError):
        PositionManagementConfig(partial_close_ratio=0)


def test_open_long_position():
    engine = PositionManagementEngine()
    position = engine.open_position(
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        quantity=2,
        entry_price=100,
        opened_at=dt(),
    )
    assert position.stop_price == pytest.approx(97)
    assert position.take_profit_price == pytest.approx(106)


def test_open_short_position():
    engine = PositionManagementEngine()
    position = engine.open_position(
        symbol="BTCUSDT",
        side=PositionSide.SHORT,
        quantity=2,
        entry_price=100,
        opened_at=dt(),
    )
    assert position.stop_price == pytest.approx(103)
    assert position.take_profit_price == pytest.approx(94)


def test_duplicate_open_position():
    engine = PositionManagementEngine()
    engine.open_position(
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        quantity=1,
        entry_price=100,
    )
    with pytest.raises(ValueError):
        engine.open_position(
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            quantity=1,
            entry_price=100,
        )


def test_long_stop_loss():
    engine = PositionManagementEngine(
        PositionManagementConfig(enable_partial_take_profit=False)
    )
    engine.open_position(
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        quantity=1,
        entry_price=100,
    )
    actions = engine.evaluate("BTCUSDT", price=96)
    assert actions[0].reason == ExitReason.STOP_LOSS
    assert engine.get_position("BTCUSDT").closed


def test_short_stop_loss():
    engine = PositionManagementEngine(
        PositionManagementConfig(enable_partial_take_profit=False)
    )
    engine.open_position(
        symbol="BTCUSDT",
        side=PositionSide.SHORT,
        quantity=1,
        entry_price=100,
    )
    actions = engine.evaluate("BTCUSDT", price=104)
    assert actions[0].reason == ExitReason.STOP_LOSS


def test_long_take_profit():
    engine = PositionManagementEngine(
        PositionManagementConfig(enable_partial_take_profit=False)
    )
    engine.open_position(
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        quantity=1,
        entry_price=100,
    )
    actions = engine.evaluate("BTCUSDT", price=107)
    assert actions[0].reason == ExitReason.TAKE_PROFIT


def test_short_take_profit():
    engine = PositionManagementEngine(
        PositionManagementConfig(enable_partial_take_profit=False)
    )
    engine.open_position(
        symbol="BTCUSDT",
        side=PositionSide.SHORT,
        quantity=1,
        entry_price=100,
    )
    actions = engine.evaluate("BTCUSDT", price=93)
    assert actions[0].reason == ExitReason.TAKE_PROFIT


def test_partial_take_profit():
    engine = PositionManagementEngine()
    position = engine.open_position(
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        quantity=2,
        entry_price=100,
    )
    actions = engine.evaluate("BTCUSDT", price=104.5)
    assert actions[0].reason == ExitReason.PARTIAL_TAKE_PROFIT
    assert position.remaining_quantity == pytest.approx(1)
    assert position.partial_taken is True


def test_partial_only_once():
    engine = PositionManagementEngine()
    engine.open_position(
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        quantity=2,
        entry_price=100,
    )
    engine.evaluate("BTCUSDT", price=104.5)
    actions = engine.evaluate("BTCUSDT", price=105)
    assert all(action.reason != ExitReason.PARTIAL_TAKE_PROFIT for action in actions)


def test_break_even_activation():
    engine = PositionManagementEngine()
    position = engine.open_position(
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        quantity=1,
        entry_price=100,
    )
    engine.evaluate("BTCUSDT", price=103.5)
    assert position.break_even_active is True
    assert position.stop_price >= 100


def test_break_even_exit():
    engine = PositionManagementEngine(
        PositionManagementConfig(enable_partial_take_profit=False)
    )
    engine.open_position(
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        quantity=1,
        entry_price=100,
    )
    engine.evaluate("BTCUSDT", price=104)
    actions = engine.evaluate("BTCUSDT", price=100.1)
    assert actions[0].reason == ExitReason.BREAK_EVEN


def test_long_trailing_stop():
    engine = PositionManagementEngine(
        PositionManagementConfig(
            take_profit_pct=0.50,
            enable_partial_take_profit=False,
        )
    )
    engine.open_position(
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        quantity=1,
        entry_price=100,
    )
    engine.evaluate("BTCUSDT", price=110)
    actions = engine.evaluate("BTCUSDT", price=107)
    assert actions[0].reason == ExitReason.TRAILING_STOP


def test_short_trailing_stop():
    engine = PositionManagementEngine(
        PositionManagementConfig(
            take_profit_pct=0.50,
            enable_partial_take_profit=False,
        )
    )
    engine.open_position(
        symbol="BTCUSDT",
        side=PositionSide.SHORT,
        quantity=1,
        entry_price=100,
    )
    engine.evaluate("BTCUSDT", price=90)
    actions = engine.evaluate("BTCUSDT", price=93)
    assert actions[0].reason == ExitReason.TRAILING_STOP


def test_daily_loss_limit():
    engine = PositionManagementEngine(
        PositionManagementConfig(daily_loss_limit_pct=0.04)
    )
    engine.start_trading_day(
        trading_date=date(2026, 7, 21),
        starting_equity=10000,
    )
    engine.register_external_pnl(-500)
    assert engine.daily_risk.blocked is True
    assert engine.can_open_new_position() is False


def test_daily_loss_closes_open_position():
    engine = PositionManagementEngine(
        PositionManagementConfig(daily_loss_limit_pct=0.04)
    )
    engine.start_trading_day(
        trading_date=date(2026, 7, 21),
        starting_equity=10000,
    )
    engine.open_position(
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        quantity=1,
        entry_price=100,
    )
    engine.register_external_pnl(-500)
    actions = engine.evaluate("BTCUSDT", price=99)
    assert actions[0].reason == ExitReason.DAILY_LOSS_LIMIT


def test_manual_close():
    engine = PositionManagementEngine()
    engine.open_position(
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        quantity=1,
        entry_price=100,
    )
    action = engine.manual_close("BTCUSDT", price=105)
    assert action.reason == ExitReason.MANUAL
    assert action.pnl == pytest.approx(5)


def test_unrealized_pnl_long():
    engine = PositionManagementEngine()
    position = engine.open_position(
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        quantity=2,
        entry_price=100,
    )
    assert position.unrealized_pnl(110) == pytest.approx(20)


def test_unrealized_pnl_short():
    engine = PositionManagementEngine()
    position = engine.open_position(
        symbol="BTCUSDT",
        side=PositionSide.SHORT,
        quantity=2,
        entry_price=100,
    )
    assert position.unrealized_pnl(90) == pytest.approx(20)


def test_open_positions():
    engine = PositionManagementEngine()
    engine.open_position(
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        quantity=1,
        entry_price=100,
    )
    engine.open_position(
        symbol="ETHUSDT",
        side=PositionSide.LONG,
        quantity=1,
        entry_price=200,
    )
    engine.manual_close("ETHUSDT", price=210)
    assert [p.symbol for p in engine.open_positions()] == ["BTCUSDT"]


def test_dashboard():
    engine = PositionManagementEngine()
    engine.start_trading_day(
        trading_date=date(2026, 7, 21),
        starting_equity=10000,
    )
    engine.open_position(
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        quantity=1,
        entry_price=100,
    )
    data = engine.dashboard()
    assert "config" in data
    assert "daily_risk" in data
    assert "positions" in data
    assert data["open_position_count"] == 1
