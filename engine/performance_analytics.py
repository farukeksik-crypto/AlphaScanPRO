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

# ---------------------------------------------------------------------------
# Sprint 10.13B - Trade Journal PRO analytics
# The original PaperTrading analytics API above remains fully compatible.
# ---------------------------------------------------------------------------

import math as _math
import sqlite3 as _sqlite3
from datetime import datetime as _datetime
from typing import Sequence as _Sequence


@dataclass(slots=True)
class JournalPerformanceMetrics:
    trade_count: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0
    win_rate_pct: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    net_pnl: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    average_win: float = 0.0
    average_loss: float = 0.0
    payoff_ratio: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    recovery_factor: float = 0.0
    average_holding_minutes: float = 0.0
    average_mfe_pct: float = 0.0
    average_mae_pct: float = 0.0
    total_commission: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class JournalPerformanceReport:
    metrics: JournalPerformanceMetrics
    equity_curve: list[dict[str, Any]] = field(default_factory=list)
    daily_pnl: list[dict[str, Any]] = field(default_factory=list)
    weekly_pnl: list[dict[str, Any]] = field(default_factory=list)
    monthly_pnl: list[dict[str, Any]] = field(default_factory=list)
    symbol_stats: list[dict[str, Any]] = field(default_factory=list)
    exit_stats: list[dict[str, Any]] = field(default_factory=list)
    market_stats: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "metrics": self.metrics.to_dict(),
            "equity_curve": self.equity_curve,
            "daily_pnl": self.daily_pnl,
            "weekly_pnl": self.weekly_pnl,
            "monthly_pnl": self.monthly_pnl,
            "symbol_stats": self.symbol_stats,
            "exit_stats": self.exit_stats,
            "market_stats": self.market_stats,
        }


def _journal_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if _math.isfinite(number) else default


def _journal_datetime(value: Any) -> _datetime | None:
    if isinstance(value, _datetime):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return _datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _journal_row_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    if isinstance(row, _sqlite3.Row):
        return dict(row)
    raise TypeError("İşlem satırı dict veya sqlite3.Row olmalıdır.")


def _normalize_journal_trades(rows: Iterable[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for raw in rows:
        row = _journal_row_dict(raw)
        closed_at = str(row.get("closed_at") or row.get("created_at") or "")
        normalized.append({
            **row,
            "closed_at": closed_at,
            "net_pnl": _journal_float(row.get("net_pnl", row.get("profit", 0.0))),
            "commission": _journal_float(row.get("commission", 0.0)),
            "holding_minutes": _journal_float(row.get("holding_minutes", 0.0)),
            "mfe_pct": _journal_float(row.get("mfe_pct", 0.0)),
            "mae_pct": _journal_float(row.get("mae_pct", 0.0)),
            "symbol": str(row.get("symbol") or "BİLİNMİYOR"),
            "market": str(row.get("market") or "BİLİNMİYOR"),
            "exit_action": str(row.get("exit_action") or row.get("event_type") or "BİLİNMİYOR"),
            "event_type": str(row.get("event_type") or ""),
        })
    normalized.sort(key=lambda item: (_journal_datetime(item["closed_at"]) or _datetime.min, str(item.get("id", ""))))
    return normalized


def calculate_journal_performance(
    rows: Iterable[Any],
    *,
    starting_equity: float = 0.0,
) -> JournalPerformanceReport:
    trades = _normalize_journal_trades(rows)
    pnls = [trade["net_pnl"] for trade in trades]
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]
    breakeven = [pnl for pnl in pnls if pnl == 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    trade_count = len(trades)
    net_pnl = sum(pnls)
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (_math.inf if gross_profit > 0 else 0.0)
    average_win = gross_profit / len(wins) if wins else 0.0
    average_loss = gross_loss / len(losses) if losses else 0.0

    equity_curve: list[dict[str, Any]] = []
    equity = float(starting_equity)
    peak = equity
    max_drawdown = 0.0
    max_drawdown_pct = 0.0
    for index, trade in enumerate(trades, start=1):
        equity += trade["net_pnl"]
        peak = max(peak, equity)
        drawdown = max(0.0, peak - equity)
        drawdown_pct = drawdown / peak * 100.0 if peak > 0 else 0.0
        max_drawdown = max(max_drawdown, drawdown)
        max_drawdown_pct = max(max_drawdown_pct, drawdown_pct)
        equity_curve.append({
            "trade_no": index,
            "closed_at": trade["closed_at"],
            "symbol": trade["symbol"],
            "net_pnl": trade["net_pnl"],
            "equity": equity,
            "peak": peak,
            "drawdown": drawdown,
            "drawdown_pct": drawdown_pct,
        })

    metrics = JournalPerformanceMetrics(
        trade_count=trade_count,
        winning_trades=len(wins),
        losing_trades=len(losses),
        breakeven_trades=len(breakeven),
        win_rate_pct=len(wins) / trade_count * 100.0 if trade_count else 0.0,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        net_pnl=net_pnl,
        profit_factor=profit_factor,
        expectancy=net_pnl / trade_count if trade_count else 0.0,
        average_win=average_win,
        average_loss=average_loss,
        payoff_ratio=average_win / average_loss if average_loss > 0 else (_math.inf if average_win > 0 else 0.0),
        max_drawdown=max_drawdown,
        max_drawdown_pct=max_drawdown_pct,
        recovery_factor=net_pnl / max_drawdown if max_drawdown > 0 else (_math.inf if net_pnl > 0 else 0.0),
        average_holding_minutes=sum(t["holding_minutes"] for t in trades) / trade_count if trade_count else 0.0,
        average_mfe_pct=sum(t["mfe_pct"] for t in trades) / trade_count if trade_count else 0.0,
        average_mae_pct=sum(t["mae_pct"] for t in trades) / trade_count if trade_count else 0.0,
        total_commission=sum(t["commission"] for t in trades),
        best_trade=max(pnls, default=0.0),
        worst_trade=min(pnls, default=0.0),
    )
    return JournalPerformanceReport(
        metrics=metrics,
        equity_curve=equity_curve,
        daily_pnl=_journal_period_stats(trades, "daily"),
        weekly_pnl=_journal_period_stats(trades, "weekly"),
        monthly_pnl=_journal_period_stats(trades, "monthly"),
        symbol_stats=_journal_group_stats(trades, "symbol"),
        exit_stats=_journal_group_stats(trades, "exit_action"),
        market_stats=_journal_group_stats(trades, "market"),
    )


def _journal_period_key(value: str, period: str) -> str:
    dt = _journal_datetime(value)
    if dt is None:
        return "TARİH YOK"
    if period == "daily":
        return dt.strftime("%Y-%m-%d")
    if period == "weekly":
        year, week, _ = dt.isocalendar()
        return f"{year}-W{week:02d}"
    if period == "monthly":
        return dt.strftime("%Y-%m")
    raise ValueError(f"Desteklenmeyen dönem: {period}")


def _journal_period_stats(trades: _Sequence[dict[str, Any]], period: str) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for trade in trades:
        buckets.setdefault(_journal_period_key(trade["closed_at"], period), []).append(trade)
    result: list[dict[str, Any]] = []
    cumulative = 0.0
    for key in sorted(buckets):
        items = buckets[key]
        pnl = sum(item["net_pnl"] for item in items)
        cumulative += pnl
        result.append({
            "period": key,
            "trade_count": len(items),
            "net_pnl": pnl,
            "cumulative_pnl": cumulative,
            "win_rate_pct": sum(1 for item in items if item["net_pnl"] > 0) / len(items) * 100.0,
        })
    return result


def _journal_group_stats(trades: _Sequence[dict[str, Any]], field_name: str) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for trade in trades:
        buckets.setdefault(str(trade.get(field_name) or "BİLİNMİYOR"), []).append(trade)
    result: list[dict[str, Any]] = []
    for group, items in buckets.items():
        pnls = [item["net_pnl"] for item in items]
        wins = [pnl for pnl in pnls if pnl > 0]
        losses = [pnl for pnl in pnls if pnl < 0]
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        result.append({
            field_name: group,
            "trade_count": len(items),
            "winning_trades": len(wins),
            "win_rate_pct": len(wins) / len(items) * 100.0,
            "net_pnl": sum(pnls),
            "average_pnl": sum(pnls) / len(items),
            "profit_factor": gross_profit / gross_loss if gross_loss > 0 else (_math.inf if gross_profit > 0 else 0.0),
            "average_holding_minutes": sum(item["holding_minutes"] for item in items) / len(items),
        })
    result.sort(key=lambda item: (item["net_pnl"], item["trade_count"]), reverse=True)
    return result


def load_trade_journal_rows(
    connection: _sqlite3.Connection,
    *,
    account_id: str | None = None,
    market: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    include_partial_exits: bool = True,
) -> list[dict[str, Any]]:
    from engine.trade_journal_pro import ensure_trade_journal_pro

    ensure_trade_journal_pro(connection)
    connection.row_factory = _sqlite3.Row
    clauses: list[str] = []
    params: list[Any] = []
    if account_id:
        clauses.append("account_id = ?")
        params.append(account_id)
    if market:
        clauses.append("market = ?")
        params.append(market)
    if date_from:
        clauses.append("closed_at >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("closed_at <= ?")
        params.append(date_to)
    if not include_partial_exits:
        clauses.append("UPPER(event_type) NOT LIKE '%PARTIAL%'")
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = connection.execute(
        f"SELECT * FROM trade_journal_pro{where} ORDER BY closed_at, id",
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def build_performance_report(
    connection: _sqlite3.Connection,
    *,
    account_id: str | None = None,
    market: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    include_partial_exits: bool = True,
    starting_equity: float = 0.0,
) -> JournalPerformanceReport:
    return calculate_journal_performance(
        load_trade_journal_rows(
            connection,
            account_id=account_id,
            market=market,
            date_from=date_from,
            date_to=date_to,
            include_partial_exits=include_partial_exits,
        ),
        starting_equity=starting_equity,
    )


# Friendly alias used by Sprint 10.13B tests and external callers.
calculate_performance = calculate_journal_performance
