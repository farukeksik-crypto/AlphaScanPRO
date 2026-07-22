from __future__ import annotations

import shutil
from pathlib import Path

SPRINT = "10_15c"
ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "payload"
BACKUP = ROOT / ".sprint_backups" / SPRINT
FILES = (
    Path("engine/robot_engine.py"),
    Path("engine/robot_risk_enforcement.py"),
    Path("tests/test_robot_risk_enforcement_10_15c.py"),
)


def main() -> None:
    for relative in FILES:
        source = PAYLOAD / relative
        target = ROOT / relative
        if not source.exists():
            raise FileNotFoundError(f"Payload bulunamadı: {source}")
        if target.exists():
            backup = BACKUP / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        print(f"Uygulandı: {relative}")
    print("Sprint 10.15C başarıyla uygulandı.")


if __name__ == "__main__":
    main()
