from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from typing import Any, Iterable


@dataclass(slots=True)
class TradeJournalProEvent:
    position_id: int
    account_id: str
    market: str
    symbol: str
    event_type: str
    side: str
    quantity: float
    entry_price: float
    exit_price: float
    gross_pnl: float
    commission: float
    net_pnl: float
    entry_score: float = 0.0
    exit_score: float = 0.0
    exit_action: str = ""
    exit_reason: str = ""
    confirmations: int = 0
    break_even_active: bool = False
    trailing_active: bool = False
    tp_stage: int = 0
    opened_at: str = ""
    closed_at: str = ""
    holding_minutes: float = 0.0
    mfe_pct: float = 0.0
    mae_pct: float = 0.0
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["metadata"] = dict(self.metadata or {})
        return data


_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS trade_journal_pro (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id INTEGER NOT NULL,
    account_id TEXT NOT NULL,
    market TEXT NOT NULL,
    symbol TEXT NOT NULL,
    event_type TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL NOT NULL,
    gross_pnl REAL NOT NULL,
    commission REAL NOT NULL DEFAULT 0,
    net_pnl REAL NOT NULL,
    entry_score REAL NOT NULL DEFAULT 0,
    exit_score REAL NOT NULL DEFAULT 0,
    exit_action TEXT NOT NULL DEFAULT '',
    exit_reason TEXT NOT NULL DEFAULT '',
    confirmations INTEGER NOT NULL DEFAULT 0,
    break_even_active INTEGER NOT NULL DEFAULT 0,
    trailing_active INTEGER NOT NULL DEFAULT 0,
    tp_stage INTEGER NOT NULL DEFAULT 0,
    opened_at TEXT NOT NULL DEFAULT '',
    closed_at TEXT NOT NULL,
    holding_minutes REAL NOT NULL DEFAULT 0,
    mfe_pct REAL NOT NULL DEFAULT 0,
    mae_pct REAL NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}'
)
"""

_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_trade_journal_pro_account_closed "
    "ON trade_journal_pro(account_id, closed_at)",
    "CREATE INDEX IF NOT EXISTS idx_trade_journal_pro_position "
    "ON trade_journal_pro(position_id)",
    "CREATE INDEX IF NOT EXISTS idx_trade_journal_pro_symbol "
    "ON trade_journal_pro(symbol)",
)


def ensure_trade_journal_pro(connection: sqlite3.Connection) -> None:
    connection.execute(_CREATE_SQL)
    for statement in _INDEX_SQL:
        connection.execute(statement)


def record_trade_event(
    connection: sqlite3.Connection,
    event: TradeJournalProEvent,
) -> int:
    ensure_trade_journal_pro(connection)
    cursor = connection.execute(
        """
        INSERT INTO trade_journal_pro (
            position_id, account_id, market, symbol, event_type, side,
            quantity, entry_price, exit_price, gross_pnl, commission, net_pnl,
            entry_score, exit_score, exit_action, exit_reason, confirmations,
            break_even_active, trailing_active, tp_stage, opened_at, closed_at,
            holding_minutes, mfe_pct, mae_pct, metadata_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            event.position_id, event.account_id, event.market, event.symbol,
            event.event_type, event.side, event.quantity, event.entry_price,
            event.exit_price, event.gross_pnl, event.commission, event.net_pnl,
            event.entry_score, event.exit_score, event.exit_action,
            event.exit_reason, event.confirmations,
            int(event.break_even_active), int(event.trailing_active),
            event.tp_stage, event.opened_at, event.closed_at,
            event.holding_minutes, event.mfe_pct, event.mae_pct,
            json.dumps(event.metadata or {}, ensure_ascii=False, sort_keys=True),
        ),
    )
    return int(cursor.lastrowid)


def journal_summary(
    connection: sqlite3.Connection,
    *,
    account_id: str | None = None,
) -> dict[str, Any]:
    ensure_trade_journal_pro(connection)
    where = " WHERE account_id = ?" if account_id else ""
    params: Iterable[Any] = (account_id,) if account_id else ()
    row = connection.execute(
        f"""
        SELECT COUNT(*),
               COALESCE(SUM(net_pnl), 0),
               COALESCE(SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END), 0),
               COALESCE(AVG(holding_minutes), 0),
               COALESCE(AVG(exit_score), 0),
               COALESCE(SUM(CASE WHEN break_even_active=1 THEN 1 ELSE 0 END), 0),
               COALESCE(SUM(CASE WHEN trailing_active=1 THEN 1 ELSE 0 END), 0)
        FROM trade_journal_pro{where}
        """,
        tuple(params),
    ).fetchone()
    count = int(row[0])
    wins = int(row[2])
    return {
        "event_count": count,
        "net_pnl": float(row[1]),
        "winning_events": wins,
        "win_rate": (wins / count * 100.0) if count else 0.0,
        "average_holding_minutes": float(row[3]),
        "average_exit_score": float(row[4]),
        "break_even_events": int(row[5]),
        "trailing_events": int(row[6]),
    }
