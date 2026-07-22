from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
required = [
    ROOT / "engine" / "market_accounts.py",
    ROOT / "engine" / "paper_capital_manager.py",
    ROOT / "engine" / "background_orchestrator.py",
    ROOT / "database" / "robot_migrations.py",
    ROOT / "ui" / "universe_manager_page.py",
    ROOT / "capital_control.py",
    ROOT / "tests" / "test_multi_universe_accounts_10_20b.py",
]
missing = [str(path) for path in required if not path.exists()]
if missing:
    raise SystemExit("Eksik dosyalar: " + ", ".join(missing))

result = subprocess.run(
    [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_multi_universe_accounts_10_20b.py",
        "tests/test_paper_capital_manager_10_20a.py",
        "tests/test_background_multi_universe_10_19a.py",
        "tests/test_universe_performance_10_19b.py",
        "-q",
    ],
    cwd=ROOT,
)
if result.returncode:
    raise SystemExit(result.returncode)
print("Sprint 10.20B doğrulandı.")
