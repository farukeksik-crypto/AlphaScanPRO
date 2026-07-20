from __future__ import annotations


def ensure_background_schema(database) -> None:
    with database.connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS background_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                market TEXT NOT NULL,
                universe TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                scanned_count INTEGER NOT NULL DEFAULT 0,
                failure_count INTEGER NOT NULL DEFAULT 0,
                action_count INTEGER NOT NULL DEFAULT 0,
                error_message TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS background_scan_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                market TEXT NOT NULL,
                universe TEXT NOT NULL,
                symbol TEXT NOT NULL,
                name TEXT,
                decision TEXT,
                score REAL,
                price REAL,
                stop_price REAL,
                target1 REAL,
                target2 REAL,
                confidence REAL,
                confidence_label TEXT,
                risk_level TEXT,
                probability REAL,
                reason TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES background_runs(id)
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_background_results_market_created
            ON background_scan_results(market, created_at DESC)
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS background_state (
                job_name TEXT PRIMARY KEY,
                last_started_at TEXT,
                last_finished_at TEXT,
                last_status TEXT,
                last_message TEXT,
                next_due_at TEXT
            )
            """
        )
        connection.commit()
