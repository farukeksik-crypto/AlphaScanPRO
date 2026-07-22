from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from typing import Any, Iterable

from engine.portfolio_risk_manager import (
    PortfolioPosition,
    PortfolioRiskConfig,
    PortfolioRiskManager,
)


@dataclass(slots=True)
class RobotRiskDecision:
    approved: bool
    decision: str
    reason: str
    message: str
    requested_quantity: float
    approved_quantity: float
    requested_value: float
    approved_value: float
    risk_amount: float
    metrics: dict[str, float]

    @property
    def reduced(self) -> bool:
        return self.approved and self.approved_quantity < self.requested_quantity

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["reduced"] = self.reduced
        return data


_CREATE_EVENTS = """
CREATE TABLE IF NOT EXISTS robot_risk_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    account_id TEXT NOT NULL,
    market TEXT NOT NULL,
    symbol TEXT NOT NULL,
    event_type TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT NOT NULL,
    message TEXT NOT NULL,
    requested_quantity REAL NOT NULL DEFAULT 0,
    approved_quantity REAL NOT NULL DEFAULT 0,
    requested_value REAL NOT NULL DEFAULT 0,
    approved_value REAL NOT NULL DEFAULT 0,
    risk_amount REAL NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}'
)
"""

_CREATE_LOCKS = """
CREATE TABLE IF NOT EXISTS robot_risk_locks (
    account_id TEXT PRIMARY KEY,
    locked INTEGER NOT NULL DEFAULT 0,
    reason TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
)
"""


def ensure_robot_risk_schema(connection: sqlite3.Connection) -> None:
    connection.execute(_CREATE_EVENTS)
    connection.execute(_CREATE_LOCKS)
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_robot_risk_events_account_created "
        "ON robot_risk_events(account_id, created_at)"
    )


class RobotRiskEnforcer:
    """PortfolioRiskManager ile robot emir akışı arasındaki kalıcı köprü."""

    def __init__(
        self,
        database,
        *,
        account_id: str,
        market: str,
        config: PortfolioRiskConfig,
    ) -> None:
        self.database = database
        self.account_id = str(account_id)
        self.market = str(market)
        self.config = config
        with self.database.connect() as connection:
            ensure_robot_risk_schema(connection)
            connection.commit()

    def set_manual_lock(self, locked: bool, reason: str = "") -> None:
        with self.database.connect() as connection:
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
                (self.account_id, int(bool(locked)), str(reason or "")),
            )
            connection.commit()

    def lock_status(self) -> dict[str, Any]:
        with self.database.connect() as connection:
            ensure_robot_risk_schema(connection)
            row = connection.execute(
                "SELECT locked, reason, updated_at FROM robot_risk_locks WHERE account_id=?",
                (self.account_id,),
            ).fetchone()
        return {
            "locked": bool(row[0]) if row else False,
            "reason": str(row[1]) if row else "",
            "updated_at": row[2] if row else None,
        }

    def evaluate(
        self,
        *,
        symbol: str,
        price: float,
        stop_price: float,
        requested_quantity: float,
        equity: float,
        day_start_equity: float,
        realized_pnl_today: float,
        positions: Iterable[dict[str, Any]] = (),
        group: str = "DEFAULT",
        metadata: dict[str, Any] | None = None,
    ) -> RobotRiskDecision:
        lock = self.lock_status()
        if lock["locked"]:
            result = RobotRiskDecision(
                approved=False, decision="REJECTED", reason="MANUAL_RISK_LOCK",
                message=lock["reason"] or "Manuel acil risk kilidi aktif.",
                requested_quantity=float(requested_quantity), approved_quantity=0.0,
                requested_value=float(requested_quantity) * float(price), approved_value=0.0,
                risk_amount=0.0, metrics={},
            )
            self.record(symbol, result, metadata)
            return result

        manager = PortfolioRiskManager(self.config)
        manager.set_account_state(
            equity=max(float(equity), 0.01),
            day_start_equity=max(float(day_start_equity), 0.01),
            realized_pnl_today=float(realized_pnl_today),
        )
        synced: list[PortfolioPosition] = []
        for item in positions:
            qty = float(item.get("quantity", 0) or 0)
            entry = float(item.get("entry_price", 0) or 0)
            current = float(item.get("current_price", entry) or entry)
            stop = float(item.get("stop_price", 0) or 0)
            if qty and entry > 0 and current > 0 and stop > 0:
                synced.append(PortfolioPosition(
                    symbol=str(item.get("symbol", "")), quantity=qty,
                    entry_price=entry, current_price=current, stop_price=stop,
                    group=str(item.get("group") or item.get("universe") or "DEFAULT"),
                ))
        manager.sync_positions(synced)
        plan = manager.plan_trade(
            symbol=symbol, side="BUY", entry_price=float(price),
            stop_price=float(stop_price), requested_quantity=float(requested_quantity),
            group=group, metadata=metadata,
        )
        evaluation = plan.evaluation
        result = RobotRiskDecision(
            approved=evaluation.approved,
            decision=evaluation.decision.value,
            reason=evaluation.reason.value,
            message=evaluation.message,
            requested_quantity=float(requested_quantity),
            approved_quantity=float(evaluation.approved_quantity),
            requested_value=float(evaluation.requested_position_value),
            approved_value=float(evaluation.approved_position_value),
            risk_amount=float(evaluation.risk_amount),
            metrics=dict(evaluation.metrics),
        )
        self.record(symbol, result, metadata)
        return result

    def record(self, symbol: str, result: RobotRiskDecision, metadata: dict[str, Any] | None = None) -> int:
        event_type = "RISK_APPROVED" if result.approved else "RISK_REJECTED"
        if result.reduced:
            event_type = "RISK_REDUCED"
        with self.database.connect() as connection:
            ensure_robot_risk_schema(connection)
            cursor = connection.execute(
                """
                INSERT INTO robot_risk_events(
                    account_id, market, symbol, event_type, decision, reason, message,
                    requested_quantity, approved_quantity, requested_value,
                    approved_value, risk_amount, metadata_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (self.account_id, self.market, symbol, event_type, result.decision,
                 result.reason, result.message, result.requested_quantity,
                 result.approved_quantity, result.requested_value,
                 result.approved_value, result.risk_amount,
                 json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True)),
            )
            connection.commit()
            return int(cursor.lastrowid)
