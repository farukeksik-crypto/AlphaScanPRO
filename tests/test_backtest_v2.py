from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from engine.backtest_v2 import (
    BacktestBar,
    BacktestConfig,
    BacktestEngineV2,
    BacktestExitReason,
    BacktestSide,
)


def make_bars(prices):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars = []
    for i, price in enumerate(prices):
        bars.append(
            BacktestBar(
                timestamp=start + timedelta(days=i),
                open=price,
                high=price * 1.01,
                low=price * 0.99,
                close=price,
                volume=1000,
            )
        )
    return bars


def test_config_validation():
    with pytest.raises(ValueError):
        BacktestConfig(initial_capital=0)
    with pytest.raises(ValueError):
        BacktestConfig(partial_close_ratio=0)


def test_bar_validation():
    with pytest.raises(ValueError):
        BacktestBar(
            datetime.now(timezone.utc),
            100,
            99,
            98,
            100,
        )


def test_long_entry_and_end_close():
    bars = make_bars([100, 101, 102])
    engine = BacktestEngineV2(
        BacktestConfig(
            commission_pct=0,
            slippage_pct=0,
            force_close_at_end=True,
        )
    )

    result = engine.run(
        bars,
        lambda i, bar, all_bars: "BUY" if i == 0 else "HOLD",
    )

    assert result.total_trades == 1
    assert result.trades[0].exit_reason == BacktestExitReason.END_OF_DATA
    assert result.net_profit > 0


def test_signal_exit():
    bars = make_bars([100, 103, 104])
    engine = BacktestEngineV2(
        BacktestConfig(
            commission_pct=0,
            slippage_pct=0,
            partial_take_profit_pct=0.50,
        )
    )

    result = engine.run(
        bars,
        lambda i, bar, all_bars: (
            "BUY" if i == 0 else "SELL" if i == 1 else "HOLD"
        ),
    )

    assert result.trades[0].exit_reason == BacktestExitReason.SIGNAL


def test_stop_loss():
    bars = make_bars([100, 95])
    engine = BacktestEngineV2(
        BacktestConfig(
            commission_pct=0,
            slippage_pct=0,
            stop_loss_pct=0.03,
            partial_take_profit_pct=0.50,
        )
    )
    result = engine.run(
        bars,
        lambda i, bar, all_bars: "BUY" if i == 0 else "HOLD",
    )
    assert result.trades[0].exit_reason == BacktestExitReason.STOP_LOSS


def test_take_profit():
    bars = make_bars([100, 108])
    engine = BacktestEngineV2(
        BacktestConfig(
            commission_pct=0,
            slippage_pct=0,
            take_profit_pct=0.05,
            partial_take_profit_pct=0.50,
        )
    )
    result = engine.run(
        bars,
        lambda i, bar, all_bars: "BUY" if i == 0 else "HOLD",
    )
    assert result.trades[0].exit_reason == BacktestExitReason.TAKE_PROFIT


def test_partial_take_profit():
    bars = make_bars([100, 105, 106])
    engine = BacktestEngineV2(
        BacktestConfig(
            commission_pct=0,
            slippage_pct=0,
            partial_take_profit_pct=0.04,
            take_profit_pct=0.50,
            trailing_stop_pct=0.50,
        )
    )
    result = engine.run(
        bars,
        lambda i, bar, all_bars: "BUY" if i == 0 else "HOLD",
    )
    assert any(
        trade.exit_reason == BacktestExitReason.PARTIAL_TAKE_PROFIT
        for trade in result.trades
    )
    assert any(trade.partial for trade in result.trades)


def test_trailing_stop():
    bars = make_bars([100, 110, 106])
    engine = BacktestEngineV2(
        BacktestConfig(
            commission_pct=0,
            slippage_pct=0,
            take_profit_pct=0.50,
            partial_take_profit_pct=0.50,
            trailing_stop_pct=0.03,
        )
    )
    result = engine.run(
        bars,
        lambda i, bar, all_bars: "BUY" if i == 0 else "HOLD",
    )
    assert result.trades[0].exit_reason == BacktestExitReason.TRAILING_STOP


def test_short_trade():
    bars = make_bars([100, 95, 90])
    engine = BacktestEngineV2(
        BacktestConfig(
            commission_pct=0,
            slippage_pct=0,
            enable_short=True,
            partial_take_profit_pct=0.50,
        )
    )
    result = engine.run(
        bars,
        lambda i, bar, all_bars: "SELL" if i == 0 else "HOLD",
    )
    assert result.trades[0].side == BacktestSide.SHORT
    assert result.net_profit > 0


def test_short_disabled():
    bars = make_bars([100, 95])
    engine = BacktestEngineV2(
        BacktestConfig(enable_short=False)
    )
    result = engine.run(
        bars,
        lambda i, bar, all_bars: "SELL",
    )
    assert result.total_trades == 0


def test_commission_and_slippage():
    bars = make_bars([100, 100])
    engine = BacktestEngineV2(
        BacktestConfig(
            commission_pct=0.001,
            slippage_pct=0.001,
            partial_take_profit_pct=0.50,
        )
    )
    result = engine.run(
        bars,
        lambda i, bar, all_bars: "BUY" if i == 0 else "SELL",
    )
    assert result.total_commission > 0
    assert result.net_profit < 0


def test_position_size():
    bars = make_bars([100, 101])
    engine = BacktestEngineV2(
        BacktestConfig(
            initial_capital=10000,
            position_size_pct=0.20,
            commission_pct=0,
            slippage_pct=0,
        )
    )
    result = engine.run(
        bars,
        lambda i, bar, all_bars: "BUY" if i == 0 else "HOLD",
    )
    assert result.trades[0].quantity == pytest.approx(20)


def test_equity_curve():
    bars = make_bars([100, 101, 102, 103])
    engine = BacktestEngineV2()
    result = engine.run(
        bars,
        lambda i, bar, all_bars: "BUY" if i == 0 else "HOLD",
    )
    assert len(result.equity_curve) >= len(bars)


def test_metrics():
    bars = make_bars([100, 110, 100, 90])
    engine = BacktestEngineV2(
        BacktestConfig(
            commission_pct=0,
            slippage_pct=0,
            partial_take_profit_pct=0.50,
            take_profit_pct=0.50,
            trailing_stop_pct=0.50,
        )
    )
    result = engine.run(
        bars,
        lambda i, bar, all_bars: (
            "BUY" if i == 0 else "SELL" if i == 1 else "HOLD"
        ),
    )
    assert result.win_rate >= 0
    assert result.max_drawdown_pct >= 0
    assert isinstance(result.sharpe_ratio, float)


def test_empty_data():
    engine = BacktestEngineV2()
    with pytest.raises(ValueError):
        engine.run([], lambda i, bar, all_bars: "HOLD")


def test_result_to_dict():
    bars = make_bars([100, 101])
    result = BacktestEngineV2().run(
        bars,
        lambda i, bar, all_bars: "BUY" if i == 0 else "HOLD",
    )
    data = result.to_dict()
    assert "trades" in data
    assert "equity_curve" in data
    assert data["initial_capital"] > 0
