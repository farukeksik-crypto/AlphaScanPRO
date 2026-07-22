from __future__ import annotations
from pathlib import Path
import py_compile
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
FILES = [
    ROOT / "engine" / "position_lifecycle_analytics.py",
    ROOT / "ui" / "robot_page.py",
    ROOT / "tests" / "test_position_lifecycle_analytics_10_18b.py",
]

def main() -> int:
    missing = [str(p.relative_to(ROOT)) for p in FILES if not p.exists()]
    if missing:
        print("Eksik dosyalar:", ", ".join(missing))
        return 1
    for path in FILES:
        py_compile.compile(str(path), doraise=True)
    result = subprocess.run([
        sys.executable, "-m", "pytest", "-q",
        "tests/test_position_lifecycle_analytics_10_18b.py",
        "tests/test_trade_performance_analytics_10_18a.py",
    ], cwd=ROOT)
    if result.returncode:
        return result.returncode
    print("Sprint 10.18B doğrulandı.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
