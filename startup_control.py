from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from config.settings import DATABASE_FILE
from database.db import Database
from engine.paper_trading_mode import PaperTradingModeManager
from engine.startup_manager import StartupManager


def _paper(enable: bool) -> None:
    PaperTradingModeManager(Database(DATABASE_FILE)).set_enabled(enable)


def _print(state, as_json: bool = False) -> None:
    payload = state.to_dict()
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print("Otomatik başlangıç:", "KURULU" if state.installed else "KURULU DEĞİL")
    print("Görev yolu:", "GÜNCEL PROJE" if state.task_correct else "HATALI / EKSİK")
    print("Worker:", "ÇALIŞIYOR" if state.worker_running else "DURDU")
    print("PID:", state.pid or "-")
    print("Heartbeat yaşı:", f"{state.heartbeat_age_seconds:.0f} sn" if state.heartbeat_age_seconds is not None else "-")
    print("Sağlık:", "BAYAT / KİLİTLİ OLABİLİR" if state.stale else "NORMAL")
    print("Eski görevler:", ", ".join(state.legacy_tasks) if state.legacy_tasks else "Yok")


def main() -> int:
    parser = argparse.ArgumentParser(description="AlphaScan PRO otomatik başlangıç yöneticisi")
    parser.add_argument("action", choices=("install", "repair", "uninstall", "start", "stop", "restart", "status", "run-worker"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    project = Path(__file__).resolve().parent
    manager = StartupManager(project)

    if args.action == "run-worker":
        os.chdir(project)
        _paper(True)
        return subprocess.call([sys.executable, str(project / "background_worker.py")], cwd=str(project))
    if args.action in {"install", "repair"}:
        _paper(True)
        removed = manager.install()
        state = manager.start()
        print("Windows otomatik başlangıç görevi güncel projeye kuruldu.")
        if removed:
            print("Kaldırılan eski görevler:", ", ".join(removed))
    elif args.action == "uninstall":
        state = manager.stop()
        manager.uninstall()
        state = manager.status()
        print("Windows otomatik başlangıç görevi kaldırıldı.")
    elif args.action == "start":
        _paper(True)
        state = manager.start()
    elif args.action == "stop":
        state = manager.stop()
    elif args.action == "restart":
        manager.stop()
        _paper(True)
        state = manager.start()
    else:
        state = manager.status()
    _print(state, args.json)
    return 0 if (args.action in {"stop", "uninstall", "status"} or state.worker_running) else 1


if __name__ == "__main__":
    raise SystemExit(main())
