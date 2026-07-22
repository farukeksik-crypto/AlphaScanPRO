from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
required = [
    ROOT / "engine" / "paper_trading_mode.py",
    ROOT / "paper_trading_control.py",
    ROOT / "tests" / "test_paper_trading_mode_10_17b.py",
]
missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
if missing:
    raise SystemExit("Eksik dosyalar: " + ", ".join(missing))

cmd = [sys.executable, "-m", "pytest", "-q", "tests/test_paper_trading_mode_10_17b.py"]
result = subprocess.run(cmd, cwd=ROOT)
if result.returncode:
    raise SystemExit(result.returncode)
print("Sprint 10.17B doğrulandı.")
