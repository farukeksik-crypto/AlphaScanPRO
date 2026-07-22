from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Any


@dataclass(frozen=True)
class UniversePerformanceRow:
    market: str
    universe: str
    scan_runs: int
    scanned: int
    failures: int
    robot_actions: int
    open_positions: int
    closed_trades: int
    winning_trades: int
    net_profit: float
    win_rate: float
    average_profit_pct: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class UniversePerformanceAnalytics:
    """Evren bazında tarama ve sanal işlem performansını birleştirir."""

    def __init__(self, database) -> None:
        self.database = database

    @staticmethod
    def _since(days: int) -> str:
        days = max(1, int(days))
        return (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")

    def rows(self, days: int = 30) -> list[UniversePerformanceRow]:
        since = self._since(days)
        with self.database.connect() as connection:
            connection.row_factory = None
            scan_rows = connection.execute(
                """
                SELECT market, universe,
                       COUNT(*) AS scan_runs,
                       COALESCE(SUM(scanned_count), 0),
                       COALESCE(SUM(failure_count), 0),
                       COALESCE(SUM(action_count), 0)
                FROM background_runs
                WHERE started_at >= ? AND status = 'SUCCESS'
                GROUP BY market, universe
                """,
                (since,),
            ).fetchall()
            open_rows = connection.execute(
                """
                SELECT COALESCE(market, 'BIST'), COALESCE(universe, ''), COUNT(*)
                FROM positions
                WHERE status = 'OPEN'
                GROUP BY COALESCE(market, 'BIST'), COALESCE(universe, '')
                """
            ).fetchall()
            trade_rows = connection.execute(
                """
                SELECT COALESCE(market, 'BIST'), COALESCE(universe, ''),
                       COUNT(*) AS closed_trades,
                       SUM(CASE WHEN COALESCE(profit, 0) > 0 THEN 1 ELSE 0 END),
                       COALESCE(SUM(profit), 0),
                       COALESCE(AVG(profit_pct), 0)
                FROM trade_history
                WHERE side = 'SELL' AND created_at >= ?
                GROUP BY COALESCE(market, 'BIST'), COALESCE(universe, '')
                """,
                (since,),
            ).fetchall()

        scans = {(str(r[0]), str(r[1])): r for r in scan_rows}
        opens = {(str(r[0]), str(r[1])): int(r[2] or 0) for r in open_rows}
        trades = {(str(r[0]), str(r[1])): r for r in trade_rows}
        keys = sorted(set(scans) | set(opens) | set(trades))
        result: list[UniversePerformanceRow] = []
        for key in keys:
            scan = scans.get(key, (key[0], key[1], 0, 0, 0, 0))
            trade = trades.get(key, (key[0], key[1], 0, 0, 0.0, 0.0))
            closed = int(trade[2] or 0)
            wins = int(trade[3] or 0)
            result.append(
                UniversePerformanceRow(
                    market=key[0], universe=key[1] or "Belirtilmemiş",
                    scan_runs=int(scan[2] or 0), scanned=int(scan[3] or 0),
                    failures=int(scan[4] or 0), robot_actions=int(scan[5] or 0),
                    open_positions=opens.get(key, 0), closed_trades=closed,
                    winning_trades=wins, net_profit=round(float(trade[4] or 0), 2),
                    win_rate=round((wins / closed * 100.0) if closed else 0.0, 2),
                    average_profit_pct=round(float(trade[5] or 0), 3),
                )
            )
        return result

    def summary(self, days: int = 30) -> dict[str, Any]:
        rows = self.rows(days)
        return {
            "days": max(1, int(days)),
            "universe_count": len(rows),
            "scan_runs": sum(r.scan_runs for r in rows),
            "scanned": sum(r.scanned for r in rows),
            "failures": sum(r.failures for r in rows),
            "robot_actions": sum(r.robot_actions for r in rows),
            "open_positions": sum(r.open_positions for r in rows),
            "closed_trades": sum(r.closed_trades for r in rows),
            "net_profit": round(sum(r.net_profit for r in rows), 2),
        }
