from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "payload"
BACKUP = ROOT / "backups" / f"sprint10_20b_{datetime.now():%Y%m%d_%H%M%S}"
FILES = [
    "engine/market_accounts.py",
    "engine/paper_capital_manager.py",
    "engine/background_orchestrator.py",
    "database/robot_migrations.py",
    "ui/universe_manager_page.py",
    "capital_control.py",
    "tests/test_multi_universe_accounts_10_20b.py",
]

for relative in FILES:
    source = PAYLOAD / relative
    target = ROOT / relative
    if not source.exists():
        raise FileNotFoundError(f"Paket dosyası eksik: {source}")
    if target.exists():
        backup = BACKUP / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)

from config.settings import DATABASE_FILE
from database.db import Database
from database.robot_migrations import migrate_database_object
from engine.paper_capital_manager import PaperCapitalManager

database = Database(DATABASE_FILE)
migrate_database_object(database)
PaperCapitalManager(database).apply_targets()

print("Sprint 10.20B uygulandı: BIST evrenleri için bağımsız sanal hesaplar etkin.")
print("BIST Katılım: 10,000,000 TRY")
print("Arındırma 0: 10,000,000 TRY")
print("Tüm BIST: 25,000,000 TRY")
print("Background Worker yeniden başlatılmalıdır.")
