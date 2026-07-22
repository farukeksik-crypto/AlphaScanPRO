from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    required = [
        ROOT / "engine" / "portfolio_risk_analytics.py",
        ROOT / "ui" / "portfolio_risk_page.py",
        ROOT / "tests" / "test_portfolio_risk_analytics_10_15b.py",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        print("Eksik dosyalar:", ", ".join(missing))
        return 1
    app_text = (ROOT / "app.py").read_text(encoding="utf-8")
    for token in ("render_portfolio_risk", '"Portföy Risk Merkezi"'):
        if token not in app_text:
            print(f"app.py entegrasyonu eksik: {token}")
            return 1
    tests = [
        "tests/test_portfolio_risk_analytics_10_15b.py",
        "tests/test_portfolio_risk_manager_10_15a.py",
        "tests/test_portfolio_risk_manager.py",
    ]
    result = subprocess.run([sys.executable, "-m", "pytest", *tests, "-q"], cwd=ROOT)
    if result.returncode:
        return result.returncode
    print("Sprint 10.15B doğrulandı.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
