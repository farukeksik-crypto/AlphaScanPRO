from __future__ import annotations

import math

import pytest

from engine.live_market_data import (
    KlineUpdate,
    MarketDataEvent,
    MarketDataEventType,
    TradeTick,
)
from engine.paper_trading_robot import (
    PaperOrderSide,
    PaperOrderStatus,
    PaperPortfolio,
    PaperTradingConfig,
    PaperTradingExecutionAdapter,
    PaperTradingRobotBridge,
)
from engine.robot_runtime import RuntimeAction, StrategyDecision


class FakeMarket:
    def __init__(self):
        self.callbacks = []

    def add_callback(self, callback):
        self.callbacks.append(callback)


class FakeRuntime:
    def __init__(self):
        self.execution = None
        self.market_data_engine = FakeMarket()


def decision(
    action=RuntimeAction.BUY,
    *,
    symbol="BTCUSDT",
    price=100.0,
    quantity=None,
    metadata=None,
):
    return StrategyDecision(
        symbol=symbol,
        action=action,
        score=80,
        reason="Test",
        quantity=quantity,
        price=price,
        metadata=metadata or {},
    )


def test_config_validation() -> None:
    with pytest.raises(ValueError):
        PaperTradingConfig(starting_cash=0).validate()


def test_initial_snapshot() -> None:
    portfolio = PaperPortfolio(PaperTradingConfig(starting_cash=1_000))
    snapshot = portfolio.snapshot()
    assert snapshot.cash == 1_000
    assert snapshot.equity == 1_000
    assert snapshot.open_positions == 0


def test_buy_creates_position() -> None:
    portfolio = PaperPortfolio(
        PaperTradingConfig(
            starting_cash=10_000,
            commission_rate=0,
            slippage_rate=0,
            default_order_value=1_000,
        )
    )
    trade = portfolio.buy(symbol="BTCUSDT", price=100)
    assert trade.status == PaperOrderStatus.FILLED
    assert portfolio.positions["BTCUSDT"].quantity == 10
    assert portfolio.cash == 9_000


def test_buy_applies_commission_and_slippage() -> None:
    portfolio = PaperPortfolio(
        PaperTradingConfig(
            starting_cash=10_000,
            commission_rate=0.01,
            slippage_rate=0.01,
            default_order_value=1_000,
        )
    )
    trade = portfolio.buy(symbol="BTCUSDT", price=100)
    assert trade.fill_price == 101
    assert trade.commission > 0
    assert portfolio.cash < 9_000


def test_duplicate_buy_rejected() -> None:
    portfolio = PaperPortfolio(
        PaperTradingConfig(
            starting_cash=10_000,
            commission_rate=0,
            slippage_rate=0,
            default_order_value=1_000,
            allow_pyramiding=False,
        )
    )
    portfolio.buy(symbol="BTCUSDT", price=100)
    second = portfolio.buy(symbol="BTCUSDT", price=101)
    assert second.status == PaperOrderStatus.REJECTED


def test_pyramiding_updates_average() -> None:
    portfolio = PaperPortfolio(
        PaperTradingConfig(
            starting_cash=10_000,
            commission_rate=0,
            slippage_rate=0,
            default_order_value=1_000,
            allow_pyramiding=True,
            max_position_pct=1,
        )
    )
    portfolio.buy(symbol="BTCUSDT", price=100)
    portfolio.buy(symbol="BTCUSDT", price=200)
    position = portfolio.positions["BTCUSDT"]
    assert position.quantity == 15
    assert math.isclose(position.average_price, 2000 / 15)


def test_max_position_limit() -> None:
    portfolio = PaperPortfolio(
        PaperTradingConfig(
            starting_cash=10_000,
            commission_rate=0,
            slippage_rate=0,
            default_order_value=9_000,
            max_position_pct=0.25,
        )
    )
    portfolio.buy(symbol="BTCUSDT", price=100)
    assert math.isclose(
        portfolio.positions["BTCUSDT"].invested_value,
        2_500,
    )


def test_sell_closes_position() -> None:
    portfolio = PaperPortfolio(
        PaperTradingConfig(
            starting_cash=10_000,
            commission_rate=0,
            slippage_rate=0,
            default_order_value=1_000,
        )
    )
    portfolio.buy(symbol="BTCUSDT", price=100)
    trade = portfolio.sell(symbol="BTCUSDT", price=110)
    assert trade.side == PaperOrderSide.SELL
    assert trade.realized_pnl == 100
    assert "BTCUSDT" not in portfolio.positions
    assert portfolio.cash == 10_100


def test_sell_without_position_rejected() -> None:
    portfolio = PaperPortfolio()
    trade = portfolio.sell(symbol="BTCUSDT", price=100)
    assert trade.status == PaperOrderStatus.REJECTED


def test_partial_sell() -> None:
    portfolio = PaperPortfolio(
        PaperTradingConfig(
            starting_cash=10_000,
            commission_rate=0,
            slippage_rate=0,
            default_order_value=1_000,
            allow_partial_sell=True,
        )
    )
    portfolio.buy(symbol="BTCUSDT", price=100)
    portfolio.sell(symbol="BTCUSDT", price=120, quantity=5)
    assert portfolio.positions["BTCUSDT"].quantity == 5
    assert portfolio.realized_pnl == 100


def test_partial_sell_disabled() -> None:
    portfolio = PaperPortfolio(
        PaperTradingConfig(
            starting_cash=10_000,
            commission_rate=0,
            slippage_rate=0,
            default_order_value=1_000,
            allow_partial_sell=False,
        )
    )
    portfolio.buy(symbol="BTCUSDT", price=100)
    portfolio.sell(symbol="BTCUSDT", price=120, quantity=5)
    assert "BTCUSDT" not in portfolio.positions


def test_unrealized_pnl() -> None:
    portfolio = PaperPortfolio(
        PaperTradingConfig(
            starting_cash=10_000,
            commission_rate=0,
            slippage_rate=0,
            default_order_value=1_000,
        )
    )
    portfolio.buy(symbol="BTCUSDT", price=100)
    portfolio.update_price("BTCUSDT", 120)
    snapshot = portfolio.snapshot()
    assert snapshot.unrealized_pnl == 200
    assert snapshot.equity == 10_200


def test_execute_buy_decision() -> None:
    portfolio = PaperPortfolio(
        PaperTradingConfig(
            starting_cash=10_000,
            commission_rate=0,
            slippage_rate=0,
            default_order_value=1_000,
        )
    )
    result = portfolio.execute_decision(decision())
    assert result["status"] == "FILLED"


def test_execute_sell_decision() -> None:
    portfolio = PaperPortfolio(
        PaperTradingConfig(
            starting_cash=10_000,
            commission_rate=0,
            slippage_rate=0,
            default_order_value=1_000,
        )
    )
    portfolio.execute_decision(decision())
    result = portfolio.execute_decision(
        decision(RuntimeAction.SELL, price=110)
    )
    assert result["side"] == "SELL"


def test_hold_decision_skipped() -> None:
    portfolio = PaperPortfolio()
    result = portfolio.execute_decision(
        decision(RuntimeAction.HOLD)
    )
    assert result["status"] == "SKIPPED"


def test_price_from_context_kline() -> None:
    portfolio = PaperPortfolio(
        PaperTradingConfig(
            starting_cash=10_000,
            commission_rate=0,
            slippage_rate=0,
            default_order_value=1_000,
        )
    )
    d = decision(price=100)
    d.price = None
    result = portfolio.execute_decision(
        d,
        {"kline": {"close": 105}},
    )
    assert result["requested_price"] == 105


def test_price_from_market_snapshot() -> None:
    portfolio = PaperPortfolio(
        PaperTradingConfig(
            starting_cash=10_000,
            commission_rate=0,
            slippage_rate=0,
            default_order_value=1_000,
        )
    )
    d = decision(price=100)
    d.price = None
    result = portfolio.execute_decision(
        d,
        {"market_snapshot": {"last_prices": {"BTCUSDT": 108}}},
    )
    assert result["requested_price"] == 108


def test_order_value_metadata() -> None:
    portfolio = PaperPortfolio(
        PaperTradingConfig(
            starting_cash=10_000,
            commission_rate=0,
            slippage_rate=0,
            default_order_value=1_000,
            max_position_pct=1,
        )
    )
    result = portfolio.execute_decision(
        decision(metadata={"order_value": 2_000})
    )
    assert result["gross_value"] == 2_000


def test_close_all() -> None:
    portfolio = PaperPortfolio(
        PaperTradingConfig(
            starting_cash=10_000,
            commission_rate=0,
            slippage_rate=0,
            default_order_value=1_000,
            max_position_pct=1,
        )
    )
    portfolio.buy(symbol="BTCUSDT", price=100)
    portfolio.buy(symbol="ETHUSDT", price=200)
    trades = portfolio.close_all(
        {"BTCUSDT": 110, "ETHUSDT": 210}
    )
    assert len(trades) == 2
    assert portfolio.snapshot().open_positions == 0


def test_trade_history_bounded() -> None:
    portfolio = PaperPortfolio(
        PaperTradingConfig(
            starting_cash=10_000,
            commission_rate=0,
            slippage_rate=0,
            default_order_value=100,
            max_trade_history=2,
            allow_pyramiding=False,
        )
    )
    portfolio.buy(symbol="A", price=10)
    portfolio.sell(symbol="A", price=11)
    portfolio.buy(symbol="B", price=10)
    assert len(portfolio.trades) == 2


def test_positions_report() -> None:
    portfolio = PaperPortfolio(
        PaperTradingConfig(
            starting_cash=10_000,
            commission_rate=0,
            slippage_rate=0,
            default_order_value=1_000,
        )
    )
    portfolio.buy(symbol="BTCUSDT", price=100)
    rows = portfolio.positions_report()
    assert rows[0]["symbol"] == "BTCUSDT"


def test_trades_report_limit() -> None:
    portfolio = PaperPortfolio(
        PaperTradingConfig(
            starting_cash=10_000,
            commission_rate=0,
            slippage_rate=0,
            default_order_value=1_000,
        )
    )
    portfolio.buy(symbol="BTCUSDT", price=100)
    portfolio.sell(symbol="BTCUSDT", price=110)
    assert len(portfolio.trades_report(limit=1)) == 1


def test_execution_adapter() -> None:
    portfolio = PaperPortfolio(
        PaperTradingConfig(
            starting_cash=10_000,
            commission_rate=0,
            slippage_rate=0,
            default_order_value=1_000,
        )
    )
    adapter = PaperTradingExecutionAdapter(portfolio)
    result = adapter.execute(decision(), {})
    assert result["status"] == "FILLED"


def test_execution_health_report() -> None:
    portfolio = PaperPortfolio(
        PaperTradingConfig(
            starting_cash=10_000,
            commission_rate=0,
            slippage_rate=0,
            default_order_value=1_000,
        )
    )
    adapter = PaperTradingExecutionAdapter(portfolio)
    report = adapter.health_report()
    assert report["equity"] == 10_000


def test_bridge_binds() -> None:
    runtime = FakeRuntime()
    bridge = PaperTradingRobotBridge(runtime=runtime)
    bridge.bind()
    assert runtime.execution is bridge.execution_adapter
    assert len(runtime.market_data_engine.callbacks) == 1


def test_bridge_binds_once() -> None:
    runtime = FakeRuntime()
    bridge = PaperTradingRobotBridge(runtime=runtime)
    bridge.bind()
    bridge.bind()
    assert len(runtime.market_data_engine.callbacks) == 1


def test_bridge_updates_trade_price() -> None:
    runtime = FakeRuntime()
    portfolio = PaperPortfolio(
        PaperTradingConfig(
            starting_cash=10_000,
            commission_rate=0,
            slippage_rate=0,
            default_order_value=1_000,
        )
    )
    portfolio.buy(symbol="BTCUSDT", price=100)
    bridge = PaperTradingRobotBridge(
        runtime=runtime,
        portfolio=portfolio,
    )
    event = MarketDataEvent(
        MarketDataEventType.TRADE,
        "BTCUSDT",
        TradeTick(
            symbol="BTCUSDT",
            price=120,
            quantity=1,
            trade_time=1,
            is_buyer_maker=False,
        ),
        {},
    )
    bridge._on_market_event(event)
    assert portfolio.positions["BTCUSDT"].last_price == 120


def test_bridge_updates_kline_price() -> None:
    runtime = FakeRuntime()
    portfolio = PaperPortfolio(
        PaperTradingConfig(
            starting_cash=10_000,
            commission_rate=0,
            slippage_rate=0,
            default_order_value=1_000,
        )
    )
    portfolio.buy(symbol="BTCUSDT", price=100)
    bridge = PaperTradingRobotBridge(
        runtime=runtime,
        portfolio=portfolio,
    )
    event = MarketDataEvent(
        MarketDataEventType.KLINE,
        "BTCUSDT",
        KlineUpdate(
            symbol="BTCUSDT",
            interval="1h",
            open_time=1,
            close_time=2,
            open=100,
            high=125,
            low=95,
            close=115,
            volume=1000,
            trade_count=10,
            closed=True,
        ),
        {},
    )
    bridge._on_market_event(event)
    assert portfolio.positions["BTCUSDT"].last_price == 115


def test_dashboard() -> None:
    runtime = FakeRuntime()
    bridge = PaperTradingRobotBridge(runtime=runtime)
    dashboard = bridge.dashboard()
    assert "portfolio" in dashboard
    assert "positions" in dashboard
    assert "recent_trades" in dashboard


def test_invalid_price_rejected() -> None:
    portfolio = PaperPortfolio()
    with pytest.raises(ValueError):
        portfolio.buy(symbol="BTCUSDT", price=0)
