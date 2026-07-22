from __future__ import annotations

import sys

from config.settings import DATABASE_FILE
from database.db import Database
from database.robot_migrations import migrate_database_object
from engine.paper_capital_manager import PaperCapitalManager


def money(value: float) -> str:
    return f"{value:,.2f}"


def main() -> int:
    command = (sys.argv[1] if len(sys.argv) > 1 else "status").lower()
    database = Database(DATABASE_FILE)
    migrate_database_object(database)
    manager = PaperCapitalManager(database)
    if command == "apply":
        results = manager.apply_targets()
        for item in results:
            state = "YÜKSELTİLDİ" if item.changed else "ZATEN UYGUN"
            print(
                f"{item.market}: {state} · başlangıç {money(item.new_starting_balance)} "
                f"{item.currency} · nakit {money(item.new_cash_balance)} {item.currency}"
            )
        return 0
    if command == "status":
        for item in manager.status():
            print(
                f"{item['market']}: başlangıç {money(item['starting_balance'])} "
                f"{item['currency']} · nakit {money(item['balance'])} {item['currency']}"
            )
        return 0
    print("Kullanım: py -3.13 .\\capital_control.py [status|apply]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
