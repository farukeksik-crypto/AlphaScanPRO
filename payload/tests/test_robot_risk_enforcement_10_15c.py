from __future__ import annotations

import sqlite3

import pytest

from database.db import Database
from engine.portfolio_risk_manager import PortfolioRiskConfig
from engine.robot_risk_enforcement import RobotRiskEnforcer


def make_enforcer(tmp_path, **changes):
    db = Database(tmp_path / "risk.db")
    values = dict(initial_equity=100_000, max_open_positions=3,
                  max_total_exposure_pct=50, max_symbol_exposure_pct=20,
                  max_group_exposure_pct=30, max_total_risk_pct=4,
                  max_risk_per_trade_pct=1, daily_loss_limit_pct=3,
                  minimum_position_value=100)
    values.update(changes)
    return db, RobotRiskEnforcer(db, account_id="paper", market="KRIPTO",
                                 config=PortfolioRiskConfig(**values))


def test_approved_decision_is_persisted(tmp_path):
    db, enforcer = make_enforcer(tmp_path)
    result = enforcer.evaluate(symbol="BTCUSDT", price=100, stop_price=95,
        requested_quantity=100, equity=100_000, day_start_equity=100_000,
        realized_pnl_today=0)
    assert result.approved is True
    with db.connect() as c:
        row = c.execute("SELECT event_type, decision FROM robot_risk_events").fetchone()
    assert row == ("RISK_APPROVED", "APPROVED")


def test_position_is_reduced_to_symbol_limit(tmp_path):
    _, enforcer = make_enforcer(tmp_path, max_symbol_exposure_pct=10)
    result = enforcer.evaluate(symbol="BTCUSDT", price=100, stop_price=95,
        requested_quantity=200, equity=100_000, day_start_equity=100_000,
        realized_pnl_today=0)
    assert result.approved is True
    assert result.reduced is True
    assert result.approved_quantity == pytest.approx(100)


def test_daily_loss_blocks_new_trade(tmp_path):
    _, enforcer = make_enforcer(tmp_path)
    result = enforcer.evaluate(symbol="ETHUSDT", price=100, stop_price=95,
        requested_quantity=10, equity=97_000, day_start_equity=100_000,
        realized_pnl_today=-3_000)
    assert result.approved is False
    assert result.reason == "DAILY_LOSS_LIMIT"


def test_existing_positions_are_synchronized(tmp_path):
    _, enforcer = make_enforcer(tmp_path, max_total_exposure_pct=20)
    positions=[{"symbol":"BTCUSDT","quantity":150,"entry_price":100,
                "current_price":100,"stop_price":95,"group":"KRIPTO"}]
    result = enforcer.evaluate(symbol="ETHUSDT", price=100, stop_price=95,
        requested_quantity=100, equity=100_000, day_start_equity=100_000,
        realized_pnl_today=0, positions=positions, group="KRIPTO")
    assert result.approved is True
    assert result.approved_quantity == pytest.approx(50)


def test_manual_emergency_lock_and_reset(tmp_path):
    _, enforcer = make_enforcer(tmp_path)
    enforcer.set_manual_lock(True, "Operatör acil durdurma")
    result = enforcer.evaluate(symbol="SOLUSDT", price=50, stop_price=45,
        requested_quantity=10, equity=100_000, day_start_equity=100_000,
        realized_pnl_today=0)
    assert result.approved is False
    assert result.reason == "MANUAL_RISK_LOCK"
    enforcer.set_manual_lock(False)
    assert enforcer.lock_status()["locked"] is False


def test_schema_is_idempotent(tmp_path):
    db, enforcer = make_enforcer(tmp_path)
    RobotRiskEnforcer(db, account_id="paper", market="KRIPTO", config=enforcer.config)
    with db.connect() as c:
        names={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"robot_risk_events", "robot_risk_locks"} <= names
