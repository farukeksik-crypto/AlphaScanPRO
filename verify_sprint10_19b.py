from __future__ import annotations
from pathlib import Path
import py_compile
import subprocess
import sys

def main() -> int:
    required = [
        Path("engine/universe_performance.py"),
        Path("ui/universe_manager_page.py"),
        Path("tests/test_universe_performance_10_19b.py"),
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError("Eksik dosyalar: " + ", ".join(missing))
    for path in required[:2]:
        py_compile.compile(str(path), doraise=True)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_universe_performance_10_19b.py", "tests/test_universe_manager_10_19a.py", "tests/test_background_multi_universe_10_19a.py", "-q"],
        check=False,
    )
    if result.returncode:
        raise SystemExit(result.returncode)
    print("Sprint 10.19B doğrulandı.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
