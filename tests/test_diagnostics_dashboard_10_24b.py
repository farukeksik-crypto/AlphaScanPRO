from __future__ import annotations

import json

from database.background_repository import (
    filter_decision_dashboard_snapshot,
    latest_filter_decisions,
)
from database.db import Database
from engine.filter_analytics import FilterAnalytics


def _database(tmp_path):
    db = Database(tmp_path / "diagnostics.db")
    FilterAnalytics(db)
    return db


def _insert(db, *, run_id=1, market="BIST", symbol="AAA", accepted=0, reason="score", decision="AL ADAY", risk="Orta"):
    flags = {
        "score": int(reason == "score"), "confidence": int(reason == "confidence"),
        "probability": int(reason == "probability"), "risk": int(reason == "risk"),
        "decision": int(reason == "decision"), "open_position": int(reason == "open_position"),
        "robot_disabled": int(reason == "robot_disabled"),
    }
    reasons = [] if accepted else [reason]
    with db.connect() as con:
        con.execute(
            """INSERT INTO filter_decisions (
                run_id, market, universe, symbol, name, decision, score, confidence,
                probability, risk_level, robot_enabled, accepted, reject_score,
                reject_confidence, reject_probability, reject_risk, reject_decision,
                reject_open_position, reject_robot_disabled, reject_reasons,
                minimum_score, minimum_confidence, minimum_probability,
                allowed_decisions, allowed_risks, price, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (run_id, market, "Hepsi", symbol, symbol, decision, 80, 70, 65, risk, 1,
             accepted, flags["score"], flags["confidence"], flags["probability"],
             flags["risk"], flags["decision"], flags["open_position"],
             flags["robot_disabled"], json.dumps(reasons), 75, 60, 60,
             '["NET AL","AL ADAY"]', '["Düşük","Orta"]', 100, "2026-07-25T12:00:00"),
        )
        con.commit()


def test_snapshot_empty_when_no_rows(tmp_path):
    snap = filter_decision_dashboard_snapshot(_database(tmp_path), "BIST")
    assert snap["scanned"] == 0
    assert snap["details"].empty


def test_snapshot_counts_accept_and_reject(tmp_path):
    db = _database(tmp_path)
    _insert(db, symbol="AAA", accepted=1, reason="")
    _insert(db, symbol="BBB", accepted=0, reason="score")
    snap = filter_decision_dashboard_snapshot(db, "BIST")
    assert (snap["scanned"], snap["accepted"], snap["rejected"]) == (2, 1, 1)
    assert snap["acceptance_rate_pct"] == 50.0


def test_snapshot_uses_latest_run_only(tmp_path):
    db = _database(tmp_path)
    _insert(db, run_id=1, symbol="OLD", accepted=0, reason="score")
    _insert(db, run_id=2, symbol="NEW", accepted=1, reason="")
    snap = filter_decision_dashboard_snapshot(db, "BIST")
    assert snap["run_id"] == 2
    assert snap["scanned"] == 1
    assert snap["details"].iloc[0]["Kod"] == "NEW"


def test_market_filter_is_respected(tmp_path):
    db = _database(tmp_path)
    _insert(db, market="BIST", symbol="BIST1")
    _insert(db, market="KRIPTO", symbol="BTC")
    frame = latest_filter_decisions(db, "KRIPTO")
    assert frame["market"].unique().tolist() == ["KRIPTO"]
    assert frame["symbol"].tolist() == ["BTC"]


def test_reject_reason_is_translated(tmp_path):
    db = _database(tmp_path)
    _insert(db, reason="probability")
    snap = filter_decision_dashboard_snapshot(db, "BIST")
    assert snap["reason_counts"].iloc[0].to_dict() == {"Engel": "Olasılık yetersiz", "Adet": 1}
    assert "Olasılık yetersiz" in snap["details"].iloc[0]["İşlem Açılmama Nedenleri"]
