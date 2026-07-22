from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from engine.market_accounts import all_account_profiles


@dataclass(frozen=True)
class CapitalUpgradeResult:
    account_id: str
    market: str
    currency: str
    old_starting_balance: float
    new_starting_balance: float
    old_cash_balance: float
    new_cash_balance: float
    added_capital: float
    changed: bool


class PaperCapitalManager:
    """Sanal hesap sermayesini performans geçmişini bozmadan yükseltir."""

    def __init__(self, database):
        self.database = database

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    def status(self) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT account_id, market, currency, starting_balance, balance,
                       daily_profit, total_profit, enabled
                FROM robot_accounts
                ORDER BY market
                """
            ).fetchall()
        return [
            {
                "account_id": row[0], "market": row[1], "currency": row[2],
                "starting_balance": float(row[3]), "balance": float(row[4]),
                "daily_profit": float(row[5]), "total_profit": float(row[6]),
                "enabled": bool(row[7]),
            }
            for row in rows
        ]

    def apply_targets(self) -> list[CapitalUpgradeResult]:
        results: list[CapitalUpgradeResult] = []
        now = self._now()
        with self.database.connect() as connection:
            for target in all_account_profiles():
                account_id = str(target["account_id"])
                market = str(target["market"])
                currency = str(target["currency"])
                target_start = float(target["starting_balance"])
                row = connection.execute(
                    """
                    SELECT starting_balance, balance
                    FROM robot_accounts WHERE account_id = ?
                    """,
                    (account_id,),
                ).fetchone()
                if row is None:
                    connection.execute(
                        """
                        INSERT INTO robot_accounts(
                            account_id, market, currency, enabled, starting_balance,
                            balance, daily_profit, total_profit, updated_at
                        ) VALUES (?, ?, ?, 1, ?, ?, 0, 0, ?)
                        """,
                        (account_id, market, currency, target_start, target_start, now),
                    )
                    old_start = old_cash = 0.0
                    new_start = new_cash = target_start
                    delta = target_start
                    changed = True
                else:
                    old_start, old_cash = float(row[0]), float(row[1])
                    delta = max(0.0, target_start - old_start)
                    new_start = old_start + delta
                    new_cash = old_cash + delta
                    changed = delta > 0
                    if changed:
                        connection.execute(
                            """
                            UPDATE robot_accounts
                            SET starting_balance = ?, balance = ?, currency = ?,
                                market = ?, updated_at = ?
                            WHERE account_id = ?
                            """,
                            (new_start, new_cash, currency, market, now, account_id),
                        )
                result = CapitalUpgradeResult(
                    account_id=account_id, market=market, currency=currency,
                    old_starting_balance=old_start,
                    new_starting_balance=new_start,
                    old_cash_balance=old_cash,
                    new_cash_balance=new_cash,
                    added_capital=delta,
                    changed=changed,
                )
                results.append(result)
                if changed:
                    connection.execute(
                        """
                        INSERT INTO system_events(created_at, event_type, message)
                        VALUES (?, 'PAPER_CAPITAL_UPGRADE', ?)
                        """,
                        (now, json.dumps(result.__dict__, ensure_ascii=False)),
                    )
            connection.commit()
        return results
