from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

from engine.trade_intelligence import analyze_closed_trade


@dataclass
class RobotConfig:
    starting_balance: float = 1_000_000.0
    commission_rate: float = 0.001
    max_positions: int = 5
    position_size_pct: float = 0.20
    minimum_score: float = 75.0
    minimum_probability: float = 55.0
    allowed_decisions: tuple[str, ...] = ("NET AL", "AL ADAY")
    strategy_profile: str = "Default"
    market: str = "BIST"
    account_id: str = "bist_main"
    currency: str = "TRY"


class RobotEngine:
    """
    AlphaScan PRO sanal işlem motoru.

    Gerçek emir göndermez. Tüm işlemleri SQLite üzerinde sanal olarak kaydeder.
    """

    def __init__(self, database, config: RobotConfig | None = None):
        self.database = database
        self.config = config or RobotConfig()
        self.market = str(self.config.market or "BIST").upper()
        self.account_id = str(self.config.account_id or "bist_main")
        self.currency = str(self.config.currency or "TRY")

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    def get_state(self) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT enabled, balance, daily_profit, total_profit, updated_at,
                       starting_balance, currency, market, account_id
                FROM robot_accounts
                WHERE account_id = ?
                """,
                (self.account_id,),
            ).fetchone()

        if row is None:
            return {
                "enabled": False,
                "balance": self.config.starting_balance,
                "daily_profit": 0.0,
                "total_profit": 0.0,
                "updated_at": None,
                "starting_balance": self.config.starting_balance,
                "currency": self.currency,
                "market": self.market,
                "account_id": self.account_id,
            }

        return {
            "enabled": bool(row[0]),
            "balance": float(row[1]),
            "daily_profit": float(row[2]),
            "total_profit": float(row[3]),
            "updated_at": row[4],
            "starting_balance": float(row[5]),
            "currency": str(row[6]),
            "market": str(row[7]),
            "account_id": str(row[8]),
        }

    def set_enabled(self, enabled: bool) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE robot_accounts
                SET enabled = ?, updated_at = ?
                WHERE account_id = ?
                """,
                (int(enabled), self._now(), self.account_id),
            )
            connection.commit()

    def reset_account(self) -> None:
        with self.database.connect() as connection:
            connection.execute(
                "DELETE FROM positions WHERE account_id = ?",
                (self.account_id,),
            )
            connection.execute(
                "DELETE FROM trade_history WHERE account_id = ?",
                (self.account_id,),
            )
            connection.execute(
                """
                UPDATE robot_accounts
                SET enabled = 0,
                    balance = starting_balance,
                    daily_profit = 0,
                    total_profit = 0,
                    updated_at = ?
                WHERE account_id = ?
                """,
                (self._now(), self.account_id),
            )
            connection.commit()

    def get_open_positions(self) -> pd.DataFrame:
        query = """
            SELECT
                id,
                symbol,
                quantity,
                entry_price,
                stop_price,
                target1,
                target2,
                opened_at,
                status,
                market,
                universe,
                technical_score,
                confidence_score,
                confidence_label,
                decision,
                entry_reason,
                strategy_profile,
                highest_price,
                lowest_price
            FROM positions
            WHERE status = 'OPEN' AND account_id = ?
            ORDER BY opened_at DESC
        """

        with self.database.connect() as connection:
            return pd.read_sql_query(
                query,
                connection,
                params=(self.account_id,),
            )

    def get_trade_history(self, limit: int = 200) -> pd.DataFrame:
        query = """
            SELECT
                id,
                symbol,
                side,
                quantity,
                price,
                commission,
                profit,
                created_at,
                market,
                universe,
                technical_score,
                confidence_score,
                confidence_label,
                decision,
                reason,
                strategy_profile,
                position_id,
                entry_price,
                exit_price,
                profit_pct,
                holding_minutes,
                mfe_pct,
                mae_pct,
                risk_pct,
                reward_pct,
                risk_reward,
                entry_efficiency,
                exit_efficiency,
                trade_quality_score,
                trade_grade
            FROM trade_history
            WHERE account_id = ?
            ORDER BY id DESC
            LIMIT ?
        """

        with self.database.connect() as connection:
            return pd.read_sql_query(
                query,
                connection,
                params=(self.account_id, int(limit)),
            )

    def has_open_position(self, symbol: str) -> bool:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM positions
                WHERE symbol = ?
                  AND status = 'OPEN'
                  AND account_id = ?
                LIMIT 1
                """,
                (symbol, self.account_id),
            ).fetchone()

        return row is not None

    def _open_position_count(self) -> int:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*)
                FROM positions
                WHERE status = 'OPEN'
                  AND account_id = ?
                """,
                (self.account_id,),
            ).fetchone()

        return int(row[0] if row else 0)

    def open_position(
        self,
        *,
        symbol: str,
        price: float,
        stop_price: float,
        target1: float,
        target2: float,
        score: float = 0.0,
        confidence: float = 0.0,
        confidence_label: str = "",
        decision: str = "",
        reason: str = "",
        market: str = "",
        universe: str = "",
        strategy_profile: str | None = None,
    ) -> dict[str, Any]:
        state = self.get_state()
        market = self.market

        if not state["enabled"]:
            return {"ok": False, "message": "Robot kapalı."}

        if price <= 0:
            return {"ok": False, "message": "Geçersiz fiyat."}

        if self.has_open_position(symbol):
            return {
                "ok": False,
                "message": f"{symbol} için açık pozisyon zaten var.",
            }

        if self._open_position_count() >= self.config.max_positions:
            return {
                "ok": False,
                "message": "Maksimum açık pozisyon sayısına ulaşıldı.",
            }

        budget = state["balance"] * self.config.position_size_pct
        quantity = budget / (
            price * (1.0 + self.config.commission_rate)
        )

        if quantity <= 0:
            return {
                "ok": False,
                "message": "Pozisyon miktarı hesaplanamadı.",
            }

        gross_cost = quantity * price
        commission = gross_cost * self.config.commission_rate
        total_cost = gross_cost + commission

        if total_cost > state["balance"]:
            return {
                "ok": False,
                "message": "Yetersiz sanal bakiye.",
            }

        opened_at = self._now()
        new_balance = state["balance"] - total_cost
        profile = strategy_profile or self.config.strategy_profile

        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO positions (
                    symbol,
                    quantity,
                    entry_price,
                    stop_price,
                    target1,
                    target2,
                    opened_at,
                    status,
                    market,
                    universe,
                    technical_score,
                    confidence_score,
                    confidence_label,
                    decision,
                    entry_reason,
                    strategy_profile,
                    account_id,
                    currency,
                    highest_price,
                    lowest_price
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN',
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol,
                    quantity,
                    price,
                    stop_price,
                    target1,
                    target2,
                    opened_at,
                    market,
                    universe,
                    score,
                    confidence,
                    confidence_label,
                    decision,
                    reason,
                    profile,
                    self.account_id,
                    self.currency,
                    price,
                    price,
                ),
            )

            position_id = int(cursor.lastrowid)

            connection.execute(
                """
                INSERT INTO trade_history (
                    symbol,
                    side,
                    quantity,
                    price,
                    commission,
                    profit,
                    created_at,
                    market,
                    universe,
                    technical_score,
                    confidence_score,
                    confidence_label,
                    decision,
                    reason,
                    strategy_profile,
                    position_id,
                    account_id,
                    currency
                )
                VALUES (?, 'BUY', ?, ?, ?, 0,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol,
                    quantity,
                    price,
                    commission,
                    opened_at,
                    market,
                    universe,
                    score,
                    confidence,
                    confidence_label,
                    decision,
                    reason,
                    profile,
                    position_id,
                    self.account_id,
                    self.currency,
                ),
            )

            connection.execute(
                """
                UPDATE robot_accounts
                SET balance = ?, updated_at = ?
                WHERE account_id = ?
                """,
                (new_balance, opened_at, self.account_id),
            )

            connection.execute(
                """
                INSERT INTO system_events (
                    created_at,
                    event_type,
                    message
                )
                VALUES (?, 'ROBOT_BUY', ?)
                """,
                (
                    opened_at,
                    (
                        f"{market}/{universe} | {symbol} sanal alım | "
                        f"fiyat={price:.4f} | miktar={quantity:.4f} | "
                        f"skor={score:.1f} | güven={confidence:.1f} | "
                        f"profil={profile} | {reason}"
                    ),
                ),
            )

            connection.commit()

        return {
            "ok": True,
            "message": f"{symbol} sanal pozisyon açıldı.",
            "position_id": position_id,
            "symbol": symbol,
            "quantity": quantity,
            "price": price,
            "commission": commission,
            "balance": new_balance,
            "market": market,
            "universe": universe,
            "score": score,
            "confidence": confidence,
        }

    def close_position(
        self,
        position_id: int,
        exit_price: float,
        exit_reason: str,
    ) -> dict[str, Any]:
        if exit_price <= 0:
            return {
                "ok": False,
                "message": "Geçersiz çıkış fiyatı.",
            }

        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    symbol,
                    quantity,
                    entry_price,
                    market,
                    universe,
                    technical_score,
                    confidence_score,
                    confidence_label,
                    decision,
                    entry_reason,
                    strategy_profile,
                    opened_at,
                    highest_price,
                    lowest_price,
                    stop_price,
                    target2
                FROM positions
                WHERE id = ?
                  AND status = 'OPEN'
                  AND account_id = ?
                """,
                (position_id, self.account_id),
            ).fetchone()

            if row is None:
                return {
                    "ok": False,
                    "message": "Açık pozisyon bulunamadı.",
                }

            (
                symbol,
                quantity,
                entry_price,
                market,
                universe,
                technical_score,
                confidence_score,
                confidence_label,
                decision,
                entry_reason,
                strategy_profile,
                opened_at,
                highest_price,
                lowest_price,
                stop_price,
                target2,
            ) = row

            quantity = float(quantity)
            entry_price = float(entry_price)

            state_row = connection.execute(
                """
                SELECT balance, daily_profit, total_profit
                FROM robot_accounts
                WHERE account_id = ?
                """,
                (self.account_id,),
            ).fetchone()

            if state_row is None:
                return {
                    "ok": False,
                    "message": "Robot hesabı bulunamadı.",
                }

            balance = float(state_row[0])
            daily_profit = float(state_row[1])
            total_profit = float(state_row[2])

            gross_revenue = quantity * exit_price
            sell_commission = (
                gross_revenue * self.config.commission_rate
            )
            net_revenue = gross_revenue - sell_commission

            entry_gross = quantity * entry_price
            buy_commission = (
                entry_gross * self.config.commission_rate
            )

            profit = (
                net_revenue
                - entry_gross
                - buy_commission
            )
            closed_at = self._now()
            new_balance = balance + net_revenue

            analytics = analyze_closed_trade(
                entry_price=entry_price,
                exit_price=exit_price,
                quantity=quantity,
                total_profit=profit,
                opened_at=opened_at,
                closed_at=closed_at,
                highest_price=highest_price,
                lowest_price=lowest_price,
                stop_price=stop_price,
                target_price=target2,
                technical_score=float(technical_score or 0),
                confidence_score=float(confidence_score or 0),
            )

            connection.execute(
                """
                UPDATE positions
                SET status = 'CLOSED'
                WHERE id = ?
                """,
                (position_id,),
            )

            connection.execute(
                """
                INSERT INTO trade_history (
                    symbol,
                    side,
                    quantity,
                    price,
                    commission,
                    profit,
                    created_at,
                    market,
                    universe,
                    technical_score,
                    confidence_score,
                    confidence_label,
                    decision,
                    reason,
                    strategy_profile,
                    position_id,
                    account_id,
                    currency,
                    entry_price,
                    exit_price,
                    profit_pct,
                    holding_minutes,
                    mfe_pct,
                    mae_pct,
                    risk_pct,
                    reward_pct,
                    risk_reward,
                    entry_efficiency,
                    exit_efficiency,
                    trade_quality_score,
                    trade_grade
                )
                VALUES (?, 'SELL', ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol,
                    quantity,
                    exit_price,
                    sell_commission,
                    profit,
                    closed_at,
                    market,
                    universe,
                    technical_score,
                    confidence_score,
                    confidence_label,
                    decision,
                    exit_reason,
                    strategy_profile,
                    position_id,
                    self.account_id,
                    self.currency,
                    entry_price,
                    exit_price,
                    analytics.profit_pct,
                    analytics.holding_minutes,
                    analytics.mfe_pct,
                    analytics.mae_pct,
                    analytics.risk_pct,
                    analytics.reward_pct,
                    analytics.risk_reward,
                    analytics.entry_efficiency,
                    analytics.exit_efficiency,
                    analytics.trade_quality_score,
                    analytics.trade_grade,
                ),
            )

            connection.execute(
                """
                UPDATE robot_accounts
                SET balance = ?,
                    daily_profit = ?,
                    total_profit = ?,
                    updated_at = ?
                WHERE account_id = ?
                """,
                (
                    new_balance,
                    daily_profit + profit,
                    total_profit + profit,
                    closed_at,
                    self.account_id,
                ),
            )

            connection.execute(
                """
                INSERT INTO system_events (
                    created_at,
                    event_type,
                    message
                )
                VALUES (?, 'ROBOT_SELL', ?)
                """,
                (
                    closed_at,
                    (
                        f"{market}/{universe} | {symbol} sanal satış | "
                        f"fiyat={exit_price:.4f} | "
                        f"kâr/zarar={profit:.2f} | "
                        f"neden={exit_reason} | "
                        f"profil={strategy_profile}"
                    ),
                ),
            )

            connection.commit()

        return {
            "ok": True,
            "message": f"{symbol} pozisyonu kapatıldı.",
            "symbol": symbol,
            "profit": profit,
            "balance": new_balance,
            "market": market,
            "universe": universe,
        }

    def process_open_positions(
        self,
        latest_prices: dict[str, float],
    ) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        positions = self.get_open_positions()

        if positions.empty:
            return actions

        for _, position in positions.iterrows():
            symbol = str(position["symbol"])
            current_price = latest_prices.get(symbol)

            if current_price is None:
                continue

            current_price = float(current_price)

            with self.database.connect() as connection:
                connection.execute(
                    """
                    UPDATE positions
                    SET highest_price = CASE
                            WHEN highest_price IS NULL OR ? > highest_price
                            THEN ? ELSE highest_price END,
                        lowest_price = CASE
                            WHEN lowest_price IS NULL OR ? < lowest_price
                            THEN ? ELSE lowest_price END
                    WHERE id = ?
                      AND status = 'OPEN'
                      AND account_id = ?
                    """,
                    (
                        current_price,
                        current_price,
                        current_price,
                        current_price,
                        int(position["id"]),
                        self.account_id,
                    ),
                )
                connection.commit()

            stop_price = float(
                position["stop_price"] or 0
            )
            target2 = float(
                position["target2"] or 0
            )

            if (
                stop_price > 0
                and current_price <= stop_price
            ):
                actions.append(
                    self.close_position(
                        int(position["id"]),
                        current_price,
                        "STOP",
                    )
                )

            elif (
                target2 > 0
                and current_price >= target2
            ):
                actions.append(
                    self.close_position(
                        int(position["id"]),
                        current_price,
                        "HEDEF 2",
                    )
                )

        return actions

    def process_scanner_results(
        self,
        results: list[dict[str, Any]],
        *,
        market: str = "",
        universe: str = "",
        strategy_profile: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self.get_state()["enabled"]:
            return [
                {
                    "ok": False,
                    "message": "Robot kapalı.",
                }
            ]

        actions: list[dict[str, Any]] = []

        candidates = sorted(
            results,
            key=lambda row: (
                float(
                    row.get(
                        "Başarı Göstergesi %",
                        0,
                    )
                    or 0
                ),
                float(
                    row.get(
                        "Güven",
                        0,
                    )
                    or 0
                ),
                float(
                    row.get(
                        "Puan",
                        0,
                    )
                    or 0
                ),
            ),
            reverse=True,
        )

        for row in candidates:
            decision = str(
                row.get(
                    "Karar",
                    "",
                )
            ).strip()

            score = float(
                row.get(
                    "Puan",
                    0,
                )
                or 0
            )

            if decision not in self.config.allowed_decisions:
                continue

            if score < self.config.minimum_score:
                continue

            probability = float(
                row.get(
                    "Başarı Göstergesi %",
                    0,
                )
                or 0
            )

            if probability < self.config.minimum_probability:
                continue

            risk_level = str(
                row.get(
                    "Risk",
                    "",
                )
            ).strip()

            # Normal riskli adaylarda genel eşikler geçerlidir:
            # minimum_score=75 ve minimum_probability=55.
            #
            # Yüksek riskli adaylar tamamen engellenmez.
            # Ancak yalnızca skor 80+ ve başarı olasılığı %60+
            # olduğunda sanal işleme alınır.
            if risk_level == "Yüksek":
                if score < 80 or probability < 60:
                    continue

            symbol = str(
                row.get(
                    "Kod",
                    "",
                )
            ).strip()

            price = float(
                row.get(
                    "Fiyat",
                    0,
                )
                or 0
            )

            if not symbol or price <= 0:
                continue

            row_market = str(
                row.get(
                    "Piyasa",
                    market,
                )
            )

            row_universe = str(
                row.get(
                    "Evren",
                    universe,
                )
            )

            actions.append(
                self.open_position(
                    symbol=symbol,
                    price=price,
                    stop_price=float(
                        row.get(
                            "Stop",
                            0,
                        )
                        or 0
                    ),
                    target1=float(
                        row.get(
                            "Hedef 1",
                            0,
                        )
                        or 0
                    ),
                    target2=float(
                        row.get(
                            "Hedef 2",
                            0,
                        )
                        or 0
                    ),
                    score=score,
                    confidence=float(
                        row.get(
                            "Güven",
                            0,
                        )
                        or 0
                    ),
                    confidence_label=str(
                        row.get(
                            "Güven Durumu",
                            "",
                        )
                    ),
                    decision=decision,
                    reason=str(
                        row.get(
                            "AI Analizi",
                            row.get(
                                "Neden",
                                "",
                            ),
                        )
                    ),
                    market=row_market,
                    universe=row_universe,
                    strategy_profile=strategy_profile,
                )
            )

            if (
                self._open_position_count()
                >= self.config.max_positions
            ):
                break

        return actions