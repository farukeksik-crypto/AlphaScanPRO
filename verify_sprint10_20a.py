from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
required = [
    ROOT / "engine" / "paper_capital_manager.py",
    ROOT / "capital_control.py",
    ROOT / "tests" / "test_paper_capital_manager_10_20a.py",
]
missing = [str(path) for path in required if not path.exists()]
if missing:
    raise SystemExit("Eksik dosyalar: " + ", ".join(missing))

result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/test_paper_capital_manager_10_20a.py", "-q"],
    cwd=ROOT,
)
if result.returncode:
    raise SystemExit(result.returncode)
print("Sprint 10.20A doğrulandı.")
