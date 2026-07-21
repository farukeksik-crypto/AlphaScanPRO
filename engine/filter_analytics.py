from __future__ import annotations

import json
from datetime import datetime
from typing import Any


class FilterAnalytics:
    """
    Robotun değerlendirdiği tarama sonuçlarını ve reddetme nedenlerini
    SQLite veritabanına kaydeder.

    Bu sınıf işlem açma kurallarını değiştirmez.
    Yalnızca analiz verisi toplar.
    """

    def __init__(self, database, logger=None) -> None:
        self.database = database
        self.logger = logger
        self._ensure_table()

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            if value is None or value == "":
                return 0.0
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _safe_text(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def _ensure_table(self) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS filter_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER,
                    market TEXT NOT NULL,
                    universe TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    name TEXT,
                    decision TEXT,
                    score REAL NOT NULL DEFAULT 0,
                    confidence REAL NOT NULL DEFAULT 0,
                    probability REAL NOT NULL DEFAULT 0,
                    risk_level TEXT,
                    robot_enabled INTEGER NOT NULL DEFAULT 0,
                    accepted INTEGER NOT NULL DEFAULT 0,
                    reject_score INTEGER NOT NULL DEFAULT 0,
                    reject_confidence INTEGER NOT NULL DEFAULT 0,
                    reject_probability INTEGER NOT NULL DEFAULT 0,
                    reject_risk INTEGER NOT NULL DEFAULT 0,
                    reject_decision INTEGER NOT NULL DEFAULT 0,
                    reject_open_position INTEGER NOT NULL DEFAULT 0,
                    reject_robot_disabled INTEGER NOT NULL DEFAULT 0,
                    reject_reasons TEXT,
                    minimum_score REAL NOT NULL DEFAULT 0,
                    minimum_confidence REAL NOT NULL DEFAULT 0,
                    minimum_probability REAL NOT NULL DEFAULT 0,
                    allowed_decisions TEXT,
                    allowed_risks TEXT,
                    price REAL NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_filter_decisions_created_at
                ON filter_decisions(created_at)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_filter_decisions_market_symbol
                ON filter_decisions(market, symbol)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_filter_decisions_run_id
                ON filter_decisions(run_id)
                """
            )
            connection.commit()

    def record_rows(
        self,
        *,
        run_id: int,
        rows: list[dict[str, Any]],
        market: str,
        universe: str,
        robot,
        robot_enabled: bool,
    ) -> int:
        if not rows:
            return 0

        state = robot.get_state()
        effective_enabled = bool(robot_enabled and state.get("enabled", False))
        created_at = self._now()
        records: list[tuple[Any, ...]] = []

        for row in rows:
            symbol = self._safe_text(row.get("Kod"))
            if not symbol:
                continue

            name = self._safe_text(
                row.get("Ad")
                or row.get("Hisse")
                or row.get("Coin")
                or row.get("Emtia")
                or symbol
            )
            decision = self._safe_text(row.get("Karar"))
            score = self._safe_float(row.get("Puan"))
            confidence = self._safe_float(row.get("Güven", 0))
            probability = self._safe_float(row.get("Başarı Göstergesi %", 0))
            risk = self._safe_text(row.get("Risk"))
            price = self._safe_float(row.get("Fiyat"))

            reject_robot_disabled = not effective_enabled
            reject_decision = decision not in robot.config.allowed_decisions
            reject_score = score < robot.config.minimum_score
            reject_confidence = confidence < robot.config.minimum_confidence
            reject_probability = probability < robot.config.minimum_probability
            reject_risk = bool(
                robot.config.allowed_risks
                and risk not in robot.config.allowed_risks
            )
            reject_open_position = robot.has_open_position(symbol)

            reasons: list[str] = []
            if reject_robot_disabled:
                reasons.append("robot_disabled")
            if reject_decision:
                reasons.append("decision")
            if reject_score:
                reasons.append("score")
            if reject_confidence:
                reasons.append("confidence")
            if reject_probability:
                reasons.append("probability")
            if reject_risk:
                reasons.append("risk")
            if reject_open_position:
                reasons.append("open_position")

            accepted = not reasons

            records.append(
                (
                    run_id,
                    market,
                    universe,
                    symbol,
                    name,
                    decision,
                    score,
                    confidence,
                    probability,
                    risk,
                    int(effective_enabled),
                    int(accepted),
                    int(reject_score),
                    int(reject_confidence),
                    int(reject_probability),
                    int(reject_risk),
                    int(reject_decision),
                    int(reject_open_position),
                    int(reject_robot_disabled),
                    json.dumps(reasons, ensure_ascii=False),
                    float(robot.config.minimum_score),
                    float(robot.config.minimum_confidence),
                    float(robot.config.minimum_probability),
                    json.dumps(
                        list(robot.config.allowed_decisions),
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        list(robot.config.allowed_risks),
                        ensure_ascii=False,
                    ),
                    price,
                    created_at,
                )
            )

        if not records:
            return 0

        with self.database.connect() as connection:
            connection.executemany(
                """
                INSERT INTO filter_decisions (
                    run_id,
                    market,
                    universe,
                    symbol,
                    name,
                    decision,
                    score,
                    confidence,
                    probability,
                    risk_level,
                    robot_enabled,
                    accepted,
                    reject_score,
                    reject_confidence,
                    reject_probability,
                    reject_risk,
                    reject_decision,
                    reject_open_position,
                    reject_robot_disabled,
                    reject_reasons,
                    minimum_score,
                    minimum_confidence,
                    minimum_probability,
                    allowed_decisions,
                    allowed_risks,
                    price,
                    created_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?
                )
                """,
                records,
            )
            connection.commit()

        return len(records)
