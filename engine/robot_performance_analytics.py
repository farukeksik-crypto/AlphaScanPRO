from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class PerformanceSummary:
    period_label: str
    closed_trades: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    win_rate_pct: float
    total_profit: float
    gross_profit: float
    gross_loss: float
    profit_factor: float | None
    average_profit: float
    average_win: float
    average_loss: float
    best_trade: float
    worst_trade: float
    average_profit_pct: float
    average_holding_minutes: float
    average_mfe_pct: float
    average_mae_pct: float
    average_risk_reward: float
    average_trade_quality_score: float
    best_market: str | None
    best_strategy: str | None
    best_grade: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RobotPerformanceAnalytics:
    """
    AlphaScan PRO robot performans analiz servisi.

    Yalnızca kapanış işlemlerini (trade_history.side = 'SELL') analiz eder.
    Database nesnesinin `connect()` metodu olması beklenir.
    """

    def __init__(
        self,
        database: Any,
        *,
        account_id: str = "bist_main",
        market: str | None = None,
    ) -> None:
        self.database = database
        self.account_id = str(account_id)
        self.market = str(market).upper() if market else None

    def load_closed_trades(
        self,
        *,
        days: int | None = None,
        limit: int | None = None,
    ) -> pd.DataFrame:
        where = [
            "account_id = ?",
            "side = 'SELL'",
        ]
        params: list[Any] = [self.account_id]

        if self.market:
            where.append("UPPER(COALESCE(market, '')) = ?")
            params.append(self.market)

        if days is not None:
            safe_days = max(1, int(days))
            where.append(
                "DATETIME(created_at) >= DATETIME('now', 'localtime', ?)"
            )
            params.append(f"-{safe_days} days")

        query = f"""
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
            WHERE {' AND '.join(where)}
            ORDER BY id DESC
        """

        if limit is not None:
            query += "\nLIMIT ?"
            params.append(max(1, int(limit)))

        with self.database.connect() as connection:
            frame = pd.read_sql_query(query, connection, params=params)

        return self._normalise_frame(frame)

    def build_summary(
        self,
        *,
        days: int | None = None,
        period_label: str | None = None,
    ) -> PerformanceSummary:
        frame = self.load_closed_trades(days=days)
        label = period_label or (
            "Tüm Zamanlar" if days is None else f"Son {int(days)} Gün"
        )

        if frame.empty:
            return PerformanceSummary(
                period_label=label,
                closed_trades=0,
                winning_trades=0,
                losing_trades=0,
                breakeven_trades=0,
                win_rate_pct=0.0,
                total_profit=0.0,
                gross_profit=0.0,
                gross_loss=0.0,
                profit_factor=None,
                average_profit=0.0,
                average_win=0.0,
                average_loss=0.0,
                best_trade=0.0,
                worst_trade=0.0,
                average_profit_pct=0.0,
                average_holding_minutes=0.0,
                average_mfe_pct=0.0,
                average_mae_pct=0.0,
                average_risk_reward=0.0,
                average_trade_quality_score=0.0,
                best_market=None,
                best_strategy=None,
                best_grade=None,
            )

        profit = frame["profit"].fillna(0.0)
        winners = frame[profit > 0]
        losers = frame[profit < 0]
        breakeven = frame[profit == 0]

        gross_profit = float(winners["profit"].sum()) if not winners.empty else 0.0
        gross_loss = abs(float(losers["profit"].sum())) if not losers.empty else 0.0
        profit_factor = (
            gross_profit / gross_loss
            if gross_loss > 0
            else (None if gross_profit == 0 else float("inf"))
        )

        return PerformanceSummary(
            period_label=label,
            closed_trades=int(len(frame)),
            winning_trades=int(len(winners)),
            losing_trades=int(len(losers)),
            breakeven_trades=int(len(breakeven)),
            win_rate_pct=self._round(
                len(winners) / len(frame) * 100.0 if len(frame) else 0.0
            ),
            total_profit=self._round(profit.sum()),
            gross_profit=self._round(gross_profit),
            gross_loss=self._round(gross_loss),
            profit_factor=(
                None
                if profit_factor is None
                else (
                    float("inf")
                    if profit_factor == float("inf")
                    else self._round(profit_factor, 3)
                )
            ),
            average_profit=self._round(profit.mean()),
            average_win=self._round(
                winners["profit"].mean() if not winners.empty else 0.0
            ),
            average_loss=self._round(
                losers["profit"].mean() if not losers.empty else 0.0
            ),
            best_trade=self._round(profit.max()),
            worst_trade=self._round(profit.min()),
            average_profit_pct=self._mean(frame, "profit_pct"),
            average_holding_minutes=self._mean(frame, "holding_minutes"),
            average_mfe_pct=self._mean(frame, "mfe_pct"),
            average_mae_pct=self._mean(frame, "mae_pct"),
            average_risk_reward=self._mean(frame, "risk_reward"),
            average_trade_quality_score=self._mean(
                frame, "trade_quality_score"
            ),
            best_market=self._best_group(frame, "market"),
            best_strategy=self._best_group(frame, "strategy_profile"),
            best_grade=self._most_common(frame, "trade_grade"),
        )

    def dashboard_payload(self) -> dict[str, Any]:
        return {
            "today": self.build_summary(
                days=1,
                period_label="Bugün",
            ).to_dict(),
            "last_7_days": self.build_summary(
                days=7,
                period_label="Son 7 Gün",
            ).to_dict(),
            "last_30_days": self.build_summary(
                days=30,
                period_label="Son 30 Gün",
            ).to_dict(),
            "all_time": self.build_summary(
                period_label="Tüm Zamanlar",
            ).to_dict(),
            "market_breakdown": self.market_breakdown(days=30),
            "strategy_breakdown": self.strategy_breakdown(days=30),
            "grade_breakdown": self.grade_breakdown(days=30),
            "daily_profit": self.daily_profit(days=30),
        }

    def market_breakdown(self, *, days: int | None = None) -> list[dict[str, Any]]:
        return self._group_breakdown("market", days=days)

    def strategy_breakdown(
        self,
        *,
        days: int | None = None,
    ) -> list[dict[str, Any]]:
        return self._group_breakdown("strategy_profile", days=days)

    def grade_breakdown(self, *, days: int | None = None) -> list[dict[str, Any]]:
        frame = self.load_closed_trades(days=days)
        if frame.empty or "trade_grade" not in frame:
            return []

        grade = frame["trade_grade"].fillna("BİLİNMİYOR").astype(str)
        result = (
            grade.value_counts(dropna=False)
            .rename_axis("trade_grade")
            .reset_index(name="trade_count")
        )
        return result.to_dict("records")

    def daily_profit(self, *, days: int = 30) -> list[dict[str, Any]]:
        frame = self.load_closed_trades(days=days)
        if frame.empty:
            return []

        frame = frame.copy()
        frame["date"] = pd.to_datetime(
            frame["created_at"], errors="coerce"
        ).dt.date
        frame = frame.dropna(subset=["date"])

        grouped = (
            frame.groupby("date", dropna=False)
            .agg(
                trade_count=("id", "count"),
                total_profit=("profit", "sum"),
                winning_trades=("profit", lambda s: int((s > 0).sum())),
                losing_trades=("profit", lambda s: int((s < 0).sum())),
            )
            .reset_index()
            .sort_values("date")
        )

        grouped["date"] = grouped["date"].astype(str)
        grouped["total_profit"] = grouped["total_profit"].round(2)
        grouped["win_rate_pct"] = grouped.apply(
            lambda row: round(
                (
                    float(row["winning_trades"])
                    / float(row["trade_count"])
                    * 100.0
                )
                if row["trade_count"]
                else 0.0,
                2,
            ),
            axis=1,
        )
        return grouped.to_dict("records")

    def _group_breakdown(
        self,
        column: str,
        *,
        days: int | None,
    ) -> list[dict[str, Any]]:
        frame = self.load_closed_trades(days=days)
        if frame.empty or column not in frame:
            return []

        work = frame.copy()
        work[column] = (
            work[column]
            .fillna("BİLİNMİYOR")
            .astype(str)
            .replace("", "BİLİNMİYOR")
        )

        grouped = (
            work.groupby(column, dropna=False)
            .agg(
                trade_count=("id", "count"),
                total_profit=("profit", "sum"),
                average_profit=("profit", "mean"),
                winning_trades=("profit", lambda s: int((s > 0).sum())),
                losing_trades=("profit", lambda s: int((s < 0).sum())),
                average_profit_pct=("profit_pct", "mean"),
                average_quality=("trade_quality_score", "mean"),
            )
            .reset_index()
        )

        grouped["win_rate_pct"] = grouped.apply(
            lambda row: (
                float(row["winning_trades"])
                / float(row["trade_count"])
                * 100.0
                if row["trade_count"]
                else 0.0
            ),
            axis=1,
        )

        numeric_columns = [
            "total_profit",
            "average_profit",
            "average_profit_pct",
            "average_quality",
            "win_rate_pct",
        ]
        for numeric_column in numeric_columns:
            grouped[numeric_column] = (
                pd.to_numeric(grouped[numeric_column], errors="coerce")
                .fillna(0.0)
                .round(2)
            )

        grouped = grouped.sort_values(
            ["total_profit", "win_rate_pct"],
            ascending=[False, False],
        )
        return grouped.to_dict("records")

    @staticmethod
    def _normalise_frame(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame

        numeric_columns = [
            "quantity",
            "price",
            "commission",
            "profit",
            "technical_score",
            "confidence_score",
            "entry_price",
            "exit_price",
            "profit_pct",
            "holding_minutes",
            "mfe_pct",
            "mae_pct",
            "risk_pct",
            "reward_pct",
            "risk_reward",
            "entry_efficiency",
            "exit_efficiency",
            "trade_quality_score",
        ]

        result = frame.copy()
        for column in numeric_columns:
            if column in result.columns:
                result[column] = pd.to_numeric(
                    result[column], errors="coerce"
                )

        return result

    @staticmethod
    def _mean(frame: pd.DataFrame, column: str) -> float:
        if column not in frame or frame[column].dropna().empty:
            return 0.0
        return round(float(frame[column].dropna().mean()), 2)

    @staticmethod
    def _best_group(frame: pd.DataFrame, column: str) -> str | None:
        if column not in frame:
            return None

        work = frame.dropna(subset=[column]).copy()
        if work.empty:
            return None

        work[column] = work[column].astype(str)
        work = work[work[column].str.strip() != ""]
        if work.empty:
            return None

        grouped = work.groupby(column)["profit"].sum()
        if grouped.empty:
            return None
        return str(grouped.idxmax())

    @staticmethod
    def _most_common(frame: pd.DataFrame, column: str) -> str | None:
        if column not in frame:
            return None

        values = frame[column].dropna().astype(str)
        values = values[values.str.strip() != ""]
        if values.empty:
            return None

        mode = values.mode()
        return str(mode.iloc[0]) if not mode.empty else None

    @staticmethod
    def _round(value: Any, digits: int = 2) -> float:
        try:
            return round(float(value), digits)
        except (TypeError, ValueError):
            return 0.0
