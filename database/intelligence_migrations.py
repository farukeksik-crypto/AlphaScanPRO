from __future__ import annotations


def ensure_intelligence_schema(database) -> None:
    """Robot Intelligence veri katmanını geriye uyumlu biçimde oluşturur."""
    with database.connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS intelligence_decision_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                market TEXT NOT NULL,
                universe TEXT NOT NULL,
                symbol TEXT NOT NULL,
                decision TEXT,
                score REAL NOT NULL DEFAULT 0,
                confidence REAL NOT NULL DEFAULT 0,
                probability REAL NOT NULL DEFAULT 0,
                risk_level TEXT,
                accepted INTEGER NOT NULL DEFAULT 0,
                reject_reasons TEXT NOT NULL DEFAULT '[]',
                trace_payload TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS intelligence_learning_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                market TEXT NOT NULL,
                universe TEXT NOT NULL,
                symbol TEXT NOT NULL,
                trade_id TEXT,
                payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                attempts INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                processed_at TEXT,
                error_message TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS intelligence_trade_snapshots (
                trade_id TEXT PRIMARY KEY,
                position_id INTEGER,
                account_id TEXT,
                market TEXT NOT NULL,
                universe TEXT NOT NULL,
                symbol TEXT NOT NULL,
                status TEXT NOT NULL,
                snapshot_payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_intelligence_events_run ON intelligence_decision_events(run_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_intelligence_events_market_created ON intelligence_decision_events(market, created_at DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_learning_queue_status_created ON intelligence_learning_queue(status, created_at)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_snapshots_symbol_status ON intelligence_trade_snapshots(symbol, status)"
        )
        connection.commit()
