from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from math import sqrt
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Iterable
import csv
import json

from engine.paper_trading_robot import PaperPortfolio, PaperTrade, PaperOrderStatus


@dataclass
class PerformanceConfig:
    risk_free_rate: float = 0.0
    periods_per_year: int = 365
    min_return_samples: int = 2
    timezone_name: str = "UTC"

    def validate(self) -> None:
        if self.periods_per_year <= 0:
            raise ValueError("periods_per_year pozitif olmalıdır.")
        if self.min_return_samples < 2:
            raise ValueError("min_return_samples en az 2 olmalıdır.")


@dataclass
class EquityPoint:
    timestamp: float
    equity: float
    cash: float
    market_value: float
    realized_pnl: float
    unrealized_pnl: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TradeStats:
    total_trades: int = 0
    closed_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0
    win_rate: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    net_profit: float = 0.0
    profit_factor: float = 0.0
    average_trade: float = 0.0
    average_win: float = 0.0
    average_loss: float = 0.0
    payoff_ratio: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RiskStats:
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    volatility: float = 0.0
    total_return: float = 0.0
    total_return_pct: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PerformanceReport:
    generated_at: float
    starting_equity: float
    ending_equity: float
    trade_stats: TradeStats
    risk_stats: RiskStats
    daily_performance: list[dict[str, Any]] = field(default_factory=list)
    weekly_performance: list[dict[str, Any]] = field(default_factory=list)
    monthly_performance: list[dict[str, Any]] = field(default_factory=list)
    equity_curve: list[dict[str, Any]] = field(default_factory=list)
    best_trades: list[dict[str, Any]] = field(default_factory=list)
    worst_trades: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "starting_equity": self.starting_equity,
            "ending_equity": self.ending_equity,
            "trade_stats": self.trade_stats.to_dict(),
            "risk_stats": self.risk_stats.to_dict(),
            "daily_performance": self.daily_performance,
            "weekly_performance": self.weekly_performance,
            "monthly_performance": self.monthly_performance,
            "equity_curve": self.equity_curve,
            "best_trades": self.best_trades,
            "worst_trades": self.worst_trades,
        }


class PerformanceTracker:
    def __init__(
        self,
        *,
        starting_equity: float,
        config: PerformanceConfig | None = None,
    ) -> None:
        if starting_equity <= 0:
            raise ValueError("starting_equity pozitif olmalıdır.")
        self.starting_equity = float(starting_equity)
        self.config = config or PerformanceConfig()
        self.config.validate()
        self.equity_points: list[EquityPoint] = []

    def record_portfolio(
        self,
        portfolio: PaperPortfolio,
        *,
        timestamp: float | None = None,
    ) -> EquityPoint:
        snapshot = portfolio.snapshot()
        point = EquityPoint(
            timestamp=float(timestamp if timestamp is not None else datetime.now(tz=timezone.utc).timestamp()),
            equity=snapshot.equity,
            cash=snapshot.cash,
            market_value=snapshot.market_value,
            realized_pnl=snapshot.realized_pnl,
            unrealized_pnl=snapshot.unrealized_pnl,
        )
        self.record_equity_point(point)
        return point

    def record_equity_point(self, point: EquityPoint) -> None:
        self.equity_points.append(point)
        self.equity_points.sort(key=lambda item: item.timestamp)

    def returns(self) -> list[float]:
        if len(self.equity_points) < 2:
            return []
        values = [self.starting_equity] + [point.equity for point in self.equity_points]
        result: list[float] = []
        for previous, current in zip(values, values[1:]):
            if previous == 0:
                result.append(0.0)
            else:
                result.append((current - previous) / previous)
        return result

    def drawdown_series(self) -> list[dict[str, float]]:
        peak = self.starting_equity
        rows: list[dict[str, float]] = []
        for point in self.equity_points:
            peak = max(peak, point.equity)
            drawdown = point.equity - peak
            drawdown_pct = (drawdown / peak * 100.0) if peak else 0.0
            rows.append(
                {
                    "timestamp": point.timestamp,
                    "equity": point.equity,
                    "peak": peak,
                    "drawdown": drawdown,
                    "drawdown_pct": drawdown_pct,
                }
            )
        return rows

    def risk_stats(self) -> RiskStats:
        ending_equity = (
            self.equity_points[-1].equity
            if self.equity_points
            else self.starting_equity
        )
        total_return = ending_equity - self.starting_equity
        total_return_pct = total_return / self.starting_equity * 100.0

        dd_rows = self.drawdown_series()
        max_drawdown = min((row["drawdown"] for row in dd_rows), default=0.0)
        max_drawdown_pct = min(
            (row["drawdown_pct"] for row in dd_rows),
            default=0.0,
        )

        returns = self.returns()
        volatility = pstdev(returns) if len(returns) >= self.config.min_return_samples else 0.0
        sharpe_ratio = 0.0
        if volatility > 0:
            period_rf = self.config.risk_free_rate / self.config.periods_per_year
            excess = [value - period_rf for value in returns]
            sharpe_ratio = mean(excess) / volatility * sqrt(self.config.periods_per_year)

        return RiskStats(
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            sharpe_ratio=sharpe_ratio,
            volatility=volatility,
            total_return=total_return,
            total_return_pct=total_return_pct,
        )

    def period_performance(self, period: str = "daily") -> list[dict[str, Any]]:
        if period not in {"daily", "weekly", "monthly"}:
            raise ValueError("period daily, weekly veya monthly olmalıdır.")

        groups: dict[str, list[EquityPoint]] = defaultdict(list)
        for point in self.equity_points:
            dt = datetime.fromtimestamp(point.timestamp, tz=timezone.utc)
            if period == "daily":
                key = dt.strftime("%Y-%m-%d")
            elif period == "weekly":
                iso_year, iso_week, _ = dt.isocalendar()
                key = f"{iso_year}-W{iso_week:02d}"
            elif period == "monthly":
                key = dt.strftime("%Y-%m")
            else:
                raise ValueError("period daily, weekly veya monthly olmalıdır.")
            groups[key].append(point)

        rows: list[dict[str, Any]] = []
        previous_equity = self.starting_equity
        for key in sorted(groups):
            points = sorted(groups[key], key=lambda item: item.timestamp)
            ending_equity = points[-1].equity
            pnl = ending_equity - previous_equity
            return_pct = pnl / previous_equity * 100.0 if previous_equity else 0.0
            rows.append(
                {
                    "period": key,
                    "starting_equity": previous_equity,
                    "ending_equity": ending_equity,
                    "pnl": pnl,
                    "return_pct": return_pct,
                    "points": len(points),
                }
            )
            previous_equity = ending_equity
        return rows


class TradeAnalyzer:
    @staticmethod
    def filled_sell_trades(
        trades: Iterable[PaperTrade | dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in trades:
            row = item.to_dict() if hasattr(item, "to_dict") else dict(item)
            status = str(row.get("status", "")).upper()
            side = str(row.get("side", "")).upper()
            if status == PaperOrderStatus.FILLED.value and side == "SELL":
                rows.append(row)
        return rows

    def trade_stats(
        self,
        trades: Iterable[PaperTrade | dict[str, Any]],
    ) -> TradeStats:
        all_rows = [
            item.to_dict() if hasattr(item, "to_dict") else dict(item)
            for item in trades
        ]
        closed = self.filled_sell_trades(all_rows)
        pnls = [float(row.get("realized_pnl", 0.0)) for row in closed]
        wins = [value for value in pnls if value > 0]
        losses = [value for value in pnls if value < 0]
        breakeven = [value for value in pnls if value == 0]

        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        net_profit = sum(pnls)
        profit_factor = (
            gross_profit / gross_loss
            if gross_loss > 0
            else (float("inf") if gross_profit > 0 else 0.0)
        )
        average_win = mean(wins) if wins else 0.0
        average_loss = mean(losses) if losses else 0.0
        payoff_ratio = (
            average_win / abs(average_loss)
            if average_loss < 0
            else (float("inf") if average_win > 0 else 0.0)
        )

        return TradeStats(
            total_trades=len(all_rows),
            closed_trades=len(closed),
            winning_trades=len(wins),
            losing_trades=len(losses),
            breakeven_trades=len(breakeven),
            win_rate=(len(wins) / len(closed) * 100.0) if closed else 0.0,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            net_profit=net_profit,
            profit_factor=profit_factor,
            average_trade=mean(pnls) if pnls else 0.0,
            average_win=average_win,
            average_loss=average_loss,
            payoff_ratio=payoff_ratio,
            best_trade=max(pnls, default=0.0),
            worst_trade=min(pnls, default=0.0),
        )

    def ranked_trades(
        self,
        trades: Iterable[PaperTrade | dict[str, Any]],
        *,
        limit: int = 5,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        closed = self.filled_sell_trades(trades)
        ranked = sorted(
            closed,
            key=lambda row: float(row.get("realized_pnl", 0.0)),
            reverse=True,
        )
        return ranked[:limit], list(reversed(ranked[-limit:]))


class PerformanceAnalytics:
    def __init__(
        self,
        *,
        starting_equity: float,
        config: PerformanceConfig | None = None,
    ) -> None:
        self.tracker = PerformanceTracker(
            starting_equity=starting_equity,
            config=config,
        )
        self.trade_analyzer = TradeAnalyzer()

    def record_portfolio(
        self,
        portfolio: PaperPortfolio,
        *,
        timestamp: float | None = None,
    ) -> EquityPoint:
        return self.tracker.record_portfolio(portfolio, timestamp=timestamp)

    def build_report(
        self,
        trades: Iterable[PaperTrade | dict[str, Any]],
    ) -> PerformanceReport:
        trade_rows = [
            item.to_dict() if hasattr(item, "to_dict") else dict(item)
            for item in trades
        ]
        best, worst = self.trade_analyzer.ranked_trades(trade_rows)
        ending_equity = (
            self.tracker.equity_points[-1].equity
            if self.tracker.equity_points
            else self.tracker.starting_equity
        )
        return PerformanceReport(
            generated_at=datetime.now(tz=timezone.utc).timestamp(),
            starting_equity=self.tracker.starting_equity,
            ending_equity=ending_equity,
            trade_stats=self.trade_analyzer.trade_stats(trade_rows),
            risk_stats=self.tracker.risk_stats(),
            daily_performance=self.tracker.period_performance("daily"),
            weekly_performance=self.tracker.period_performance("weekly"),
            monthly_performance=self.tracker.period_performance("monthly"),
            equity_curve=[point.to_dict() for point in self.tracker.equity_points],
            best_trades=best,
            worst_trades=worst,
        )

    def dashboard_payload(
        self,
        trades: Iterable[PaperTrade | dict[str, Any]],
    ) -> dict[str, Any]:
        report = self.build_report(trades)
        return {
            "summary": {
                "starting_equity": report.starting_equity,
                "ending_equity": report.ending_equity,
                "net_profit": report.trade_stats.net_profit,
                "win_rate": report.trade_stats.win_rate,
                "profit_factor": report.trade_stats.profit_factor,
                "max_drawdown_pct": report.risk_stats.max_drawdown_pct,
                "sharpe_ratio": report.risk_stats.sharpe_ratio,
                "total_return_pct": report.risk_stats.total_return_pct,
            },
            "equity_curve": report.equity_curve,
            "daily_performance": report.daily_performance,
            "monthly_performance": report.monthly_performance,
            "best_trades": report.best_trades,
            "worst_trades": report.worst_trades,
        }

    @staticmethod
    def export_json(report: PerformanceReport, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return target

    @staticmethod
    def export_csv(report: PerformanceReport, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        rows = report.equity_curve
        fieldnames = [
            "timestamp",
            "equity",
            "cash",
            "market_value",
            "realized_pnl",
            "unrealized_pnl",
        ]
        with target.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return target


class PerformanceRobotBridge:
    def __init__(
        self,
        *,
        portfolio: PaperPortfolio,
        analytics: PerformanceAnalytics | None = None,
    ) -> None:
        self.portfolio = portfolio
        self.analytics = analytics or PerformanceAnalytics(
            starting_equity=portfolio.config.starting_cash
        )

    def capture(self, timestamp: float | None = None) -> EquityPoint:
        return self.analytics.record_portfolio(
            self.portfolio,
            timestamp=timestamp,
        )

    def report(self) -> PerformanceReport:
        return self.analytics.build_report(self.portfolio.trades)

    def dashboard(self) -> dict[str, Any]:
        return self.analytics.dashboard_payload(self.portfolio.trades)
