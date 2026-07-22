from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "payload"
BACKUP = ROOT / ".sprint_backups" / "10_16b"
FILES = [
    Path("engine/adaptive_strategy_engine.py"),
    Path("engine/robot_engine.py"),
    Path("ui/market_intelligence_page.py"),
    Path("tests/test_adaptive_strategy_engine_10_16b.py"),
    Path("tests/test_robot_adaptive_strategy_10_16b.py"),
]


def main() -> None:
    for relative in FILES:
        source = PAYLOAD / relative
        target = ROOT / relative
        backup = BACKUP / relative
        if target.exists() and not backup.exists():
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        print(f"Uygulandı: {relative}")
    print("Sprint 10.16B başarıyla uygulandı.")


if __name__ == "__main__":
    main()
