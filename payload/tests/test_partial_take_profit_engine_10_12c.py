import pytest
from engine.position_management import PositionManagementConfig, PositionManagementEngine, PositionSide, ExitReason


def _engine(**overrides):
    values = dict(
        enable_multi_stage_take_profit=True,
        take_profit_levels=(0.04, 0.07, 0.10),
        take_profit_ratios=(0.40, 0.35, 1.0),
        enable_break_even=False,
        enable_trailing_stop=False,
        enable_stop_loss=False,
        enable_take_profit=True,
    )
    values.update(overrides)
    return PositionManagementEngine(PositionManagementConfig(**values))


def test_tp1_sells_configured_initial_quantity_ratio():
    engine = _engine()
    pos = engine.open_position(symbol='BTCUSDT', side=PositionSide.LONG, quantity=10, entry_price=100)
    actions = engine.evaluate('BTCUSDT', price=104)
    assert len(actions) == 1
    assert actions[0].reason == ExitReason.PARTIAL_TAKE_PROFIT
    assert actions[0].quantity == pytest.approx(4)
    assert pos.remaining_quantity == pytest.approx(6)
    assert pos.partial_stage == 1


def test_tp2_sells_second_configured_initial_quantity_ratio():
    engine = _engine()
    pos = engine.open_position(symbol='BTCUSDT', side=PositionSide.LONG, quantity=10, entry_price=100)
    engine.evaluate('BTCUSDT', price=104)
    actions = engine.evaluate('BTCUSDT', price=107)
    assert actions[0].quantity == pytest.approx(3.5)
    assert pos.remaining_quantity == pytest.approx(2.5)
    assert pos.partial_stage == 2


def test_tp3_closes_all_remaining_quantity():
    engine = _engine()
    pos = engine.open_position(symbol='BTCUSDT', side=PositionSide.LONG, quantity=10, entry_price=100)
    engine.evaluate('BTCUSDT', price=104)
    engine.evaluate('BTCUSDT', price=107)
    actions = engine.evaluate('BTCUSDT', price=110)
    assert actions[0].reason == ExitReason.TAKE_PROFIT
    assert actions[0].quantity == pytest.approx(2.5)
    assert pos.closed is True
    assert pos.remaining_quantity == 0
    assert pos.partial_stage == 3


def test_only_one_tp_stage_executes_per_tick_even_on_gap():
    engine = _engine()
    pos = engine.open_position(symbol='BTCUSDT', side=PositionSide.LONG, quantity=10, entry_price=100)
    actions = engine.evaluate('BTCUSDT', price=112)
    assert len(actions) == 1
    assert pos.partial_stage == 1
    assert pos.remaining_quantity == pytest.approx(6)


def test_short_position_uses_same_staged_logic():
    engine = _engine()
    pos = engine.open_position(symbol='TEST', side=PositionSide.SHORT, quantity=10, entry_price=100)
    engine.evaluate('TEST', price=96)
    assert pos.remaining_quantity == pytest.approx(6)
    engine.evaluate('TEST', price=93)
    assert pos.remaining_quantity == pytest.approx(2.5)
    engine.evaluate('TEST', price=90)
    assert pos.closed is True


def test_invalid_stage_configuration_is_rejected():
    with pytest.raises(ValueError):
        PositionManagementConfig(take_profit_levels=(0.07, 0.04, 0.10))
    with pytest.raises(ValueError):
        PositionManagementConfig(take_profit_ratios=(0.60, 0.50, 1.0))
