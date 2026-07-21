from __future__ import annotations

from engine.position_management import (
    PositionManagementConfig,
    PositionManagementEngine,
    PositionSide,
)
import pytest

from engine.robot_engine import RobotConfig


def test_break_even_covers_round_trip_costs() -> None:
    cfg = PositionManagementConfig(
        enable_partial_take_profit=False,
        enable_trailing_stop=False,
        commission_rate=0.001,
        slippage_rate=0.0005,
        break_even_extra_buffer_pct=0.0002,
        break_even_offset_pct=0.0,
    )
    engine = PositionManagementEngine(cfg)
    position = engine.open_position(
        symbol="BTCUSDT", side=PositionSide.LONG, quantity=1, entry_price=100
    )
    engine.evaluate("BTCUSDT", price=103.1)
    assert position.break_even_active is True
    assert position.stop_price == pytest.approx(100.32)
    assert position.metadata["break_even"]["cost_buffer_pct"] == 0.0032


def test_break_even_stop_never_moves_backwards() -> None:
    cfg = PositionManagementConfig(
        enable_partial_take_profit=False,
        enable_trailing_stop=False,
        break_even_offset_pct=0.002,
    )
    engine = PositionManagementEngine(cfg)
    position = engine.open_position(
        symbol="ETHUSDT", side=PositionSide.LONG, quantity=1, entry_price=100
    )
    position.stop_price = 101.0
    engine.evaluate("ETHUSDT", price=104.0)
    assert position.stop_price == 101.0


def test_break_even_is_activated_only_once() -> None:
    engine = PositionManagementEngine(
        PositionManagementConfig(enable_partial_take_profit=False, enable_trailing_stop=False)
    )
    position = engine.open_position(
        symbol="SOLUSDT", side=PositionSide.LONG, quantity=1, entry_price=100
    )
    engine.evaluate("SOLUSDT", price=104.0)
    first = dict(position.metadata["break_even"])
    engine.evaluate("SOLUSDT", price=105.0)
    assert position.metadata["break_even"] == first


def test_robot_config_has_cost_aware_break_even_defaults() -> None:
    cfg = RobotConfig()
    effective = max(
        cfg.break_even_buffer_pct,
        2 * cfg.commission_rate + 2 * cfg.slippage_rate + cfg.break_even_extra_buffer_pct,
    )
    assert cfg.break_even_include_costs is True
    assert effective >= 0.0032
