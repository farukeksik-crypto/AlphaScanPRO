from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from engine.startup_manager import StartupManager


def test_status_detects_healthy_worker(tmp_path, monkeypatch):
    monkeypatch.setattr("engine.startup_manager.PID_FILE", tmp_path / "worker.pid")
    monkeypatch.setattr("engine.startup_manager.HEARTBEAT_FILE", tmp_path / "worker.heartbeat")
    (tmp_path / "worker.pid").write_text("123", encoding="utf-8")
    (tmp_path / "worker.heartbeat").write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
    manager = StartupManager(tmp_path)
    with patch.object(manager, "is_installed", return_value=True), \
         patch.object(manager, "task_points_to_current_project", return_value=True), \
         patch.object(manager, "legacy_tasks", return_value=()), \
         patch.object(manager, "process_running", return_value=True):
        state = manager.status()
    assert state.installed is True
    assert state.task_correct is True
    assert state.worker_running is True
    assert state.stale is False


def test_status_marks_stale_heartbeat(tmp_path, monkeypatch):
    monkeypatch.setattr("engine.startup_manager.PID_FILE", tmp_path / "worker.pid")
    monkeypatch.setattr("engine.startup_manager.HEARTBEAT_FILE", tmp_path / "worker.heartbeat")
    (tmp_path / "worker.pid").write_text("456", encoding="utf-8")
    old = datetime.now(timezone.utc) - timedelta(minutes=10)
    (tmp_path / "worker.heartbeat").write_text(old.isoformat(), encoding="utf-8")
    manager = StartupManager(tmp_path)
    with patch.object(manager, "is_installed", return_value=False), \
         patch.object(manager, "task_points_to_current_project", return_value=False), \
         patch.object(manager, "legacy_tasks", return_value=()), \
         patch.object(manager, "process_running", return_value=True):
        state = manager.status(stale_after_seconds=60)
    assert state.stale is True


def test_task_command_uses_current_project_and_quotes_paths(tmp_path):
    manager = StartupManager(tmp_path / "Alpha Scan", python_executable=r"C:\Python 313\python.exe")
    command = manager._task_command()
    assert command.startswith('"C:\\Python 313\\python.exe"')
    assert str((tmp_path / "Alpha Scan" / "startup_control.py").resolve()) in command


def test_remove_legacy_tasks_deletes_only_existing(tmp_path):
    manager = StartupManager(tmp_path)
    calls = []

    def fake_exists(name):
        return name == "AlphaScanPRO Background Worker"

    def fake_run(command, **_kwargs):
        calls.append(command)
        class Result:
            returncode = 0
            stdout = "SUCCESS"
            stderr = ""
        return Result()

    with patch.object(manager, "task_exists", side_effect=fake_exists), patch.object(manager, "_run", side_effect=fake_run):
        removed = manager.remove_legacy_tasks()
    assert removed == ("AlphaScanPRO Background Worker",)
    assert calls == [["schtasks", "/Delete", "/F", "/TN", "AlphaScanPRO Background Worker"]]
