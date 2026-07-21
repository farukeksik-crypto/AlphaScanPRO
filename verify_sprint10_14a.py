from __future__ import annotations
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
commands = [
    [sys.executable, "-m", "py_compile", "engine/ai/walk_forward_lab.py", "ui/strategy_lab_page.py"],
    [sys.executable, "-m", "pytest", "tests/test_walk_forward_10_14a.py", "-q"],
]
for command in commands:
    print("Çalıştırılıyor:", " ".join(command))
    completed = subprocess.run(command, cwd=ROOT)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)
print("Sprint 10.14A doğrulandı.")
