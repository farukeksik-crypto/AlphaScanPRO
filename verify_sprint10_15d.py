from __future__ import annotations

import py_compile
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for relative in (
    "engine/robot_risk_monitor.py",
    "ui/portfolio_risk_page.py",
    "tests/test_robot_risk_monitor_10_15d.py",
):
    py_compile.compile(str(ROOT / relative), doraise=True)

command = [
    sys.executable, "-m", "pytest", "-q",
    "tests/test_robot_risk_monitor_10_15d.py",
    "tests/test_robot_risk_enforcement_10_15c.py",
    "tests/test_portfolio_risk_manager_10_15a.py",
    "tests/test_portfolio_risk_analytics_10_15b.py",
]
result = subprocess.run(command, cwd=ROOT)
if result.returncode:
    raise SystemExit(result.returncode)
print("Sprint 10.15D doğrulandı.")
