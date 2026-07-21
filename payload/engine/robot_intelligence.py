from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any

from engine.trade_journal_pro import ensure_trade_journal_pro


@dataclass(slots=True)
class IntelligenceAlert:
    level: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(slots=True)
class RobotIntelligenceSnapshot:
    generated_at: str
    enabled: bool
    balance: float
    daily_profit: float
    total_profit: float
    open_position_count: int
    open_market_value: float
    recent_trade_count: int
    recent_net_pnl: float
    recent_win_rate: float
    recent_profit_factor: float
    average_holding_minutes: float
    break_even_usage_pct: float
    trailing_usage_pct: float
    partial_exit_usage_pct: float
    best_symbol: str = ""
    worst_symbol: str = ""
    alerts: list[dict[str, str]] = field(default_factory=list)
    open_positions: list[dict[str, Any]] = field(default_factory=list)
    recent_trades: list[dict[str, Any]] = field(default_factory=list)
    symbol_performance: list[dict[str, Any]] = field(default_factory=list)
    exit_action_performance: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _profit_factor(rows: list[sqlite3.Row]) -> float:
    gross_profit = sum(max(_safe_float(row["net_pnl"]), 0.0) for row in rows)
    gross_loss = abs(sum(min(_safe_float(row["net_pnl"]), 0.0) for row in rows))
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def build_robot_intelligence_snapshot(
    connection: sqlite3.Connection,
    *,
    account_id: str | None = None,
    lookback_days: int = 30,
    recent_limit: int = 20,
) -> RobotIntelligenceSnapshot:
    if lookback_days <= 0:
        raise ValueError("lookback_days pozitif olmalıdır.")
    if recent_limit <= 0:
        raise ValueError("recent_limit pozitif olmalıdır.")

    connection.row_factory = sqlite3.Row
    ensure_trade_journal_pro(connection)

    state = connection.execute(
        "SELECT enabled, balance, daily_profit, total_profit FROM robot_state WHERE id=1"
    ).fetchone()
    enabled = bool(state["enabled"]) if state else False
    balance = _safe_float(state["balance"] if state else 0)
    daily_profit = _safe_float(state["daily_profit"] if state else 0)
    total_profit = _safe_float(state["total_profit"] if state else 0)

    position_columns = _table_columns(connection, "positions")
    select_parts = ["id", "symbol", "quantity", "entry_price", "stop_price", "target1", "target2", "opened_at", "status"]
    for optional in ("market", "current_price", "highest_price", "break_even_active", "trailing_active", "tp_stage"):
        if optional in position_columns:
            select_parts.append(optional)
    open_rows = connection.execute(
        f"SELECT {', '.join(select_parts)} FROM positions WHERE UPPER(status)='OPEN' ORDER BY opened_at"
    ).fetchall()
    open_positions = [dict(row) for row in open_rows]
    open_market_value = 0.0
    for row in open_positions:
        price = _safe_float(row.get("current_price")) or _safe_float(row.get("entry_price"))
        open_market_value += _safe_float(row.get("quantity")) * price

    cutoff = (datetime.now() - timedelta(days=lookback_days)).isoformat(timespec="seconds")
    where = ["closed_at >= ?"]
    params: list[Any] = [cutoff]
    if account_id:
        where.append("account_id = ?")
        params.append(account_id)
    where_sql = " AND ".join(where)

    trade_rows = connection.execute(
        f"SELECT * FROM trade_journal_pro WHERE {where_sql} ORDER BY closed_at DESC",
        tuple(params),
    ).fetchall()
    recent_trades = [dict(row) for row in trade_rows[:recent_limit]]
    trade_count = len(trade_rows)
    wins = sum(1 for row in trade_rows if _safe_float(row["net_pnl"]) > 0)
    recent_net_pnl = sum(_safe_float(row["net_pnl"]) for row in trade_rows)
    win_rate = wins / trade_count * 100.0 if trade_count else 0.0
    profit_factor = _profit_factor(trade_rows)
    avg_holding = sum(_safe_float(row["holding_minutes"]) for row in trade_rows) / trade_count if trade_count else 0.0
    be_pct = sum(int(row["break_even_active"] or 0) for row in trade_rows) / trade_count * 100.0 if trade_count else 0.0
    trailing_pct = sum(int(row["trailing_active"] or 0) for row in trade_rows) / trade_count * 100.0 if trade_count else 0.0
    partial_pct = sum(1 for row in trade_rows if str(row["event_type"]).upper() == "PARTIAL_EXIT") / trade_count * 100.0 if trade_count else 0.0

    symbol_rows = connection.execute(
        f"""
        SELECT symbol, COUNT(*) trade_count, SUM(net_pnl) net_pnl,
               AVG(net_pnl) average_pnl,
               100.0 * SUM(CASE WHEN net_pnl>0 THEN 1 ELSE 0 END)/COUNT(*) win_rate
        FROM trade_journal_pro WHERE {where_sql}
        GROUP BY symbol ORDER BY net_pnl DESC
        """,
        tuple(params),
    ).fetchall()
    symbol_performance = [dict(row) for row in symbol_rows]

    exit_rows = connection.execute(
        f"""
        SELECT CASE WHEN exit_action='' THEN event_type ELSE exit_action END exit_action,
               COUNT(*) trade_count, SUM(net_pnl) net_pnl, AVG(net_pnl) average_pnl,
               100.0 * SUM(CASE WHEN net_pnl>0 THEN 1 ELSE 0 END)/COUNT(*) win_rate
        FROM trade_journal_pro WHERE {where_sql}
        GROUP BY CASE WHEN exit_action='' THEN event_type ELSE exit_action END
        ORDER BY net_pnl DESC
        """,
        tuple(params),
    ).fetchall()
    exit_action_performance = [dict(row) for row in exit_rows]

    alerts: list[IntelligenceAlert] = []
    if not enabled:
        alerts.append(IntelligenceAlert("INFO", "ROBOT_DISABLED", "Robot şu anda kapalı."))
    if trade_count == 0:
        alerts.append(IntelligenceAlert("INFO", "NO_RECENT_TRADES", "Seçilen dönemde kapanmış işlem yok."))
    elif trade_count < 20:
        alerts.append(IntelligenceAlert("WARN", "LOW_SAMPLE", "İstatistik için işlem örneklemi henüz düşük."))
    if trade_count >= 5 and recent_net_pnl < 0:
        alerts.append(IntelligenceAlert("WARN", "NEGATIVE_PNL", "Son dönem net PnL negatiftir."))
    if trade_count >= 10 and profit_factor < 1.0:
        alerts.append(IntelligenceAlert("CRITICAL", "LOW_PROFIT_FACTOR", "Profit Factor 1,00 seviyesinin altındadır."))
    if len(open_positions) >= 5:
        alerts.append(IntelligenceAlert("WARN", "POSITION_LOAD", "Açık pozisyon sayısı yüksektir."))

    return RobotIntelligenceSnapshot(
        generated_at=datetime.now().isoformat(timespec="seconds"),
        enabled=enabled,
        balance=balance,
        daily_profit=daily_profit,
        total_profit=total_profit,
        open_position_count=len(open_positions),
        open_market_value=open_market_value,
        recent_trade_count=trade_count,
        recent_net_pnl=recent_net_pnl,
        recent_win_rate=win_rate,
        recent_profit_factor=profit_factor,
        average_holding_minutes=avg_holding,
        break_even_usage_pct=be_pct,
        trailing_usage_pct=trailing_pct,
        partial_exit_usage_pct=partial_pct,
        best_symbol=str(symbol_rows[0]["symbol"]) if symbol_rows else "",
        worst_symbol=str(symbol_rows[-1]["symbol"]) if symbol_rows else "",
        alerts=[item.to_dict() for item in alerts],
        open_positions=open_positions,
        recent_trades=recent_trades,
        symbol_performance=symbol_performance,
        exit_action_performance=exit_action_performance,
    )
