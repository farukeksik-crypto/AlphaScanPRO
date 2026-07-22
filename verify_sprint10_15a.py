from __future__ import annotations

from pathlib import Path
import py_compile
import subprocess
import sys


def main() -> int:
    project = Path.cwd()
    targets = [
        project / "engine" / "portfolio_risk_manager.py",
        project / "tests" / "test_portfolio_risk_manager.py",
        project / "tests" / "test_portfolio_risk_manager_10_15a.py",
        project / "tests" / "test_portfolio_engine.py",
        project / "tests" / "test_risk_core.py",
    ]
    missing = [str(path) for path in targets if not path.exists()]
    if missing:
        print("HATA: Eksik dosyalar:")
        for item in missing:
            print(f"- {item}")
        return 1

    py_compile.compile(str(targets[0]), doraise=True)
    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_portfolio_risk_manager.py",
        "tests/test_portfolio_risk_manager_10_15a.py",
        "tests/test_portfolio_engine.py",
        "tests/test_risk_core.py",
        "-q",
    ]
    result = subprocess.run(command, cwd=project)
    if result.returncode != 0:
        return result.returncode

    print("Sprint 10.15A doğrulandı.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
