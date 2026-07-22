from __future__ import annotations

import py_compile
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
required = [
    ROOT / "engine" / "fundamental_quality.py",
    ROOT / "ui" / "financial_analysis_page.py",
    ROOT / "tests" / "test_fundamental_quality_10_21a.py",
]
missing = [str(path) for path in required if not path.exists()]
if missing:
    raise SystemExit("Eksik dosyalar: " + ", ".join(missing))

for relative in ("engine/fundamental_quality.py", "ui/financial_analysis_page.py"):
    py_compile.compile(str(ROOT / relative), doraise=True)

result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/test_fundamental_quality_10_21a.py", "-q"],
    cwd=ROOT,
)
if result.returncode:
    raise SystemExit(result.returncode)
print("Sprint 10.21A doğrulandı.")
