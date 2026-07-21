from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from engine.paper_trading_robot import PaperPortfolio, PaperTradingConfig
from engine.performance_analytics import (
    EquityPoint,
    PerformanceAnalytics,
    PerformanceConfig,
    PerformanceRobotBridge,
    PerformanceTracker,
    TradeAnalyzer,
)


def portfolio() -> PaperPortfolio:
    return PaperPortfolio(
        PaperTradingConfig(
            starting_cash=10_000,
            commission_rate=0,
            slippage_rate=0,
            default_order_value=1_000,
            max_position_pct=1,
        )
    )


def test_config_validation() -> None:
    with pytest.raises(ValueError):
        PerformanceConfig(periods_per_year=0).validate()


def test_tracker_starting_equity_validation() -> None:
    with pytest.raises(ValueError):
        PerformanceTracker(starting_equity=0)


def test_record_equity_point_sorted() -> None:
    tracker = PerformanceTracker(starting_equity=1000)
    tracker.record_equity_point(EquityPoint(2, 1100, 1100, 0, 100, 0))
    tracker.record_equity_point(EquityPoint(1, 1050, 1050, 0, 50, 0))
    assert [point.timestamp for point in tracker.equity_points] == [1, 2]


def test_returns() -> None:
    tracker = PerformanceTracker(starting_equity=1000)
    tracker.record_equity_point(EquityPoint(1, 1100, 1100, 0, 100, 0))
    tracker.record_equity_point(EquityPoint(2, 1210, 1210, 0, 210, 0))
    assert tracker.returns() == pytest.approx([0.1, 0.1])


def test_drawdown_series() -> None:
    tracker = PerformanceTracker(starting_equity=1000)
    tracker.record_equity_point(EquityPoint(1, 1200, 1200, 0, 200, 0))
    tracker.record_equity_point(EquityPoint(2, 900, 900, 0, -100, 0))
    rows = tracker.drawdown_series()
    assert rows[-1]["drawdown"] == -300
    assert rows[-1]["drawdown_pct"] == -25


def test_risk_stats_total_return() -> None:
    tracker = PerformanceTracker(starting_equity=1000)
    tracker.record_equity_point(EquityPoint(1, 1100, 1100, 0, 100, 0))
    stats = tracker.risk_stats()
    assert stats.total_return == 100
    assert stats.total_return_pct == 10


def test_risk_stats_sharpe() -> None:
    tracker = PerformanceTracker(
        starting_equity=1000,
        config=PerformanceConfig(periods_per_year=365),
    )
    tracker.record_equity_point(EquityPoint(1, 1100, 1100, 0, 100, 0))
    tracker.record_equity_point(EquityPoint(2, 1080, 1080, 0, 80, 0))
    tracker.record_equity_point(EquityPoint(3, 1200, 1200, 0, 200, 0))
    assert math.isfinite(tracker.risk_stats().sharpe_ratio)


def test_period_daily() -> None:
    tracker = PerformanceTracker(starting_equity=1000)
    tracker.record_equity_point(EquityPoint(0, 1100, 1100, 0, 100, 0))
    rows = tracker.period_performance("daily")
    assert rows[0]["period"] == "1970-01-01"
    assert rows[0]["pnl"] == 100


def test_period_weekly() -> None:
    tracker = PerformanceTracker(starting_equity=1000)
    tracker.record_equity_point(EquityPoint(0, 1100, 1100, 0, 100, 0))
    assert "W" in tracker.period_performance("weekly")[0]["period"]


def test_period_monthly() -> None:
    tracker = PerformanceTracker(starting_equity=1000)
    tracker.record_equity_point(EquityPoint(0, 1100, 1100, 0, 100, 0))
    assert tracker.period_performance("monthly")[0]["period"] == "1970-01"


def test_period_invalid() -> None:
    tracker = PerformanceTracker(starting_equity=1000)
    with pytest.raises(ValueError):
        tracker.period_performance("yearly")


def test_trade_stats() -> None:
    p = portfolio()
    p.buy(symbol="BTCUSDT", price=100)
    p.sell(symbol="BTCUSDT", price=110)
    p.buy(symbol="ETHUSDT", price=100)
    p.sell(symbol="ETHUSDT", price=90)
    stats = TradeAnalyzer().trade_stats(p.trades)
    assert stats.closed_trades == 2
    assert stats.winning_trades == 1
    assert stats.losing_trades == 1
    assert stats.win_rate == 50


def test_profit_factor() -> None:
    p = portfolio()
    p.buy(symbol="BTCUSDT", price=100)
    p.sell(symbol="BTCUSDT", price=120)
    p.buy(symbol="ETHUSDT", price=100)
    p.sell(symbol="ETHUSDT", price=90)
    stats = TradeAnalyzer().trade_stats(p.trades)
    assert stats.profit_factor == 2


def test_best_worst_trade() -> None:
    p = portfolio()
    p.buy(symbol="BTCUSDT", price=100)
    p.sell(symbol="BTCUSDT", price=120)
    p.buy(symbol="ETHUSDT", price=100)
    p.sell(symbol="ETHUSDT", price=80)
    stats = TradeAnalyzer().trade_stats(p.trades)
    assert stats.best_trade == 200
    assert stats.worst_trade == -200


def test_ranked_trades() -> None:
    p = portfolio()
    p.buy(symbol="A", price=100)
    p.sell(symbol="A", price=110)
    p.buy(symbol="B", price=100)
    p.sell(symbol="B", price=90)
    best, worst = TradeAnalyzer().ranked_trades(p.trades, limit=1)
    assert best[0]["realized_pnl"] == 100
    assert worst[0]["realized_pnl"] == -100


def test_record_portfolio() -> None:
    p = portfolio()
    analytics = PerformanceAnalytics(starting_equity=10_000)
    point = analytics.record_portfolio(p, timestamp=1)
    assert point.equity == 10_000
    assert point.timestamp == 1


def test_build_report() -> None:
    p = portfolio()
    p.buy(symbol="BTCUSDT", price=100)
    p.sell(symbol="BTCUSDT", price=110)
    analytics = PerformanceAnalytics(starting_equity=10_000)
    analytics.record_portfolio(p, timestamp=1)
    report = analytics.build_report(p.trades)
    assert report.ending_equity == 10_100
    assert report.trade_stats.net_profit == 100


def test_dashboard_payload() -> None:
    p = portfolio()
    analytics = PerformanceAnalytics(starting_equity=10_000)
    analytics.record_portfolio(p, timestamp=1)
    payload = analytics.dashboard_payload(p.trades)
    assert "summary" in payload
    assert "equity_curve" in payload


def test_export_json(tmp_path: Path) -> None:
    p = portfolio()
    analytics = PerformanceAnalytics(starting_equity=10_000)
    analytics.record_portfolio(p, timestamp=1)
    report = analytics.build_report(p.trades)
    target = analytics.export_json(report, tmp_path / "report.json")
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["ending_equity"] == 10_000


def test_export_csv(tmp_path: Path) -> None:
    p = portfolio()
    analytics = PerformanceAnalytics(starting_equity=10_000)
    analytics.record_portfolio(p, timestamp=1)
    report = analytics.build_report(p.trades)
    target = analytics.export_csv(report, tmp_path / "equity.csv")
    text = target.read_text(encoding="utf-8-sig")
    assert "timestamp,equity,cash" in text


def test_robot_bridge_capture() -> None:
    p = portfolio()
    bridge = PerformanceRobotBridge(portfolio=p)
    point = bridge.capture(timestamp=1)
    assert point.equity == 10_000


def test_robot_bridge_report() -> None:
    p = portfolio()
    bridge = PerformanceRobotBridge(portfolio=p)
    bridge.capture(timestamp=1)
    report = bridge.report()
    assert report.starting_equity == 10_000


def test_robot_bridge_dashboard() -> None:
    p = portfolio()
    bridge = PerformanceRobotBridge(portfolio=p)
    bridge.capture(timestamp=1)
    dashboard = bridge.dashboard()
    assert dashboard["summary"]["ending_equity"] == 10_000


def test_empty_trade_stats() -> None:
    stats = TradeAnalyzer().trade_stats([])
    assert stats.total_trades == 0
    assert stats.win_rate == 0


def test_equity_point_to_dict() -> None:
    point = EquityPoint(1, 1000, 900, 100, 0, 0)
    assert point.to_dict()["market_value"] == 100
