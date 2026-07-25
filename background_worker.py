from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import os
import signal
import sys
import time

from config.background_settings import BACKGROUND_LOG_DIR, RUNTIME_DIR, load_background_settings
from config.settings import CACHE_DIR, DATABASE_FILE, load_watchlists
from database.background_migrations import ensure_background_schema
from database.intelligence_migrations import ensure_intelligence_schema
from database.db import Database
from engine.background_orchestrator import BackgroundOrchestrator
from engine.cache_engine import CacheEngine
from engine.data_engine import DataEngine
from engine.market_scheduler import JobClock, bist_market_open, zoned_now
from engine.notification_manager import NotificationManager
from engine.universe_manager import UniverseManager

STOP_REQUESTED = False


def _stop(*_args):
    global STOP_REQUESTED
    STOP_REQUESTED = True


def _logger() -> logging.Logger:
    logger = logging.getLogger("alphascan.background")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger
    handler = RotatingFileHandler(
        BACKGROUND_LOG_DIR / "background_worker.log",
        maxBytes=5_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logger.addHandler(handler)
    logger.addHandler(logging.StreamHandler(sys.stdout))
    return logger


def _acquire_lock() -> object:
    lock_path = RUNTIME_DIR / "background_worker.lock"
    handle = open(lock_path, "a+", encoding="utf-8")
    if sys.platform == "win32":
        import msvcrt
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            handle.close()
            raise RuntimeError("Background Worker zaten çalışıyor.") from exc
    else:
        import fcntl
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise RuntimeError("Background Worker zaten çalışıyor.") from exc
    handle.seek(0)
    handle.truncate()
    handle.write(str(Path.cwd()))
    handle.flush()
    return handle


def main() -> int:
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    logger = _logger()
    lock_handle = _acquire_lock()
    pid_path = RUNTIME_DIR / "background_worker.pid"
    pid_path.write_text(str(os.getpid()), encoding="utf-8")
    settings = load_background_settings()

    database = Database(DATABASE_FILE)
    ensure_background_schema(database)
    ensure_intelligence_schema(database)
    data_engine = DataEngine(CacheEngine(CACHE_DIR))
    universe_manager = UniverseManager()
    watchlists = load_watchlists()
    watchlists["arindirma_0"] = universe_manager.get_items("arindirma_0")
    watchlists["Katılım Tüm"] = universe_manager.get_items("katilim_tum")
    watchlists["katilim_tum"] = watchlists["Katılım Tüm"]
    orchestrator = BackgroundOrchestrator(database, data_engine, watchlists, settings, logger)
    notifier = NotificationManager(database, settings, logger)

    clocks = {"bist": JobClock(), "crypto": JobClock(), "commodity": JobClock()}
    logger.info("AlphaScan Background Worker başladı.")
    if settings.notify_worker_start:
        notifier.send("WORKER_START", "AlphaScan PRO", "Arka plan tarama sistemi çalışmaya başladı.")

    try:
        while not STOP_REQUESTED:
            now = zoned_now(settings.timezone)
            heartbeat = RUNTIME_DIR / "background_worker.heartbeat"
            heartbeat.write_text(now.isoformat(timespec="seconds"), encoding="utf-8")

            if settings.crypto.enabled and clocks["crypto"].due(now, settings.crypto.interval_minutes):
                orchestrator.run_crypto()
                clocks["crypto"].mark(now)

            if settings.commodity.enabled and clocks["commodity"].due(now, settings.commodity.interval_minutes):
                orchestrator.run_commodity()
                clocks["commodity"].mark(now)

            if (
                settings.bist.enabled
                and bist_market_open(now, settings.bist_market_start, settings.bist_market_end)
                and clocks["bist"].due(now, settings.bist.interval_minutes)
            ):
                orchestrator.run_bist()
                clocks["bist"].mark(now)

            time.sleep(settings.loop_seconds)
    finally:
        logger.info("AlphaScan Background Worker durdu.")
        try:
            (RUNTIME_DIR / "background_worker.heartbeat").unlink(missing_ok=True)
            pid_path.unlink(missing_ok=True)
        except OSError:
            pass
        lock_handle.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
