from __future__ import annotations

from pathlib import Path

from database.db import Database
from database.intelligence_repository import IntelligenceRepository
from engine.models.trade_snapshot import TradeSnapshot


def test_repository_queue_snapshot_and_summary(tmp_path: Path):
    db = Database(tmp_path / "intelligence.db")
    repo = IntelligenceRepository(db)
    event_id = repo.enqueue(event_type="DECISION_ACCEPTED", market="KRIPTO", universe="Hepsi", symbol="BTC", payload={"score": 88})
    assert event_id > 0
    snapshot = TradeSnapshot.open(
        trade_id="trade-1", market="KRIPTO", universe="Hepsi", symbol="BTC",
        decision="NET AL", score=88, confidence=75, probability=72, risk_level="Orta",
        entry_price=100, stop_loss=95, take_profit=110, quantity=2,
    )
    repo.save_snapshot(snapshot, position_id=12, account_id="KRIPTO")
    loaded = repo.get_snapshot("trade-1")
    assert loaded is not None
    assert loaded.symbol == "BTC"
    summary = repo.summary()
    assert summary["learning_events"] == 1
    assert summary["trade_snapshots"] == 1
    assert summary["open_trade_snapshots"] == 1


def test_record_decision_events(tmp_path: Path):
    db = Database(tmp_path / "events.db")
    repo = IntelligenceRepository(db)
    count = repo.record_decision_events([{
        "run_id": 1, "market": "BIST", "universe": "Genel", "symbol": "ASELS",
        "decision": "AL ADAY", "score": 80, "confidence": 70, "probability": 65,
        "risk_level": "Orta", "accepted": True, "reject_reasons": [],
        "trace_payload": {"accepted": True},
    }])
    assert count == 1
    assert repo.summary()["accepted_events"] == 1
