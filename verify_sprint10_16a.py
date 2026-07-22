from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TESTS = [
    "tests/test_market_regime_engine.py",
    "tests/test_market_intelligence_10_16a.py",
    "tests/test_robot_risk_enforcement_10_15c.py",
    "tests/test_robot_risk_monitor_10_15d.py",
]


def main() -> None:
    for relative in (
        "engine/market_regime_engine.py",
        "ui/market_intelligence_page.py",
        "tests/test_market_intelligence_10_16a.py",
        "app.py",
    ):
        if not (ROOT / relative).exists():
            raise FileNotFoundError(f"Eksik dosya: {relative}")

    compile_result = subprocess.run(
        [sys.executable, "-m", "py_compile", "engine/market_regime_engine.py", "ui/market_intelligence_page.py", "app.py"],
        cwd=ROOT,
    )
    if compile_result.returncode:
        raise SystemExit(compile_result.returncode)

    result = subprocess.run([sys.executable, "-m", "pytest", "-q", *TESTS], cwd=ROOT)
    if result.returncode:
        raise SystemExit(result.returncode)
    print("Sprint 10.16A doğrulandı.")


if __name__ == "__main__":
    main()
