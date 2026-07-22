from __future__ import annotations

import math
import sqlite3

from engine.performance_analytics import build_performance_report, calculate_performance
from engine.trade_journal_pro import TradeJournalProEvent, record_trade_event


def _trade(symbol: str, pnl: float, closed_at: str, *, exit_action: str = "FULL_EXIT") -> dict:
    return {
        "symbol": symbol,
        "market": "KRIPTO",
        "net_pnl": pnl,
        "commission": 1.0,
        "holding_minutes": 60.0,
        "mfe_pct": 3.0,
        "mae_pct": -1.0,
        "closed_at": closed_at,
        "exit_action": exit_action,
    }


def test_core_metrics_and_equity_curve() -> None:
    report = calculate_performance(
        [
            _trade("BTC", 100.0, "2026-07-01T10:00:00"),
            _trade("ETH", -40.0, "2026-07-02T10:00:00"),
            _trade("BTC", 20.0, "2026-07-03T10:00:00"),
        ],
        starting_equity=1000.0,
    )
    metrics = report.metrics
    assert metrics.trade_count == 3
    assert metrics.winning_trades == 2
    assert metrics.losing_trades == 1
    assert round(metrics.win_rate_pct, 2) == 66.67
    assert metrics.net_pnl == 80.0
    assert metrics.gross_profit == 120.0
    assert metrics.gross_loss == 40.0
    assert metrics.profit_factor == 3.0
    assert round(metrics.expectancy, 6) == round(80 / 3, 6)
    assert metrics.max_drawdown == 40.0
    assert len(report.equity_curve) == 3
    assert report.equity_curve[-1]["equity"] == 1080.0


def test_profit_factor_is_infinite_without_losses() -> None:
    report = calculate_performance([_trade("BTC", 50, "2026-07-01T10:00:00")])
    assert math.isinf(report.metrics.profit_factor)


def test_period_symbol_and_exit_aggregations() -> None:
    report = calculate_performance(
        [
            _trade("BTC", 100, "2026-07-01T10:00:00", exit_action="TP1"),
            _trade("BTC", -25, "2026-07-02T10:00:00", exit_action="STOP"),
            _trade("ETH", 10, "2026-08-02T10:00:00", exit_action="TP1"),
        ]
    )
    assert len(report.daily_pnl) == 3
    assert len(report.monthly_pnl) == 2
    assert report.symbol_stats[0]["symbol"] == "BTC"
    tp1 = next(row for row in report.exit_stats if row["exit_action"] == "TP1")
    assert tp1["trade_count"] == 2
    assert tp1["net_pnl"] == 110


def test_sqlite_filters_and_partial_exit_switch() -> None:
    connection = sqlite3.connect(":memory:")
    base = dict(
        position_id=1,
        account_id="KRIPTO_USDT",
        market="KRIPTO",
        symbol="BTC/USDT",
        side="SELL",
        quantity=1.0,
        entry_price=100.0,
        exit_price=110.0,
        gross_pnl=10.0,
        commission=1.0,
        net_pnl=9.0,
        opened_at="2026-07-01T09:00:00",
        closed_at="2026-07-01T10:00:00",
    )
    record_trade_event(connection, TradeJournalProEvent(event_type="FULL_EXIT", **base))
    record_trade_event(
        connection,
        TradeJournalProEvent(
            event_type="PARTIAL_EXIT",
            position_id=2,
            account_id="KRIPTO_USDT",
            market="KRIPTO",
            symbol="ETH/USDT",
            side="SELL",
            quantity=1.0,
            entry_price=100.0,
            exit_price=95.0,
            gross_pnl=-5.0,
            commission=1.0,
            net_pnl=-6.0,
            opened_at="2026-07-02T09:00:00",
            closed_at="2026-07-02T10:00:00",
        ),
    )
    connection.commit()

    all_report = build_performance_report(connection, account_id="KRIPTO_USDT")
    full_only = build_performance_report(
        connection,
        account_id="KRIPTO_USDT",
        include_partial_exits=False,
    )
    assert all_report.metrics.trade_count == 2
    assert all_report.metrics.net_pnl == 3.0
    assert full_only.metrics.trade_count == 1
    assert full_only.metrics.net_pnl == 9.0
