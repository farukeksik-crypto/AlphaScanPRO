from __future__ import annotations

import py_compile
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILES = (
    ROOT / "engine" / "production_readiness.py",
    ROOT / "paper_trading_readiness.py",
    ROOT / "tests" / "test_production_readiness_10_17a.py",
)
TESTS = (
    "tests/test_production_readiness_10_17a.py",
    "tests/test_multi_timeframe_intelligence_10_16c.py",
    "tests/test_robot_multi_timeframe_10_16c.py",
    "tests/test_adaptive_strategy_engine_10_16b.py",
    "tests/test_robot_adaptive_strategy_10_16b.py",
)


def main() -> int:
    missing = [str(path.relative_to(ROOT)) for path in FILES if not path.exists()]
    if missing:
        print("Eksik dosyalar:", ", ".join(missing))
        return 1

    for path in FILES:
        py_compile.compile(str(path), doraise=True)

    command = [sys.executable, "-m", "pytest", *TESTS, "-q"]
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode:
        return result.returncode

    print("Sprint 10.17A doğrulandı.")
    print("Hazırlık raporu: py -3.13 .\\paper_trading_readiness.py")
    print("Worker zorunlu kontrol: py -3.13 .\\paper_trading_readiness.py --require-worker")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
