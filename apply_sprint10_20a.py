from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "payload"
BACKUP = ROOT / "backups" / f"sprint10_20a_{datetime.now():%Y%m%d_%H%M%S}"
FILES = [
    "engine/market_accounts.py",
    "engine/paper_capital_manager.py",
    "capital_control.py",
    "tests/test_paper_capital_manager_10_20a.py",
]

for relative in FILES:
    source = PAYLOAD / relative
    target = ROOT / relative
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
results = PaperCapitalManager(database).apply_targets()
print("Sprint 10.20A uygulandı: yüksek kapasiteli sanal sermaye profili etkin.")
for item in results:
    print(f"{item.market}: {item.new_starting_balance:,.2f} {item.currency} · eklenen sermaye {item.added_capital:,.2f}")
