from datetime import datetime, timezone

import pytest

from engine.position_management import (
    PositionManagementConfig,
    PositionManagementEngine,
    PositionSide,
)


def _engine(**overrides):
    values = {
        "enable_break_even": True,
        "break_even_trigger_pct": 0.02,
        "break_even_offset_pct": 0.0,
        "break_even_include_costs": False,
        "enable_trailing_stop": True,
        "atr_trailing_enabled": True,
        "atr_trailing_multiplier": 2.0,
        "atr_trailing_min_pct": 0.005,
        "atr_trailing_max_pct": 0.03,
        "trailing_requires_break_even": True,
        "enable_partial_take_profit": False,
        "enable_take_profit": False,
    }
    values.update(overrides)
    return PositionManagementEngine(PositionManagementConfig(**values))


def test_atr_trailing_waits_for_break_even():
    engine = _engine()
    position = engine.open_position(
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        quantity=1,
        entry_price=100,
        opened_at=datetime.now(timezone.utc),
    )

    engine.evaluate("BTCUSDT", price=101, atr=2)

    assert position.break_even_active is False
    assert position.trailing_stop_price is None


def test_atr_trailing_uses_clamped_atr_distance():
    engine = _engine()
    position = engine.open_position(
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        quantity=1,
        entry_price=100,
    )

    engine.evaluate("BTCUSDT", price=104, atr=10)

    # ATR*2=20, fakat üst sınır %3 => 3.12 mesafe.
    assert position.break_even_active is True
    assert position.trailing_stop_price == pytest.approx(104 - (104 * 0.03))
    assert position.metadata["atr_trailing"]["mode"] == "ATR"


def test_long_atr_trailing_never_moves_backwards():
    engine = _engine()
    position = engine.open_position(
        symbol="ETHUSDT",
        side=PositionSide.LONG,
        quantity=1,
        entry_price=100,
    )

    engine.evaluate("ETHUSDT", price=105, atr=1)
    first_stop = position.trailing_stop_price
    engine.evaluate("ETHUSDT", price=103, atr=3)

    assert position.trailing_stop_price == first_stop


def test_short_atr_trailing_never_moves_backwards():
    engine = _engine()
    position = engine.open_position(
        symbol="TEST",
        side=PositionSide.SHORT,
        quantity=1,
        entry_price=100,
    )

    engine.evaluate("TEST", price=96, atr=1)
    first_stop = position.trailing_stop_price
    engine.evaluate("TEST", price=98, atr=3)

    assert position.trailing_stop_price == first_stop


def test_invalid_atr_bounds_are_rejected():
    with pytest.raises(ValueError):
        PositionManagementConfig(
            atr_trailing_min_pct=0.05,
            atr_trailing_max_pct=0.01,
        )
