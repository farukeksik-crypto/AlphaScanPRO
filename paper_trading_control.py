from __future__ import annotations

import argparse
import json

from config.settings import DATABASE_FILE
from database.db import Database
from engine.paper_trading_mode import PaperTradingModeManager, SUPPORTED_MARKETS


def main() -> int:
    parser = argparse.ArgumentParser(description="AlphaScan PRO 7/24 Paper Trading kontrolü")
    parser.add_argument("action", choices=("status", "start", "stop"))
    parser.add_argument("--market", action="append", choices=SUPPORTED_MARKETS, help="Tekrarlanabilir; boşsa tüm piyasalar")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    manager = PaperTradingModeManager(Database(DATABASE_FILE))
    if args.action == "start":
        status = manager.set_enabled(True, args.market)
    elif args.action == "stop":
        status = manager.set_enabled(False, args.market)
    else:
        status = manager.status()

    payload = status.to_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("Paper Trading:", "TAM AKTİF" if status.fully_enabled else "KISMİ AKTİF" if status.enabled else "KAPALI")
        print("Aktif piyasalar:", ", ".join(status.enabled_markets) or "Yok")
        print("Kapalı piyasalar:", ", ".join(status.disabled_markets) or "Yok")
        print("Worker taramaları:", status.worker_jobs)
        print("Worker robot bayrakları:", status.worker_robot_flags)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
