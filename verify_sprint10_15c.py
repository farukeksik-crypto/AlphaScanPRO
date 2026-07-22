from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TESTS = [
    "tests/test_robot_risk_enforcement_10_15c.py",
    "tests/test_portfolio_risk_manager_10_15a.py",
    "tests/test_portfolio_risk_analytics_10_15b.py",
]


def main() -> None:
    for relative in (
        "engine/robot_risk_enforcement.py",
        "engine/robot_engine.py",
        "tests/test_robot_risk_enforcement_10_15c.py",
    ):
        if not (ROOT / relative).exists():
            raise FileNotFoundError(f"Eksik dosya: {relative}")
    command = [sys.executable, "-m", "pytest", *TESTS, "-q"]
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode:
        raise SystemExit(result.returncode)
    print("Sprint 10.15C doğrulandı.")


if __name__ == "__main__":
    main()
