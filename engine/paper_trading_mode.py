from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from config.background_settings import (
    BACKGROUND_CONFIG_FILE,
    load_background_settings,
    save_background_settings,
)
from database.robot_migrations import migrate_database_object
from engine.market_accounts import account_for_market, normalize_market

SUPPORTED_MARKETS = ("BIST", "KRIPTO", "EMTIA")


@dataclass(frozen=True)
class PaperTradingStatus:
    enabled_markets: tuple[str, ...]
    disabled_markets: tuple[str, ...]
    worker_jobs: dict[str, bool]
    worker_robot_flags: dict[str, bool]

    @property
    def enabled(self) -> bool:
        return bool(self.enabled_markets)

    @property
    def fully_enabled(self) -> bool:
        return len(self.enabled_markets) == len(SUPPORTED_MARKETS) and all(self.worker_jobs.values()) and all(self.worker_robot_flags.values())

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "fully_enabled": self.fully_enabled,
            "enabled_markets": list(self.enabled_markets),
            "disabled_markets": list(self.disabled_markets),
            "worker_jobs": dict(self.worker_jobs),
            "worker_robot_flags": dict(self.worker_robot_flags),
        }


class PaperTradingModeManager:
    """7/24 sanal işlem modunu tek noktadan açıp kapatır.

    Bu sınıf gerçek emir göndermez. Yalnızca robot hesaplarını ve Background
    Worker tarama/robot bayraklarını birlikte yönetir.
    """

    def __init__(self, database, config_path: str | Path = BACKGROUND_CONFIG_FILE):
        self.database = database
        self.config_path = Path(config_path)
        migrate_database_object(database)

    @staticmethod
    def _markets(markets: Iterable[str] | None) -> tuple[str, ...]:
        raw = tuple(markets or SUPPORTED_MARKETS)
        normalized = tuple(dict.fromkeys(normalize_market(item) for item in raw))
        invalid = [item for item in normalized if item not in SUPPORTED_MARKETS]
        if invalid:
            raise ValueError(f"Desteklenmeyen piyasa: {', '.join(invalid)}")
        return normalized

    def set_enabled(self, enabled: bool, markets: Iterable[str] | None = None) -> PaperTradingStatus:
        selected = self._markets(markets)
        now = datetime.now().isoformat(timespec="seconds")
        with self.database.connect() as connection:
            for market in selected:
                if market == "BIST":
                    connection.execute(
                        "UPDATE robot_accounts SET enabled = ?, updated_at = ? WHERE market = 'BIST'",
                        (int(enabled), now),
                    )
                else:
                    account = account_for_market(market)
                    connection.execute(
                        "UPDATE robot_accounts SET enabled = ?, updated_at = ? WHERE account_id = ?",
                        (int(enabled), now, account["account_id"]),
                    )
            connection.commit()

        settings = load_background_settings(self.config_path)
        mapping = {"BIST": settings.bist, "KRIPTO": settings.crypto, "EMTIA": settings.commodity}
        for market in selected:
            mapping[market].enabled = bool(enabled)
            mapping[market].robot_enabled = bool(enabled)
        save_background_settings(settings, self.config_path)

        self._record_event("PAPER_TRADING_ENABLED" if enabled else "PAPER_TRADING_DISABLED", selected)
        return self.status()

    def status(self) -> PaperTradingStatus:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT market, enabled FROM robot_accounts ORDER BY market"
            ).fetchall()
        account_state: dict[str, bool] = {}
        for market_value, enabled_value in rows:
            market = normalize_market(market_value)
            account_state[market] = account_state.get(market, False) or bool(enabled_value)
        enabled = tuple(m for m in SUPPORTED_MARKETS if account_state.get(m, False))
        disabled = tuple(m for m in SUPPORTED_MARKETS if not account_state.get(m, False))

        settings = load_background_settings(self.config_path)
        jobs = {"BIST": settings.bist, "KRIPTO": settings.crypto, "EMTIA": settings.commodity}
        return PaperTradingStatus(
            enabled_markets=enabled,
            disabled_markets=disabled,
            worker_jobs={market: bool(job.enabled) for market, job in jobs.items()},
            worker_robot_flags={market: bool(job.robot_enabled) for market, job in jobs.items()},
        )

    def _record_event(self, event_type: str, markets: tuple[str, ...]) -> None:
        message = f"7/24 paper trading: {', '.join(markets)}"
        with self.database.connect() as connection:
            connection.execute(
                "INSERT INTO system_events(created_at, event_type, message) VALUES (?, ?, ?)",
                (datetime.now().isoformat(timespec="seconds"), event_type, message),
            )
            connection.commit()
