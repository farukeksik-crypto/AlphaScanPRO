from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "payload"
BACKUP = ROOT / ".sprint_backups" / "10_16c"
FILES = [
    Path("engine/multi_timeframe_intelligence.py"),
    Path("engine/robot_engine.py"),
    Path("ui/market_intelligence_page.py"),
    Path("tests/test_multi_timeframe_intelligence_10_16c.py"),
    Path("tests/test_robot_multi_timeframe_10_16c.py"),
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
    print("Sprint 10.16C başarıyla uygulandı.")


if __name__ == "__main__":
    main()
