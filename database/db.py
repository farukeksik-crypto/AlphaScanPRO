from __future__ import annotations

import sqlite3
from pathlib import Path


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self):
        return sqlite3.connect(self.path)

    def initialize(self):
        with self.connect() as connection:

            # Sistem olayları
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS system_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL
                )
                """
            )

            # Robot durumu
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS robot_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    enabled INTEGER NOT NULL DEFAULT 0,
                    balance REAL NOT NULL DEFAULT 1000000,
                    daily_profit REAL NOT NULL DEFAULT 0,
                    total_profit REAL NOT NULL DEFAULT 0,
                    updated_at TEXT
                )
                """
            )

            # Açık pozisyonlar
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_price REAL,
                    target1 REAL,
                    target2 REAL,
                    opened_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'OPEN'
                )
                """
            )

            # İşlem geçmişi
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS trade_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    price REAL NOT NULL,
                    commission REAL DEFAULT 0,
                    profit REAL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )

            # Robot durum kaydı (ilk açılışta)
            connection.execute(
                """
                INSERT OR IGNORE INTO robot_state (
                    id,
                    enabled,
                    balance,
                    daily_profit,
                    total_profit,
                    updated_at
                )
                VALUES (
                    1,
                    0,
                    1000000,
                    0,
                    0,
                    datetime('now')
                )
                """
            )

            connection.commit()

    def health_check(self) -> bool:
        try:
            with self.connect() as connection:
                connection.execute("SELECT 1")
            return True
        except Exception:
            return False