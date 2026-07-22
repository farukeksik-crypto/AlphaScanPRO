from __future__ import annotations

from pathlib import Path
import py_compile
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
FILES = [
    ROOT / "engine" / "trade_performance_analytics.py",
    ROOT / "ui" / "robot_page.py",
    ROOT / "tests" / "test_trade_performance_analytics_10_18a.py",
]


def main() -> int:
    missing = [str(path.relative_to(ROOT)) for path in FILES if not path.exists()]
    if missing:
        print("Eksik dosyalar:", ", ".join(missing))
        return 1
    for path in FILES:
        py_compile.compile(str(path), doraise=True)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/test_trade_performance_analytics_10_18a.py", "tests/test_trade_intelligence.py"],
        cwd=ROOT,
    )
    if result.returncode != 0:
        return result.returncode
    print("Sprint 10.18A doğrulandı.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
