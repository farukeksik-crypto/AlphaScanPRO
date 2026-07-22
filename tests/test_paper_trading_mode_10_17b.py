from pathlib import Path

from config.background_settings import BackgroundSettings, save_background_settings
from database.db import Database
from engine.paper_trading_mode import PaperTradingModeManager


def test_enable_all_markets(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    config = tmp_path / "background.json"
    save_background_settings(BackgroundSettings(), config)
    manager = PaperTradingModeManager(db, config)

    status = manager.set_enabled(True)

    assert status.fully_enabled is True
    assert set(status.enabled_markets) == {"BIST", "KRIPTO", "EMTIA"}
    assert all(status.worker_jobs.values())
    assert all(status.worker_robot_flags.values())


def test_stop_only_crypto(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    config = tmp_path / "background.json"
    save_background_settings(BackgroundSettings(), config)
    manager = PaperTradingModeManager(db, config)
    manager.set_enabled(True)

    status = manager.set_enabled(False, ["KRIPTO"])

    assert "KRIPTO" in status.disabled_markets
    assert "BIST" in status.enabled_markets
    assert status.worker_jobs["KRIPTO"] is False
    assert status.worker_robot_flags["KRIPTO"] is False


def test_event_is_recorded(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    config = tmp_path / "background.json"
    save_background_settings(BackgroundSettings(), config)
    manager = PaperTradingModeManager(db, config)
    manager.set_enabled(True, ["KRIPTO"])

    with db.connect() as connection:
        row = connection.execute(
            "SELECT event_type, message FROM system_events ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row[0] == "PAPER_TRADING_ENABLED"
    assert "KRIPTO" in row[1]
