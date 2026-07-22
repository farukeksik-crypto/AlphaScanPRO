from __future__ import annotations

import importlib.util
import json
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Iterable, Sequence


class CheckStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True)
class ReadinessCheck:
    name: str
    status: CheckStatus
    message: str
    details: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ReadinessReport:
    generated_at: str
    verdict: str
    checks: tuple[ReadinessCheck, ...]

    @property
    def passed(self) -> int:
        return sum(item.status is CheckStatus.PASS for item in self.checks)

    @property
    def warnings(self) -> int:
        return sum(item.status is CheckStatus.WARN for item in self.checks)

    @property
    def failed(self) -> int:
        return sum(item.status is CheckStatus.FAIL for item in self.checks)

    @property
    def ready(self) -> bool:
        return self.failed == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at,
            "verdict": self.verdict,
            "ready": self.ready,
            "passed": self.passed,
            "warnings": self.warnings,
            "failed": self.failed,
            "checks": [
                {**asdict(item), "status": item.status.value}
                for item in self.checks
            ],
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


@dataclass(frozen=True)
class WatchdogSnapshot:
    status: CheckStatus
    message: str
    heartbeat_path: str
    age_seconds: float | None


class WorkerWatchdog:
    def __init__(self, heartbeat_path: str | Path, *, stale_after_seconds: int = 180):
        self.heartbeat_path = Path(heartbeat_path)
        self.stale_after_seconds = max(1, int(stale_after_seconds))

    def inspect(self, *, now: datetime | None = None, required: bool = False) -> WatchdogSnapshot:
        now = now or datetime.now(timezone.utc)
        if not self.heartbeat_path.exists():
            status = CheckStatus.FAIL if required else CheckStatus.WARN
            return WatchdogSnapshot(status, "Worker heartbeat dosyası bulunamadı.", str(self.heartbeat_path), None)

        try:
            raw = self.heartbeat_path.read_text(encoding="utf-8").strip()
            stamp = datetime.fromisoformat(raw)
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            age = max(0.0, (now.astimezone(timezone.utc) - stamp.astimezone(timezone.utc)).total_seconds())
        except (OSError, ValueError) as exc:
            return WatchdogSnapshot(CheckStatus.FAIL, f"Heartbeat okunamadı: {exc}", str(self.heartbeat_path), None)

        if age > self.stale_after_seconds:
            return WatchdogSnapshot(CheckStatus.FAIL, f"Worker heartbeat eski ({age:.0f} sn).", str(self.heartbeat_path), age)
        return WatchdogSnapshot(CheckStatus.PASS, f"Worker aktif; heartbeat yaşı {age:.0f} sn.", str(self.heartbeat_path), age)


class ProductionReadinessChecker:
    DEFAULT_REQUIRED_MODULES = (
        "streamlit", "pandas", "plotly", "ccxt", "yfinance",
    )
    CORE_PROJECT_MODULES = (
        "engine.robot_engine",
        "engine.portfolio_risk_manager",
        "engine.market_regime_engine",
        "engine.multi_timeframe_intelligence",
        "engine.adaptive_strategy_engine",
        "engine.trade_journal_pro",
    )
    REQUIRED_TABLES = (
        "robot_state", "positions", "trade_history", "system_events",
    )

    def __init__(
        self,
        base_dir: str | Path,
        *,
        database_path: str | Path | None = None,
        heartbeat_path: str | Path | None = None,
        required_modules: Sequence[str] | None = None,
        min_free_gb: float = 0.25,
        stale_after_seconds: int = 180,
    ):
        self.base_dir = Path(base_dir).resolve()
        self.database_path = Path(database_path) if database_path else self.base_dir / "database" / "alphascan.db"
        self.heartbeat_path = Path(heartbeat_path) if heartbeat_path else self.base_dir / "runtime" / "background_worker.heartbeat"
        self.required_modules = tuple(self.DEFAULT_REQUIRED_MODULES if required_modules is None else required_modules)
        self.min_free_gb = float(min_free_gb)
        self.stale_after_seconds = int(stale_after_seconds)

    def run(self, *, require_worker: bool = False) -> ReadinessReport:
        checks: list[ReadinessCheck] = []
        checks.append(self._check_python())
        checks.append(self._check_dependencies())
        checks.append(self._check_core_modules())
        checks.append(self._check_writable_paths())
        checks.append(self._check_database())
        checks.append(self._check_disk())
        checks.append(self._check_worker(require_worker=require_worker))
        checks.append(self._check_git_hygiene())

        failed = any(item.status is CheckStatus.FAIL for item in checks)
        warned = any(item.status is CheckStatus.WARN for item in checks)
        verdict = "NOT_READY" if failed else ("READY_WITH_WARNINGS" if warned else "READY")
        return ReadinessReport(
            generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            verdict=verdict,
            checks=tuple(checks),
        )

    def _check_python(self) -> ReadinessCheck:
        version = sys.version_info
        if version < (3, 11):
            return ReadinessCheck("Python", CheckStatus.FAIL, f"Python {version.major}.{version.minor} desteklenmiyor; en az 3.11 gerekli.")
        return ReadinessCheck("Python", CheckStatus.PASS, f"Python {version.major}.{version.minor}.{version.micro} uygun.")

    def _check_dependencies(self) -> ReadinessCheck:
        missing = [name for name in self.required_modules if importlib.util.find_spec(name) is None]
        if missing:
            return ReadinessCheck("Bağımlılıklar", CheckStatus.FAIL, "Eksik Python paketleri var.", {"missing": missing})
        return ReadinessCheck("Bağımlılıklar", CheckStatus.PASS, "Zorunlu Python paketleri bulundu.", {"modules": list(self.required_modules)})

    def _check_core_modules(self) -> ReadinessCheck:
        missing = [name for name in self.CORE_PROJECT_MODULES if importlib.util.find_spec(name) is None]
        if missing:
            return ReadinessCheck("Çekirdek modüller", CheckStatus.FAIL, "Çekirdek proje modülleri eksik.", {"missing": missing})
        return ReadinessCheck("Çekirdek modüller", CheckStatus.PASS, "Robot, risk ve market intelligence modülleri erişilebilir.")

    def _check_writable_paths(self) -> ReadinessCheck:
        paths = [self.base_dir / name for name in ("cache", "logs", "runtime", "database")]
        failed: list[str] = []
        for path in paths:
            try:
                path.mkdir(parents=True, exist_ok=True)
                probe = path / ".alphascan_write_test"
                probe.write_text("ok", encoding="utf-8")
                probe.unlink()
            except OSError:
                failed.append(str(path))
        if failed:
            return ReadinessCheck("Yazma izinleri", CheckStatus.FAIL, "Bazı çalışma klasörlerine yazılamıyor.", {"paths": failed})
        return ReadinessCheck("Yazma izinleri", CheckStatus.PASS, "Cache, log, runtime ve database klasörleri yazılabilir.")

    def _check_database(self) -> ReadinessCheck:
        if not self.database_path.exists():
            return ReadinessCheck("Veritabanı", CheckStatus.FAIL, "AlphaScan veritabanı bulunamadı.", {"path": str(self.database_path)})
        try:
            with sqlite3.connect(self.database_path) as connection:
                connection.execute("SELECT 1")
                rows = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            tables = {str(row[0]) for row in rows}
        except sqlite3.Error as exc:
            return ReadinessCheck("Veritabanı", CheckStatus.FAIL, f"SQLite sağlık kontrolü başarısız: {exc}")
        missing = sorted(set(self.REQUIRED_TABLES) - tables)
        if missing:
            return ReadinessCheck("Veritabanı", CheckStatus.FAIL, "Zorunlu tablolar eksik.", {"missing_tables": missing})
        return ReadinessCheck("Veritabanı", CheckStatus.PASS, "SQLite erişilebilir ve temel şema hazır.", {"table_count": len(tables)})

    def _check_disk(self) -> ReadinessCheck:
        usage = shutil.disk_usage(self.base_dir)
        free_gb = usage.free / (1024 ** 3)
        if free_gb < self.min_free_gb:
            return ReadinessCheck("Disk alanı", CheckStatus.FAIL, f"Boş disk alanı düşük: {free_gb:.2f} GB.")
        status = CheckStatus.WARN if free_gb < max(1.0, self.min_free_gb * 2) else CheckStatus.PASS
        return ReadinessCheck("Disk alanı", status, f"Boş disk alanı: {free_gb:.2f} GB.")

    def _check_worker(self, *, require_worker: bool) -> ReadinessCheck:
        snapshot = WorkerWatchdog(self.heartbeat_path, stale_after_seconds=self.stale_after_seconds).inspect(required=require_worker)
        return ReadinessCheck("Background Worker", snapshot.status, snapshot.message, {"heartbeat": snapshot.heartbeat_path, "age_seconds": snapshot.age_seconds})

    def _check_git_hygiene(self) -> ReadinessCheck:
        git_dir = self.base_dir / ".git"
        if not git_dir.exists():
            return ReadinessCheck("Git hijyeni", CheckStatus.WARN, "Git deposu bulunamadı; yedek/payload takibi kontrol edilemedi.")
        try:
            result = subprocess.run(
                ["git", "ls-files", ".sprint_backups", "payload"],
                cwd=self.base_dir,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return ReadinessCheck("Git hijyeni", CheckStatus.WARN, f"Git takibi kontrol edilemedi: {exc}")
        tracked = [line for line in result.stdout.splitlines() if line.strip()]
        if tracked:
            return ReadinessCheck(
                "Git hijyeni",
                CheckStatus.WARN,
                "Sprint yedekleri veya payload dosyaları Git tarafından izleniyor; repo büyüyebilir.",
                {"tracked_count": len(tracked), "sample": tracked[:10]},
            )
        return ReadinessCheck("Git hijyeni", CheckStatus.PASS, "Geçici sprint klasörleri Git tarafından izlenmiyor.")


def format_text_report(report: ReadinessReport) -> str:
    lines = [
        "AlphaScan PRO - Paper Trading Readiness",
        f"Karar: {report.verdict}",
        f"PASS={report.passed} WARN={report.warnings} FAIL={report.failed}",
        "",
    ]
    for item in report.checks:
        lines.append(f"[{item.status.value}] {item.name}: {item.message}")
    return "\n".join(lines)
