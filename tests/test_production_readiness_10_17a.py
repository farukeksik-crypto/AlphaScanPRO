from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from engine.production_readiness import (
    CheckStatus,
    ProductionReadinessChecker,
    WorkerWatchdog,
    format_text_report,
)


def _database(path):
    with sqlite3.connect(path) as connection:
        for table in ProductionReadinessChecker.REQUIRED_TABLES:
            connection.execute(f"CREATE TABLE {table} (id INTEGER)")


def test_watchdog_reports_missing_as_warning(tmp_path):
    result = WorkerWatchdog(tmp_path / "missing").inspect(required=False)
    assert result.status is CheckStatus.WARN
    assert result.age_seconds is None


def test_watchdog_reports_fresh_heartbeat(tmp_path):
    heartbeat = tmp_path / "heartbeat"
    now = datetime.now(timezone.utc)
    heartbeat.write_text(now.isoformat(), encoding="utf-8")
    result = WorkerWatchdog(heartbeat, stale_after_seconds=60).inspect(now=now)
    assert result.status is CheckStatus.PASS
    assert result.age_seconds == 0


def test_watchdog_reports_stale_heartbeat(tmp_path):
    heartbeat = tmp_path / "heartbeat"
    now = datetime.now(timezone.utc)
    heartbeat.write_text((now - timedelta(minutes=10)).isoformat(), encoding="utf-8")
    result = WorkerWatchdog(heartbeat, stale_after_seconds=60).inspect(now=now)
    assert result.status is CheckStatus.FAIL


def test_database_check_passes_with_required_schema(tmp_path):
    db = tmp_path / "database" / "alphascan.db"
    db.parent.mkdir()
    _database(db)
    checker = ProductionReadinessChecker(tmp_path, database_path=db, required_modules=("sys",), min_free_gb=0)
    result = checker._check_database()
    assert result.status is CheckStatus.PASS


def test_database_check_fails_when_table_missing(tmp_path):
    db = tmp_path / "alphascan.db"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE robot_state (id INTEGER)")
    checker = ProductionReadinessChecker(tmp_path, database_path=db, required_modules=("sys",), min_free_gb=0)
    result = checker._check_database()
    assert result.status is CheckStatus.FAIL
    assert "positions" in result.details["missing_tables"]


def test_dependency_check_lists_missing_module(tmp_path):
    checker = ProductionReadinessChecker(tmp_path, required_modules=("module_that_does_not_exist_1017a",))
    result = checker._check_dependencies()
    assert result.status is CheckStatus.FAIL
    assert result.details["missing"] == ["module_that_does_not_exist_1017a"]


def test_writable_paths_are_created(tmp_path):
    checker = ProductionReadinessChecker(tmp_path, required_modules=("sys",), min_free_gb=0)
    result = checker._check_writable_paths()
    assert result.status is CheckStatus.PASS
    assert (tmp_path / "runtime").is_dir()


def test_full_report_ready_with_worker_warning(tmp_path, monkeypatch):
    db = tmp_path / "database" / "alphascan.db"
    db.parent.mkdir()
    _database(db)
    checker = ProductionReadinessChecker(tmp_path, database_path=db, required_modules=("sys",), min_free_gb=0)
    monkeypatch.setattr(checker, "_check_core_modules", lambda: checker._check_python())
    monkeypatch.setattr(checker, "_check_git_hygiene", lambda: checker._check_python())
    report = checker.run(require_worker=False)
    assert report.ready is True
    assert report.verdict == "READY_WITH_WARNINGS"
    assert report.warnings == 1
    assert "Paper Trading Readiness" in format_text_report(report)


def test_full_report_not_ready_when_worker_required(tmp_path, monkeypatch):
    db = tmp_path / "database" / "alphascan.db"
    db.parent.mkdir()
    _database(db)
    checker = ProductionReadinessChecker(tmp_path, database_path=db, required_modules=("sys",), min_free_gb=0)
    monkeypatch.setattr(checker, "_check_core_modules", lambda: checker._check_python())
    monkeypatch.setattr(checker, "_check_git_hygiene", lambda: checker._check_python())
    report = checker.run(require_worker=True)
    assert report.ready is False
    assert report.verdict == "NOT_READY"


def test_json_report_contains_counts(tmp_path, monkeypatch):
    db = tmp_path / "database" / "alphascan.db"
    db.parent.mkdir()
    _database(db)
    checker = ProductionReadinessChecker(tmp_path, database_path=db, required_modules=("sys",), min_free_gb=0)
    monkeypatch.setattr(checker, "_check_core_modules", lambda: checker._check_python())
    monkeypatch.setattr(checker, "_check_git_hygiene", lambda: checker._check_python())
    payload = checker.run().to_json()
    assert '"passed"' in payload
    assert '"verdict"' in payload
