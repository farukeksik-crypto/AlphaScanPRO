from __future__ import annotations

import json
from typing import Any

DEFAULT_ROBOT_SETTINGS: dict[str, Any] = {
    "minimum_score": 80.0,
    "minimum_confidence": 65.0,
    "minimum_probability": 65.0,
    "max_positions": 5,
    "position_size_pct": 0.20,
    "allowed_decisions": ["NET AL"],
    "allowed_risks": ["Düşük", "Orta"],
    "strategy_profile": "Default",
}


def _ensure_table(database) -> None:
    with database.connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS robot_settings (
                account_id TEXT PRIMARY KEY,
                market TEXT NOT NULL,
                minimum_score REAL NOT NULL,
                minimum_confidence REAL NOT NULL,
                minimum_probability REAL NOT NULL,
                max_positions INTEGER NOT NULL,
                position_size_pct REAL NOT NULL,
                allowed_decisions TEXT NOT NULL,
                allowed_risks TEXT NOT NULL,
                strategy_profile TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.commit()


def load_robot_settings(database, account_id: str, market: str) -> dict[str, Any]:
    _ensure_table(database)
    with database.connect() as connection:
        row = connection.execute(
            """
            SELECT minimum_score, minimum_confidence, minimum_probability,
                   max_positions, position_size_pct, allowed_decisions,
                   allowed_risks, strategy_profile
            FROM robot_settings
            WHERE account_id = ?
            """,
            (account_id,),
        ).fetchone()

    settings = dict(DEFAULT_ROBOT_SETTINGS)
    if row is None:
        return settings

    settings.update(
        {
            "minimum_score": float(row[0]),
            "minimum_confidence": float(row[1]),
            "minimum_probability": float(row[2]),
            "max_positions": int(row[3]),
            "position_size_pct": float(row[4]),
            "allowed_decisions": json.loads(row[5]),
            "allowed_risks": json.loads(row[6]),
            "strategy_profile": str(row[7] or "Default"),
        }
    )
    return settings


def save_robot_settings(
    database,
    *,
    account_id: str,
    market: str,
    minimum_score: float,
    minimum_confidence: float,
    minimum_probability: float,
    max_positions: int,
    position_size_pct: float,
    allowed_decisions,
    allowed_risks,
    strategy_profile: str,
) -> None:
    _ensure_table(database)
    with database.connect() as connection:
        connection.execute(
            """
            INSERT INTO robot_settings (
                account_id, market, minimum_score, minimum_confidence,
                minimum_probability, max_positions, position_size_pct,
                allowed_decisions, allowed_risks, strategy_profile, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(account_id) DO UPDATE SET
                market = excluded.market,
                minimum_score = excluded.minimum_score,
                minimum_confidence = excluded.minimum_confidence,
                minimum_probability = excluded.minimum_probability,
                max_positions = excluded.max_positions,
                position_size_pct = excluded.position_size_pct,
                allowed_decisions = excluded.allowed_decisions,
                allowed_risks = excluded.allowed_risks,
                strategy_profile = excluded.strategy_profile,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                account_id,
                market,
                float(minimum_score),
                float(minimum_confidence),
                float(minimum_probability),
                int(max_positions),
                float(position_size_pct),
                json.dumps(list(allowed_decisions), ensure_ascii=False),
                json.dumps(list(allowed_risks), ensure_ascii=False),
                strategy_profile.strip() or "Default",
            ),
        )
        connection.commit()
