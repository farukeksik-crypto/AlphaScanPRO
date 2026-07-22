from __future__ import annotations

from database.db import Database
from engine.robot_risk_enforcement import RobotRiskDecision, RobotRiskEnforcer
from engine.robot_risk_monitor import (
    get_risk_lock,
    list_risk_events,
    set_risk_lock,
    summarize_risk_events,
)
from engine.portfolio_risk_manager import PortfolioRiskConfig


def _db(tmp_path):
    return Database(tmp_path / "risk_monitor.sqlite")


def test_lock_round_trip(tmp_path):
    db = _db(tmp_path)
    assert get_risk_lock(db, "crypto_main")["locked"] is False
    set_risk_lock(db, "crypto_main", locked=True, reason="manual review")
    status = get_risk_lock(db, "crypto_main")
    assert status["locked"] is True
    assert status["reason"] == "manual review"
    set_risk_lock(db, "crypto_main", locked=False)
    assert get_risk_lock(db, "crypto_main")["locked"] is False


def test_event_listing_filter_and_summary(tmp_path):
    db = _db(tmp_path)
    enforcer = RobotRiskEnforcer(
        db, account_id="crypto_main", market="KRIPTO", config=PortfolioRiskConfig()
    )
    enforcer.record("BTC/USDT", RobotRiskDecision(
        approved=True, decision="APPROVED", reason="OK", message="ok",
        requested_quantity=2, approved_quantity=2, requested_value=200,
        approved_value=200, risk_amount=10, metrics={"x": 1},
    ), {"source": "test"})
    enforcer.record("ETH/USDT", RobotRiskDecision(
        approved=True, decision="REDUCED", reason="EXPOSURE_LIMIT", message="reduced",
        requested_quantity=3, approved_quantity=1, requested_value=300,
        approved_value=100, risk_amount=5, metrics={},
    ))
    enforcer.record("SOL/USDT", RobotRiskDecision(
        approved=False, decision="REJECTED", reason="DAILY_LOSS_LIMIT", message="blocked",
        requested_quantity=4, approved_quantity=0, requested_value=400,
        approved_value=0, risk_amount=0, metrics={},
    ))

    all_events = list_risk_events(db, "crypto_main")
    assert len(all_events) == 3
    assert all_events[2]["metadata"] == {"source": "test"}
    rejected = list_risk_events(db, "crypto_main", event_type="RISK_REJECTED")
    assert len(rejected) == 1
    assert rejected[0]["symbol"] == "SOL/USDT"

    summary = summarize_risk_events(db, "crypto_main")
    assert summary.total_events == 3
    assert summary.approved_count == 1
    assert summary.reduced_count == 1
    assert summary.rejected_count == 1
    assert summary.requested_value == 900
    assert summary.approved_value == 300
    assert summary.blocked_value == 600
    assert round(summary.rejection_rate_pct, 2) == 33.33
    assert summary.top_reasons[0]["count"] == 1


def test_limit_is_clamped_and_account_isolated(tmp_path):
    db = _db(tmp_path)
    enforcer = RobotRiskEnforcer(
        db, account_id="bist_main", market="BIST", config=PortfolioRiskConfig()
    )
    for index in range(3):
        enforcer.record(f"SYM{index}", RobotRiskDecision(
            approved=False, decision="REJECTED", reason="TEST", message="blocked",
            requested_quantity=1, approved_quantity=0, requested_value=10,
            approved_value=0, risk_amount=0, metrics={},
        ))
    assert len(list_risk_events(db, "bist_main", limit=2)) == 2
    assert list_risk_events(db, "crypto_main") == []
