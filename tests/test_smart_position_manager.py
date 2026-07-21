from __future__ import annotations

import pytest

from engine.smart_position_manager import (
    ExitReason,
    PositionSide,
    PositionStatus,
    SmartPositionConfig,
    SmartPositionManager,
    SmartPositionRuntimeBridge,
)


def manager(**kwargs):
    return SmartPositionManager(SmartPositionConfig(**kwargs))


def test_config_validation_ratios() -> None:
    with pytest.raises(ValueError):
        SmartPositionConfig(
            target_1_close_ratio=0.5,
            target_2_close_ratio=0.5,
            target_3_close_ratio=0.5,
        ).validate()


def test_config_validation_targets() -> None:
    with pytest.raises(ValueError):
        SmartPositionConfig(
            risk_reward_target_1=2,
            risk_reward_target_2=1,
            risk_reward_target_3=3,
        ).validate()


def test_parse_long() -> None:
    assert SmartPositionManager.parse_side("BUY") == PositionSide.LONG


def test_parse_short() -> None:
    assert SmartPositionManager.parse_side("SELL") == PositionSide.SHORT


def test_invalid_side() -> None:
    with pytest.raises(ValueError):
        SmartPositionManager.parse_side("X")


def test_create_long_position() -> None:
    item = manager()
    pos = item.create_position(
        symbol="BTC/USDT",
        side="BUY",
        entry_price=100,
        quantity=10,
        atr=2,
    )
    assert pos.initial_stop == 96
    assert pos.target_1 == 104
    assert pos.target_2 == 108
    assert pos.target_3 == 112


def test_create_short_position() -> None:
    item = manager()
    pos = item.create_position(
        symbol="BTCUSDT",
        side="SELL",
        entry_price=100,
        quantity=10,
        atr=2,
    )
    assert pos.initial_stop == 104
    assert pos.target_1 == 96
    assert pos.target_2 == 92
    assert pos.target_3 == 88


def test_invalid_entry() -> None:
    with pytest.raises(ValueError):
        manager().create_position(
            symbol="BTCUSDT",
            side="BUY",
            entry_price=0,
            quantity=1,
            atr=1,
        )


def test_invalid_quantity() -> None:
    with pytest.raises(ValueError):
        manager().create_position(
            symbol="BTCUSDT",
            side="BUY",
            entry_price=100,
            quantity=0,
            atr=1,
        )


def test_invalid_atr() -> None:
    with pytest.raises(ValueError):
        manager().create_position(
            symbol="BTCUSDT",
            side="BUY",
            entry_price=100,
            quantity=1,
            atr=0,
        )


def test_long_stop_loss() -> None:
    item = manager()
    item.create_position(
        symbol="BTCUSDT",
        side="BUY",
        entry_price=100,
        quantity=10,
        atr=2,
    )
    result = item.update_position("BTCUSDT", 95)
    assert result.closed is True
    assert result.events[0].reason == ExitReason.STOP_LOSS


def test_short_stop_loss() -> None:
    item = manager()
    item.create_position(
        symbol="BTCUSDT",
        side="SELL",
        entry_price=100,
        quantity=10,
        atr=2,
    )
    result = item.update_position("BTCUSDT", 105)
    assert result.closed is True
    assert result.events[0].reason == ExitReason.STOP_LOSS


def test_break_even_long() -> None:
    item = manager()
    pos = item.create_position(
        symbol="BTCUSDT",
        side="BUY",
        entry_price=100,
        quantity=10,
        atr=2,
    )
    item.update_position("BTCUSDT", 104)
    assert pos.break_even_active is True
    assert pos.current_stop > 100


def test_break_even_short() -> None:
    item = manager()
    pos = item.create_position(
        symbol="BTCUSDT",
        side="SELL",
        entry_price=100,
        quantity=10,
        atr=2,
    )
    item.update_position("BTCUSDT", 96)
    assert pos.break_even_active is True
    assert pos.current_stop < 100


def test_trailing_long() -> None:
    item = manager()
    pos = item.create_position(
        symbol="BTCUSDT",
        side="BUY",
        entry_price=100,
        quantity=10,
        atr=2,
    )
    item.update_position("BTCUSDT", 106)
    assert pos.trailing_active is True
    assert pos.current_stop == pytest.approx(103)


def test_trailing_short() -> None:
    item = manager()
    pos = item.create_position(
        symbol="BTCUSDT",
        side="SELL",
        entry_price=100,
        quantity=10,
        atr=2,
    )
    item.update_position("BTCUSDT", 94)
    assert pos.trailing_active is True
    assert pos.current_stop == pytest.approx(97)


def test_target_1_partial_close() -> None:
    item = manager()
    pos = item.create_position(
        symbol="BTCUSDT",
        side="BUY",
        entry_price=100,
        quantity=10,
        atr=2,
    )
    result = item.update_position("BTCUSDT", 104)
    assert pos.target_1_hit is True
    assert pos.remaining_quantity == pytest.approx(6)
    assert result.events[0].reason == ExitReason.TAKE_PROFIT_1


def test_target_2_partial_close() -> None:
    item = manager()
    pos = item.create_position(
        symbol="BTCUSDT",
        side="BUY",
        entry_price=100,
        quantity=10,
        atr=2,
    )
    item.update_position("BTCUSDT", 108)
    assert pos.target_1_hit is True
    assert pos.target_2_hit is True
    assert pos.remaining_quantity == pytest.approx(3)


def test_target_3_closes_position() -> None:
    item = manager()
    pos = item.create_position(
        symbol="BTCUSDT",
        side="BUY",
        entry_price=100,
        quantity=10,
        atr=2,
    )
    result = item.update_position("BTCUSDT", 112)
    assert pos.status == PositionStatus.CLOSED
    assert result.closed is True
    assert item.get_position("BTCUSDT") is None


def test_short_targets() -> None:
    item = manager()
    pos = item.create_position(
        symbol="BTCUSDT",
        side="SELL",
        entry_price=100,
        quantity=10,
        atr=2,
    )
    item.update_position("BTCUSDT", 88)
    assert pos.status == PositionStatus.CLOSED
    assert pos.realized_pnl > 0


def test_trailing_stop_reason() -> None:
    item = manager()
    item.create_position(
        symbol="BTCUSDT",
        side="BUY",
        entry_price=100,
        quantity=10,
        atr=2,
    )
    item.update_position("BTCUSDT", 106)
    result = item.update_position("BTCUSDT", 102)
    assert result.events[0].reason == ExitReason.TRAILING_STOP


def test_manual_close_full() -> None:
    item = manager()
    pos = item.create_position(
        symbol="BTCUSDT",
        side="BUY",
        entry_price=100,
        quantity=10,
        atr=2,
    )
    event = item.manual_close("BTCUSDT", 105)
    assert event.reason == ExitReason.MANUAL
    assert pos.status == PositionStatus.CLOSED


def test_manual_close_partial() -> None:
    item = manager()
    pos = item.create_position(
        symbol="BTCUSDT",
        side="BUY",
        entry_price=100,
        quantity=10,
        atr=2,
    )
    item.manual_close("BTCUSDT", 105, quantity=2)
    assert pos.remaining_quantity == 8
    assert pos.status == PositionStatus.PARTIAL


def test_missing_position() -> None:
    with pytest.raises(KeyError):
        manager().update_position("BTCUSDT", 100)


def test_dashboard() -> None:
    item = manager()
    item.create_position(
        symbol="BTCUSDT",
        side="BUY",
        entry_price=100,
        quantity=10,
        atr=2,
    )
    data = item.dashboard()
    assert data["open_position_count"] == 1
    assert len(data["positions"]) == 1


def test_runtime_bridge_open() -> None:
    bridge = SmartPositionRuntimeBridge(manager())
    pos = bridge.open_from_execution(
        {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "price": 100,
            "quantity": 5,
        },
        {"atr": 2, "price": 100},
    )
    assert pos.initial_quantity == 5


def test_runtime_bridge_price() -> None:
    bridge = SmartPositionRuntimeBridge(manager())
    bridge.open_from_execution(
        {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "price": 100,
            "quantity": 5,
        },
        {"atr": 2, "price": 100},
    )
    result = bridge.on_price("BTCUSDT", 104)
    assert "events" in result


def test_runtime_bridge_dashboard() -> None:
    bridge = SmartPositionRuntimeBridge(manager())
    assert "positions" in bridge.dashboard()


def test_symbol_normalization() -> None:
    assert SmartPositionManager.normalize_symbol("btc-usdt") == "BTCUSDT"


def test_position_to_dict() -> None:
    pos = manager().create_position(
        symbol="BTCUSDT",
        side="BUY",
        entry_price=100,
        quantity=1,
        atr=2,
    )
    data = pos.to_dict()
    assert data["side"] == "LONG"
    assert data["risk_per_unit"] == 4


def test_event_history() -> None:
    item = manager()
    item.create_position(
        symbol="BTCUSDT",
        side="BUY",
        entry_price=100,
        quantity=10,
        atr=2,
    )
    item.update_position("BTCUSDT", 104)
    assert len(item.event_history) == 1


def test_realized_pnl_long() -> None:
    item = manager()
    pos = item.create_position(
        symbol="BTCUSDT",
        side="BUY",
        entry_price=100,
        quantity=10,
        atr=2,
    )
    item.update_position("BTCUSDT", 104)
    assert pos.realized_pnl == pytest.approx(16)


def test_realized_pnl_short() -> None:
    item = manager()
    pos = item.create_position(
        symbol="BTCUSDT",
        side="SELL",
        entry_price=100,
        quantity=10,
        atr=2,
    )
    item.update_position("BTCUSDT", 96)
    assert pos.realized_pnl == pytest.approx(16)
