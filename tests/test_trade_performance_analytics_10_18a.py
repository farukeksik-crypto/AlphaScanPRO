from __future__ import annotations

import math
import pandas as pd

from engine.trade_performance_analytics import (
    closed_trade_rows,
    equity_curve,
    performance_by,
    summarize_trade_history,
)


def sample_history() -> pd.DataFrame:
    return pd.DataFrame([
        {"side": "BUY", "symbol": "BTC", "market": "KRIPTO", "profit": 0, "created_at": "2026-07-20T10:00:00"},
        {"side": "SELL", "symbol": "BTC", "market": "KRIPTO", "profit": 100, "profit_pct": 5, "holding_minutes": 60, "mfe_pct": 8, "mae_pct": -2, "trade_quality_score": 90, "reason": "HEDEF", "created_at": "2026-07-20T11:00:00"},
        {"side": "SELL", "symbol": "ETH", "market": "KRIPTO", "profit": -40, "profit_pct": -2, "holding_minutes": 120, "mfe_pct": 1, "mae_pct": -4, "trade_quality_score": 55, "reason": "STOP", "created_at": "2026-07-20T13:00:00"},
        {"side": "SELL", "symbol": "BAKIR", "market": "EMTIA", "profit": 60, "profit_pct": 3, "holding_minutes": 180, "mfe_pct": 5, "mae_pct": -1, "trade_quality_score": 80, "reason": "TRAILING", "created_at": "2026-07-20T16:00:00"},
    ])


def test_only_sell_rows_are_closed_trades():
    closed = closed_trade_rows(sample_history())
    assert len(closed) == 3
    assert set(closed["side"]) == {"SELL"}


def test_summary_core_metrics():
    summary = summarize_trade_history(sample_history())
    assert summary.closed_trades == 3
    assert summary.winning_trades == 2
    assert summary.losing_trades == 1
    assert round(summary.win_rate_pct, 2) == 66.67
    assert summary.net_profit == 120
    assert summary.gross_profit == 160
    assert summary.gross_loss == 40
    assert summary.profit_factor == 4


def test_summary_average_metrics():
    summary = summarize_trade_history(sample_history())
    assert summary.average_win == 80
    assert summary.average_loss == 40
    assert summary.payoff_ratio == 2
    assert summary.average_holding_minutes == 120
    assert summary.average_quality_score == 75


def test_drawdown_is_calculated_chronologically():
    summary = summarize_trade_history(sample_history())
    assert summary.maximum_drawdown == 40


def test_empty_history_is_safe():
    summary = summarize_trade_history(pd.DataFrame())
    assert summary.closed_trades == 0
    assert summary.profit_factor is None
    assert equity_curve(pd.DataFrame()).empty


def test_no_loss_profit_factor_is_infinite():
    frame = pd.DataFrame([{"side": "SELL", "profit": 10}])
    assert math.isinf(summarize_trade_history(frame).profit_factor)


def test_breakdown_by_market():
    table = performance_by(sample_history(), "market")
    crypto = table[table["market"] == "KRIPTO"].iloc[0]
    assert crypto["İşlem"] == 2
    assert crypto["Net K/Z"] == 60


def test_breakdown_missing_column_is_empty():
    assert performance_by(sample_history(), "missing").empty


def test_equity_curve_last_value_matches_net_profit():
    curve = equity_curve(sample_history())
    assert curve.iloc[-1]["Kümülatif K/Z"] == 120
    assert curve["Drawdown"].min() == -40
