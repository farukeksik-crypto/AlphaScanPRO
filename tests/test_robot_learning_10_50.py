from __future__ import annotations

import json
import sqlite3
from datetime import datetime

import pytest

from engine.robot_learning import build_robot_learning_report
from engine.trade_journal_pro import ensure_trade_journal_pro


def _connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    ensure_trade_journal_pro(connection)
    return connection


def _insert(connection: sqlite3.Connection, *, score: float, pnl: float, risk: str = "Orta") -> None:
    now = datetime.now().isoformat(timespec="seconds")
    connection.execute(
        """INSERT INTO trade_journal_pro(
            position_id, account_id, market, symbol, event_type, side, quantity,
            entry_price, exit_price, gross_pnl, commission, net_pnl, entry_score,
            exit_score, exit_action, exit_reason, confirmations, break_even_active,
            trailing_active, tp_stage, opened_at, closed_at, holding_minutes,
            mfe_pct, mae_pct, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (1, "A", "KRIPTO", "BTC", "FULL_EXIT", "SELL", 1, 100, 101, pnl, 0,
         pnl, score, 50, "SMART_EXIT", "test", 2, 0, 0, 0, now, now, 60, 2, -1,
         json.dumps({"decision": "AL ADAY", "risk": risk, "strategy_profile": "Default"})),
    )
    connection.commit()


def test_low_sample_only_recommends_data_collection() -> None:
    connection = _connection()
    for _ in range(4):
        _insert(connection, score=86, pnl=10)
    report = build_robot_learning_report(connection, minimum_sample=10)
    assert report.data_ready is False
    assert report.recommendations[0].priority == "BİLGİ"
    assert report.recommendations[0].automatic_change is False


def test_stable_profitable_segment_creates_opportunity() -> None:
    connection = _connection()
    for _ in range(10):
        _insert(connection, score=91, pnl=10)
    report = build_robot_learning_report(connection, minimum_sample=10)
    assert report.data_ready is True
    assert any(item.priority == "FIRSAT" for item in report.recommendations)
    score = next(item for item in report.segments if item.dimension == "Puan Bandı" and item.segment == "90+")
    assert score.stable is True
    assert score.profit_factor == pytest.approx(float("inf"))


def test_unstable_segment_is_not_promoted() -> None:
    connection = _connection()
    for _ in range(5):
        _insert(connection, score=91, pnl=20)
    for _ in range(5):
        _insert(connection, score=91, pnl=-15)
    report = build_robot_learning_report(connection, minimum_sample=10)
    score = next(item for item in report.segments if item.dimension == "Puan Bandı" and item.segment == "90+")
    assert score.stable is False
    assert not any(item.priority == "FIRSAT" and "90+" in item.title for item in report.recommendations)


def test_invalid_parameters_rejected() -> None:
    connection = _connection()
    with pytest.raises(ValueError):
        build_robot_learning_report(connection, lookback_days=0)
    with pytest.raises(ValueError):
        build_robot_learning_report(connection, minimum_sample=4)
