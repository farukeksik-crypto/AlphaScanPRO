from __future__ import annotations

import json
import sqlite3
from datetime import datetime

import pytest

from engine.confidence_calibration import build_confidence_calibration_report
from engine.trade_journal_pro import ensure_trade_journal_pro


def _connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    ensure_trade_journal_pro(connection)
    return connection


def _insert(connection: sqlite3.Connection, *, probability: float | None, pnl: float) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    metadata = {} if probability is None else {"probability": probability}
    connection.execute(
        """INSERT INTO trade_journal_pro(
        position_id, account_id, market, symbol, event_type, side, quantity,
        entry_price, exit_price, gross_pnl, commission, net_pnl, entry_score,
        exit_score, exit_action, exit_reason, confirmations, break_even_active,
        trailing_active, tp_stage, opened_at, closed_at, holding_minutes,
        mfe_pct, mae_pct, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (1, "A", "KRIPTO", "BTC", "FULL_EXIT", "SELL", 1, 100, 101, pnl, 0,
         pnl, 85, 50, "SMART_EXIT", "test", 2, 0, 0, 0, now, now, 60, 2, -1,
         json.dumps(metadata)),
    )
    connection.commit()


def test_low_sample_reports_data_collection() -> None:
    connection = _connection()
    for _ in range(4):
        _insert(connection, probability=80, pnl=10)
    report = build_confidence_calibration_report(connection, minimum_sample=10)
    assert report.status == "VERİ BİRİKİYOR"
    assert report.data_ready is False


def test_percentage_and_ratio_probabilities_are_supported() -> None:
    connection = _connection()
    _insert(connection, probability=80, pnl=10)
    _insert(connection, probability=0.8, pnl=-10)
    report = build_confidence_calibration_report(connection, minimum_sample=5)
    assert report.eligible_trade_count == 2
    assert report.average_predicted_pct == pytest.approx(80.0)
    assert report.actual_win_rate_pct == pytest.approx(50.0)


def test_missing_probability_is_skipped() -> None:
    connection = _connection()
    _insert(connection, probability=None, pnl=10)
    report = build_confidence_calibration_report(connection, minimum_sample=5)
    assert report.eligible_trade_count == 0
    assert report.skipped_trade_count == 1


def test_well_calibrated_data_is_good() -> None:
    connection = _connection()
    for index in range(20):
        _insert(connection, probability=50, pnl=10 if index % 2 == 0 else -10)
    report = build_confidence_calibration_report(connection, minimum_sample=20)
    assert report.status == "İYİ"
    assert report.mean_absolute_calibration_error_pct == pytest.approx(0.0)
