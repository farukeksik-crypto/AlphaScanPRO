from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from engine.backtest_v2 import BacktestBar, BacktestConfig
from engine.strategy_optimizer import (
    OptimizationConfig,
    OptimizerWeights,
    StrategyOptimizer,
)


def make_bars(count=24):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    prices = [
        100 + i * 0.8 + (2 if i % 5 == 0 else 0)
        for i in range(count)
    ]
    return [
        BacktestBar(
            timestamp=start + timedelta(days=i),
            open=price,
            high=price * 1.01,
            low=price * 0.99,
            close=price,
            volume=1000,
        )
        for i, price in enumerate(prices)
    ]


def signal_factory(parameters):
    hold_period = int(parameters.get("hold_period", 3))

    def signal(index, bar, bars):
        cycle = hold_period + 1
        if index % cycle == 0:
            return "BUY"
        if index % cycle == hold_period:
            return "SELL"
        return "HOLD"

    return signal


def test_weight_normalization():
    normalized = OptimizerWeights().normalized()
    total = sum(abs(value) for value in (
        normalized.net_profit_pct,
        normalized.win_rate,
        normalized.profit_factor,
        normalized.sharpe_ratio,
        normalized.max_drawdown_pct,
    ))
    assert total == pytest.approx(1.0)


def test_zero_weights_rejected():
    with pytest.raises(ValueError):
        OptimizerWeights(
            net_profit_pct=0,
            win_rate=0,
            profit_factor=0,
            sharpe_ratio=0,
            max_drawdown_pct=0,
        ).normalized()


def test_config_validation():
    with pytest.raises(ValueError):
        OptimizationConfig(top_n=0)
    with pytest.raises(ValueError):
        OptimizationConfig(train_ratio=0.2)


def test_parameter_combinations():
    combinations = StrategyOptimizer.parameter_combinations({
        "hold_period": [2, 3],
        "stop_loss_pct": [0.02, 0.03],
    })
    assert len(combinations) == 4


def test_empty_grid_returns_single_combination():
    assert StrategyOptimizer.parameter_combinations({}) == [{}]


def test_empty_grid_value_rejected():
    with pytest.raises(ValueError):
        StrategyOptimizer.parameter_combinations({
            "hold_period": [],
        })


def test_score_result():
    optimizer = StrategyOptimizer()
    evaluation = optimizer.evaluate_parameters(
        bars=make_bars(),
        parameters={"hold_period": 3},
        signal_factory=signal_factory,
    )
    assert isinstance(evaluation.score, float)


def test_min_trade_rejection():
    optimizer = StrategyOptimizer(
        config=OptimizationConfig(min_trades=100)
    )
    evaluation = optimizer.evaluate_parameters(
        bars=make_bars(),
        parameters={"hold_period": 3},
        signal_factory=signal_factory,
    )
    assert evaluation.rejected is True


def test_backtest_config_parameter_override():
    optimizer = StrategyOptimizer(
        base_backtest_config=BacktestConfig(
            commission_pct=0,
            slippage_pct=0,
        )
    )
    evaluation = optimizer.evaluate_parameters(
        bars=make_bars(),
        parameters={
            "hold_period": 3,
            "stop_loss_pct": 0.02,
        },
        signal_factory=signal_factory,
    )
    assert evaluation.backtest.config.stop_loss_pct == 0.02


def test_optimize_selects_best():
    optimizer = StrategyOptimizer(
        base_backtest_config=BacktestConfig(
            commission_pct=0,
            slippage_pct=0,
            partial_take_profit_pct=0.50,
            take_profit_pct=0.50,
            trailing_stop_pct=0.50,
        )
    )
    report = optimizer.optimize(
        bars=make_bars(),
        parameter_grid={"hold_period": [1, 2, 3, 4]},
        signal_factory=signal_factory,
    )
    assert report.best is not None
    assert report.parameter_count == 4
    assert report.evaluations[0].score >= report.evaluations[-1].score


def test_top_n_limit():
    optimizer = StrategyOptimizer(
        config=OptimizationConfig(top_n=2)
    )
    report = optimizer.optimize(
        bars=make_bars(),
        parameter_grid={"hold_period": [1, 2, 3, 4]},
        signal_factory=signal_factory,
    )
    assert len(report.evaluations) == 2
    assert report.parameter_count == 4


def test_empty_bars_rejected():
    optimizer = StrategyOptimizer()
    with pytest.raises(ValueError):
        optimizer.optimize(
            bars=[],
            parameter_grid={"hold_period": [2]},
            signal_factory=signal_factory,
        )


def test_fold_windows():
    optimizer = StrategyOptimizer(
        config=OptimizationConfig(
            walk_forward_folds=3
        )
    )
    windows = optimizer._fold_windows(24)
    assert len(windows) == 3
    assert windows[0][0] == 0


def test_walk_forward():
    optimizer = StrategyOptimizer(
        base_backtest_config=BacktestConfig(
            commission_pct=0,
            slippage_pct=0,
            partial_take_profit_pct=0.50,
            take_profit_pct=0.50,
            trailing_stop_pct=0.50,
        ),
        config=OptimizationConfig(
            walk_forward_folds=3,
            min_trades=0,
        ),
    )
    result = optimizer.walk_forward(
        bars=make_bars(32),
        parameter_grid={"hold_period": [1, 2, 3]},
        signal_factory=signal_factory,
    )
    assert len(result.folds) >= 1
    assert 0 <= result.stability_score <= 1
    assert "hold_period" in result.robust_parameters


def test_optimize_with_walk_forward():
    optimizer = StrategyOptimizer(
        config=OptimizationConfig(
            walk_forward_folds=2,
            min_trades=0,
        )
    )
    report = optimizer.optimize_with_walk_forward(
        bars=make_bars(30),
        parameter_grid={"hold_period": [1, 2]},
        signal_factory=signal_factory,
    )
    assert report.best is not None
    assert report.walk_forward is not None


def test_parameter_consensus():
    optimizer = StrategyOptimizer()
    result = optimizer.walk_forward(
        bars=make_bars(28),
        parameter_grid={"hold_period": [1, 2]},
        signal_factory=signal_factory,
    )
    assert isinstance(result.robust_parameters, dict)


def test_dashboard():
    optimizer = StrategyOptimizer(
        config=OptimizationConfig(
            walk_forward_folds=2,
            min_trades=0,
        )
    )
    report = optimizer.optimize_with_walk_forward(
        bars=make_bars(30),
        parameter_grid={"hold_period": [1, 2]},
        signal_factory=signal_factory,
    )
    dashboard = optimizer.dashboard(report)
    assert "best_parameters" in dashboard
    assert "walk_forward_stability_score" in dashboard


def test_report_to_dict():
    optimizer = StrategyOptimizer()
    report = optimizer.optimize(
        bars=make_bars(),
        parameter_grid={"hold_period": [1, 2]},
        signal_factory=signal_factory,
    )
    data = report.to_dict()
    assert data["parameter_count"] == 2
    assert "evaluations" in data
