from __future__ import annotations
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "payload"

for relative in [
    Path("engine/ai/walk_forward_lab.py"),
    Path("ui/strategy_lab_page.py"),
    Path("tests/test_walk_forward_10_14a.py"),
]:
    source = PAYLOAD / relative
    target = ROOT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and relative.suffix == ".py":
        backup = target.with_suffix(target.suffix + ".sprint10_14a.bak")
        if not backup.exists():
            shutil.copy2(target, backup)
    shutil.copy2(source, target)
    print(f"Güncellendi: {relative}")

print("Sprint 10.14A uygulandı.")
