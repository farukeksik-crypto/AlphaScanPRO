from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Iterable

from database.intelligence_migrations import ensure_intelligence_schema
from engine.models.trade_snapshot import TradeSnapshot


class IntelligenceRepository:
    def __init__(self, database) -> None:
        self.database = database
        ensure_intelligence_schema(database)

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    def record_decision_events(self, events: Iterable[dict[str, Any]]) -> int:
        rows = []
        now = self._now()
        for event in events:
            symbol = str(event.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            rows.append((
                event.get("run_id"), str(event.get("market") or ""),
                str(event.get("universe") or ""), symbol,
                str(event.get("decision") or ""), float(event.get("score") or 0),
                float(event.get("confidence") or 0), float(event.get("probability") or 0),
                str(event.get("risk_level") or ""), int(bool(event.get("accepted"))),
                json.dumps(list(event.get("reject_reasons") or []), ensure_ascii=False),
                json.dumps(dict(event.get("trace_payload") or {}), ensure_ascii=False, default=str),
                str(event.get("created_at") or now),
            ))
        if not rows:
            return 0
        with self.database.connect() as connection:
            connection.executemany(
                """INSERT INTO intelligence_decision_events(
                    run_id, market, universe, symbol, decision, score, confidence, probability,
                    risk_level, accepted, reject_reasons, trace_payload, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", rows
            )
            connection.commit()
        return len(rows)

    def enqueue(self, *, event_type: str, market: str, universe: str, symbol: str, payload: dict[str, Any], trade_id: str = "") -> int:
        with self.database.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO intelligence_learning_queue(
                    event_type, market, universe, symbol, trade_id, payload, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (event_type, market, universe, symbol.upper(), trade_id, json.dumps(payload, ensure_ascii=False, default=str), self._now()),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def save_snapshot(self, snapshot: TradeSnapshot, *, position_id: int | None = None, account_id: str = "") -> None:
        payload = snapshot.to_dict()
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO intelligence_trade_snapshots(
                    trade_id, position_id, account_id, market, universe, symbol, status,
                    snapshot_payload, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(trade_id) DO UPDATE SET
                    position_id=excluded.position_id, account_id=excluded.account_id,
                    status=excluded.status, snapshot_payload=excluded.snapshot_payload,
                    updated_at=excluded.updated_at""",
                (snapshot.trade_id, position_id, account_id, snapshot.market, snapshot.universe,
                 snapshot.symbol, snapshot.status, json.dumps(payload, ensure_ascii=False, default=str),
                 snapshot.created_at, snapshot.updated_at),
            )
            connection.commit()

    def get_snapshot(self, trade_id: str) -> TradeSnapshot | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT snapshot_payload FROM intelligence_trade_snapshots WHERE trade_id = ?", (trade_id,)
            ).fetchone()
        return TradeSnapshot.from_dict(json.loads(row[0])) if row else None

    def summary(self) -> dict[str, Any]:
        with self.database.connect() as connection:
            decisions = connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(accepted),0) FROM intelligence_decision_events"
            ).fetchone()
            queue = connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(CASE WHEN status='PENDING' THEN 1 ELSE 0 END),0) FROM intelligence_learning_queue"
            ).fetchone()
            snapshots = connection.execute(
                "SELECT COUNT(*), COALESCE(SUM(CASE WHEN status='OPEN' THEN 1 ELSE 0 END),0) FROM intelligence_trade_snapshots"
            ).fetchone()
        total = int(decisions[0] or 0)
        accepted = int(decisions[1] or 0)
        return {
            "decision_events": total, "accepted_events": accepted,
            "acceptance_rate_pct": (accepted / total * 100.0) if total else 0.0,
            "learning_events": int(queue[0] or 0), "pending_learning_events": int(queue[1] or 0),
            "trade_snapshots": int(snapshots[0] or 0), "open_trade_snapshots": int(snapshots[1] or 0),
        }
