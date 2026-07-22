from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "payload"
FILES = (
    Path("engine/robot_risk_monitor.py"),
    Path("ui/portfolio_risk_page.py"),
    Path("tests/test_robot_risk_monitor_10_15d.py"),
)
BACKUP = ROOT / ".sprint_backups" / "10_15d"

for relative in FILES:
    source = PAYLOAD / relative
    target = ROOT / relative
    if not source.exists():
        raise FileNotFoundError(f"Paket dosyası bulunamadı: {source}")
    if target.exists():
        backup = BACKUP / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    print(f"Uygulandı: {relative}")

print("Sprint 10.15D başarıyla uygulandı.")
