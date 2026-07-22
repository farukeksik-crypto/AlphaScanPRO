from __future__ import annotations

import shutil
from pathlib import Path

SPRINT = "10_16a"
ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "payload"
BACKUP = ROOT / ".sprint_backups" / SPRINT
FILES = (
    Path("engine/market_regime_engine.py"),
    Path("ui/market_intelligence_page.py"),
    Path("tests/test_market_intelligence_10_16a.py"),
    Path("app.py"),
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
            if not backup.exists():
                shutil.copy2(target, backup)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        print(f"Uygulandı: {relative}")
    print("Sprint 10.16A başarıyla uygulandı.")


if __name__ == "__main__":
    main()
