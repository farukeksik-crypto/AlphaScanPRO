from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Sequence

from config.background_settings import RUNTIME_DIR

TASK_NAME = "AlphaScanPRO_7x24_PaperTrading"
LEGACY_TASK_NAMES = (
    "AlphaScanPRO Background Worker",
    "AlphaScanPRO_BackgroundWorker",
)
PID_FILE = RUNTIME_DIR / "background_worker.pid"
HEARTBEAT_FILE = RUNTIME_DIR / "background_worker.heartbeat"


@dataclass(frozen=True)
class StartupStatus:
    installed: bool
    task_correct: bool
    worker_running: bool
    pid: int | None
    heartbeat_age_seconds: float | None
    stale: bool
    legacy_tasks: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "installed": self.installed,
            "task_correct": self.task_correct,
            "worker_running": self.worker_running,
            "pid": self.pid,
            "heartbeat_age_seconds": self.heartbeat_age_seconds,
            "stale": self.stale,
            "legacy_tasks": list(self.legacy_tasks),
        }


class StartupManager:
    def __init__(self, project_dir: str | Path | None = None, python_executable: str | None = None):
        self.project_dir = Path(project_dir or Path.cwd()).resolve()
        self.python_executable = str(python_executable or sys.executable)

    @staticmethod
    def _run(command: Sequence[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=check,
        )

    def _task_command(self) -> str:
        manager = self.project_dir / "startup_control.py"
        return f'"{self.python_executable}" "{manager}" run-worker'

    def _query_task(self, name: str, verbose: bool = False) -> subprocess.CompletedProcess[str]:
        command = ["schtasks", "/Query", "/TN", name]
        if verbose:
            command.extend(["/V", "/FO", "LIST"])
        return self._run(command)

    def task_exists(self, name: str) -> bool:
        return os.name == "nt" and self._query_task(name).returncode == 0

    def is_installed(self) -> bool:
        return self.task_exists(TASK_NAME)

    def legacy_tasks(self) -> tuple[str, ...]:
        if os.name != "nt":
            return ()
        return tuple(name for name in LEGACY_TASK_NAMES if self.task_exists(name))

    def task_points_to_current_project(self) -> bool:
        if not self.is_installed():
            return False
        try:
            result = self._query_task(TASK_NAME, verbose=True)
        except OSError:
            return False
        normalized = result.stdout.casefold().replace("/", "\\")
        project = str(self.project_dir).casefold().replace("/", "\\")
        return result.returncode == 0 and project in normalized and "startup_control.py" in normalized

    def remove_legacy_tasks(self) -> tuple[str, ...]:
        removed: list[str] = []
        for name in LEGACY_TASK_NAMES:
            if not self.task_exists(name):
                continue
            result = self._run(["schtasks", "/Delete", "/F", "/TN", name])
            if result.returncode != 0:
                raise RuntimeError(
                    f"Eski görev kaldırılamadı ({name}): "
                    + (result.stderr.strip() or result.stdout.strip() or "bilinmeyen hata")
                )
            removed.append(name)
        return tuple(removed)

    def install(self) -> tuple[str, ...]:
        if os.name != "nt":
            raise RuntimeError("Otomatik başlangıç kurulumu yalnızca Windows üzerinde destekleniyor.")

        removed = self.remove_legacy_tasks()
        command = [
            "schtasks", "/Create", "/F", "/SC", "ONLOGON", "/RL", "LIMITED",
            "/TN", TASK_NAME, "/TR", self._task_command(),
        ]
        result = self._run(command)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Görev oluşturulamadı.")
        if not self.task_points_to_current_project():
            raise RuntimeError("Görev oluşturuldu ancak güncel proje klasörünü göstermiyor.")
        return removed

    def uninstall(self) -> None:
        if os.name != "nt":
            return
        if self.task_exists(TASK_NAME):
            result = self._run(["schtasks", "/Delete", "/F", "/TN", TASK_NAME])
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or result.stdout.strip())

    @staticmethod
    def read_pid() -> int | None:
        try:
            return int(PID_FILE.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            return None

    @staticmethod
    def process_running(pid: int | None) -> bool:
        if not pid or pid <= 0:
            return False
        if os.name == "nt":
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            return result.returncode == 0 and f'"{pid}"' in result.stdout
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    @staticmethod
    def heartbeat_age() -> float | None:
        try:
            stamp = datetime.fromisoformat(HEARTBEAT_FILE.read_text(encoding="utf-8").strip())
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            return max(0.0, (datetime.now(stamp.tzinfo) - stamp).total_seconds())
        except (OSError, ValueError):
            return None

    def status(self, stale_after_seconds: float = 180.0) -> StartupStatus:
        pid = self.read_pid()
        running = self.process_running(pid)
        age = self.heartbeat_age()
        stale = running and (age is None or age > stale_after_seconds)
        return StartupStatus(
            installed=self.is_installed(),
            task_correct=self.task_points_to_current_project(),
            worker_running=running,
            pid=pid if running else None,
            heartbeat_age_seconds=age,
            stale=stale,
            legacy_tasks=self.legacy_tasks(),
        )

    def _launch_direct(self) -> None:
        flags = 0
        if os.name == "nt":
            flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        subprocess.Popen(
            [self.python_executable, str(self.project_dir / "startup_control.py"), "run-worker"],
            cwd=str(self.project_dir),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
            close_fds=os.name != "nt",
        )

    def start(self, wait_seconds: float = 8.0) -> StartupStatus:
        current = self.status()
        if current.worker_running:
            return current

        launched_by_task = False
        if os.name == "nt" and current.installed and current.task_correct:
            result = self._run(["schtasks", "/Run", "/TN", TASK_NAME])
            launched_by_task = result.returncode == 0

        if not launched_by_task:
            self._launch_direct()

        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            state = self.status()
            if state.worker_running:
                return state
            time.sleep(0.25)

        # Görev başarılı görünüp worker üretmediyse doğrudan başlatmayı bir kez dene.
        if launched_by_task:
            self._launch_direct()
            deadline = time.time() + wait_seconds
            while time.time() < deadline:
                state = self.status()
                if state.worker_running:
                    return state
                time.sleep(0.25)
        return self.status()

    def stop(self, wait_seconds: float = 4.0) -> StartupStatus:
        pid = self.read_pid()
        if os.name == "nt" and self.is_installed():
            self._run(["schtasks", "/End", "/TN", TASK_NAME])
        if pid and self.process_running(pid):
            if os.name == "nt":
                self._run(["taskkill", "/PID", str(pid), "/T", "/F"])
            else:
                os.kill(pid, 15)
        deadline = time.time() + wait_seconds
        while time.time() < deadline and self.process_running(pid):
            time.sleep(0.25)
        try:
            PID_FILE.unlink(missing_ok=True)
            HEARTBEAT_FILE.unlink(missing_ok=True)
        except OSError:
            pass
        return self.status()
