from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from engine.robot_risk_enforcement import ensure_robot_risk_schema


@dataclass(slots=True)
class RiskEventSummary:
    total_events: int
    approved_count: int
    reduced_count: int
    rejected_count: int
    requested_value: float
    approved_value: float
    blocked_value: float
    approval_rate_pct: float
    reduction_rate_pct: float
    rejection_rate_pct: float
    top_reasons: list[dict[str, Any]]


def get_risk_lock(database, account_id: str) -> dict[str, Any]:
    with database.connect() as connection:
        ensure_robot_risk_schema(connection)
        row = connection.execute(
            "SELECT locked, reason, updated_at FROM robot_risk_locks WHERE account_id=?",
            (str(account_id),),
        ).fetchone()
    return {
        "locked": bool(row[0]) if row else False,
        "reason": str(row[1]) if row else "",
        "updated_at": row[2] if row else None,
    }


def set_risk_lock(database, account_id: str, *, locked: bool, reason: str = "") -> None:
    with database.connect() as connection:
        ensure_robot_risk_schema(connection)
        connection.execute(
            """
            INSERT INTO robot_risk_locks(account_id, locked, reason, updated_at)
            VALUES (?, ?, ?, datetime('now','localtime'))
            ON CONFLICT(account_id) DO UPDATE SET
                locked=excluded.locked,
                reason=excluded.reason,
                updated_at=excluded.updated_at
            """,
            (str(account_id), int(bool(locked)), str(reason or "")),
        )
        connection.commit()


def list_risk_events(
    database,
    account_id: str,
    *,
    limit: int = 100,
    event_type: str | None = None,
) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 1000))
    sql = """
        SELECT id, created_at, account_id, market, symbol, event_type, decision,
               reason, message, requested_quantity, approved_quantity,
               requested_value, approved_value, risk_amount, metadata_json
        FROM robot_risk_events
        WHERE account_id=?
    """
    params: list[Any] = [str(account_id)]
    if event_type and event_type != "ALL":
        sql += " AND event_type=?"
        params.append(str(event_type))
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with database.connect() as connection:
        ensure_robot_risk_schema(connection)
        rows = connection.execute(sql, params).fetchall()

    result: list[dict[str, Any]] = []
    for row in rows:
        try:
            metadata = json.loads(row[14] or "{}")
        except (TypeError, json.JSONDecodeError):
            metadata = {}
        result.append({
            "id": row[0], "created_at": row[1], "account_id": row[2],
            "market": row[3], "symbol": row[4], "event_type": row[5],
            "decision": row[6], "reason": row[7], "message": row[8],
            "requested_quantity": float(row[9] or 0),
            "approved_quantity": float(row[10] or 0),
            "requested_value": float(row[11] or 0),
            "approved_value": float(row[12] or 0),
            "risk_amount": float(row[13] or 0), "metadata": metadata,
        })
    return result


def summarize_risk_events(database, account_id: str, *, limit: int = 500) -> RiskEventSummary:
    events = list_risk_events(database, account_id, limit=limit)
    total = len(events)
    approved = sum(item["event_type"] == "RISK_APPROVED" for item in events)
    reduced = sum(item["event_type"] == "RISK_REDUCED" for item in events)
    rejected = sum(item["event_type"] == "RISK_REJECTED" for item in events)
    requested_value = sum(float(item["requested_value"]) for item in events)
    approved_value = sum(float(item["approved_value"]) for item in events)
    blocked_value = max(requested_value - approved_value, 0.0)

    reason_counts: dict[str, int] = {}
    for item in events:
        reason = str(item["reason"] or "UNKNOWN")
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    top_reasons = [
        {"reason": reason, "count": count}
        for reason, count in sorted(reason_counts.items(), key=lambda pair: (-pair[1], pair[0]))[:10]
    ]
    divisor = total or 1
    return RiskEventSummary(
        total_events=total,
        approved_count=approved,
        reduced_count=reduced,
        rejected_count=rejected,
        requested_value=requested_value,
        approved_value=approved_value,
        blocked_value=blocked_value,
        approval_rate_pct=approved / divisor * 100,
        reduction_rate_pct=reduced / divisor * 100,
        rejection_rate_pct=rejected / divisor * 100,
        top_reasons=top_reasons,
    )
