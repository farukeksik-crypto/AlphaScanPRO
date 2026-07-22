from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILES = [
    ROOT / "engine" / "multi_timeframe_intelligence.py",
    ROOT / "engine" / "market_regime_engine.py",
    ROOT / "engine" / "adaptive_strategy_engine.py",
    ROOT / "engine" / "robot_engine.py",
    ROOT / "ui" / "market_intelligence_page.py",
]
TESTS = [
    "tests/test_multi_timeframe_intelligence_10_16c.py",
    "tests/test_robot_multi_timeframe_10_16c.py",
    "tests/test_market_intelligence_10_16a.py",
    "tests/test_adaptive_strategy_engine_10_16b.py",
    "tests/test_robot_adaptive_strategy_10_16b.py",
    "tests/test_portfolio_risk_manager_10_15a.py",
    "tests/test_portfolio_risk_analytics_10_15b.py",
    "tests/test_robot_risk_enforcement_10_15c.py",
    "tests/test_robot_risk_monitor_10_15d.py",
]


def main() -> None:
    missing = [str(path.relative_to(ROOT)) for path in FILES if not path.exists()]
    if missing:
        raise SystemExit("Eksik dosyalar: " + ", ".join(missing))
    subprocess.run([sys.executable, "-m", "py_compile", *map(str, FILES)], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "-m", "pytest", "-q", *TESTS], cwd=ROOT, check=True)
    print("Sprint 10.16C doğrulandı.")


if __name__ == "__main__":
    main()
