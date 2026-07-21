from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

POSITION_COLUMNS = {
    "market": "TEXT",
    "universe": "TEXT",
    "technical_score": "REAL",
    "confidence_score": "REAL",
    "confidence_label": "TEXT",
    "decision": "TEXT",
    "entry_reason": "TEXT",
    "strategy_profile": "TEXT",
    "account_id": "TEXT",
    "currency": "TEXT",
    "highest_price": "REAL",
    "lowest_price": "REAL",
    "break_even_active": "INTEGER NOT NULL DEFAULT 0",
    "trailing_active": "INTEGER NOT NULL DEFAULT 0",
    "target1_completed": "INTEGER NOT NULL DEFAULT 0",
    "initial_quantity": "REAL",
}

TRADE_HISTORY_COLUMNS = {
    "market": "TEXT",
    "universe": "TEXT",
    "technical_score": "REAL",
    "confidence_score": "REAL",
    "confidence_label": "TEXT",
    "decision": "TEXT",
    "reason": "TEXT",
    "strategy_profile": "TEXT",
    "position_id": "INTEGER",
    "account_id": "TEXT",
    "currency": "TEXT",
    "entry_price": "REAL",
    "exit_price": "REAL",
    "profit_pct": "REAL",
    "holding_minutes": "REAL",
    "mfe_pct": "REAL",
    "mae_pct": "REAL",
    "risk_pct": "REAL",
    "reward_pct": "REAL",
    "risk_reward": "REAL",
    "entry_efficiency": "REAL",
    "exit_efficiency": "REAL",
    "trade_quality_score": "REAL",
    "trade_grade": "TEXT",
}

ACCOUNT_DEFAULTS = (
    ("bist_main", "BIST", "TRY", 1_000_000.0),
    ("crypto_main", "KRIPTO", "USDT", 100_000.0),
    ("commodity_main", "EMTIA", "USD", 100_000.0),
)


def _existing_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _add_missing_columns(connection: sqlite3.Connection, table_name: str, columns: dict[str, str]) -> list[str]:
    existing = _existing_columns(connection, table_name)
    added: list[str] = []
    for name, kind in columns.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {name} {kind}")
            added.append(name)
    return added


def _ensure_accounts(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS robot_accounts (
            account_id TEXT PRIMARY KEY,
            market TEXT NOT NULL UNIQUE,
            currency TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 0,
            starting_balance REAL NOT NULL,
            balance REAL NOT NULL,
            daily_profit REAL NOT NULL DEFAULT 0,
            total_profit REAL NOT NULL DEFAULT 0,
            updated_at TEXT
        )
        """
    )

    old = connection.execute(
        "SELECT enabled, balance, daily_profit, total_profit, updated_at FROM robot_state WHERE id=1"
    ).fetchone()
    old_values = old or (0, 1_000_000.0, 0.0, 0.0, None)

    for account_id, market, currency, starting in ACCOUNT_DEFAULTS:
        if market == "BIST":
            values = (account_id, market, currency, int(old_values[0]), starting, float(old_values[1]), float(old_values[2]), float(old_values[3]), old_values[4])
        else:
            values = (account_id, market, currency, 0, starting, starting, 0.0, 0.0, None)
        connection.execute(
            """
            INSERT OR IGNORE INTO robot_accounts(
                account_id, market, currency, enabled, starting_balance,
                balance, daily_profit, total_profit, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )

    # Eski kayıtları güvenli varsayımla piyasalara dağıt.
    connection.execute(
        """
        UPDATE positions
        SET market = CASE
            WHEN UPPER(COALESCE(market,'')) LIKE 'KR%PTO%' OR UPPER(COALESCE(market,''))='CRYPTO' THEN 'KRIPTO'
            WHEN UPPER(COALESCE(market,'')) LIKE 'EMT%A%' OR UPPER(COALESCE(market,''))='COMMODITY' THEN 'EMTIA'
            ELSE 'BIST' END
        WHERE account_id IS NULL OR account_id=''
        """
    )
    connection.execute(
        """
        UPDATE positions SET
          account_id = CASE market WHEN 'KRIPTO' THEN 'crypto_main' WHEN 'EMTIA' THEN 'commodity_main' ELSE 'bist_main' END,
          currency = CASE market WHEN 'KRIPTO' THEN 'USDT' WHEN 'EMTIA' THEN 'USD' ELSE 'TRY' END
        WHERE account_id IS NULL OR account_id=''
        """
    )
    connection.execute(
        """
        UPDATE trade_history
        SET market = CASE
            WHEN UPPER(COALESCE(market,'')) LIKE 'KR%PTO%' OR UPPER(COALESCE(market,''))='CRYPTO' THEN 'KRIPTO'
            WHEN UPPER(COALESCE(market,'')) LIKE 'EMT%A%' OR UPPER(COALESCE(market,''))='COMMODITY' THEN 'EMTIA'
            ELSE 'BIST' END
        WHERE account_id IS NULL OR account_id=''
        """
    )
    connection.execute(
        """
        UPDATE trade_history SET
          account_id = CASE market WHEN 'KRIPTO' THEN 'crypto_main' WHEN 'EMTIA' THEN 'commodity_main' ELSE 'bist_main' END,
          currency = CASE market WHEN 'KRIPTO' THEN 'USDT' WHEN 'EMTIA' THEN 'USD' ELSE 'TRY' END
        WHERE account_id IS NULL OR account_id=''
        """
    )


def _migrate(connection: sqlite3.Connection) -> dict[str, list[str]]:
    p = _add_missing_columns(connection, "positions", POSITION_COLUMNS)
    h = _add_missing_columns(connection, "trade_history", TRADE_HISTORY_COLUMNS)
    _ensure_accounts(connection)
    connection.commit()
    return {"positions": p, "trade_history": h}


def migrate_robot_database(database_path: str | Path) -> dict[str, list[str]]:
    path = Path(database_path)
    if not path.exists():
        raise FileNotFoundError(f"Veritabanı bulunamadı: {path}")
    with sqlite3.connect(path) as connection:
        return _migrate(connection)


def migrate_database_object(database) -> dict[str, list[str]]:
    with database.connect() as connection:
        return _migrate(connection)


def ensure_columns(connection: sqlite3.Connection, table_name: str, columns: Iterable[tuple[str, str]]) -> list[str]:
    return _add_missing_columns(connection, table_name, dict(columns))
