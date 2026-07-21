from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class TradeRecord:
    trade_id: str
    symbol: str
    side: str
    quantity: float
    entry_price: float
    exit_price: float
    opened_at: datetime
    closed_at: datetime
    gross_pnl: float
    commission: float = 0.0
    slippage_cost: float = 0.0
    entry_reason: str = ""
    exit_reason: str = ""
    strategy: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.symbol = self.symbol.strip().upper()
        self.side = self.side.strip().upper()
        if not self.trade_id:
            self.trade_id = uuid4().hex
        if not self.symbol:
            raise ValueError("symbol boş olamaz.")
        if self.side not in {"LONG", "SHORT"}:
            raise ValueError("side LONG veya SHORT olmalıdır.")
        if self.quantity <= 0:
            raise ValueError("quantity pozitif olmalıdır.")
        if self.entry_price <= 0 or self.exit_price <= 0:
            raise ValueError("Fiyatlar pozitif olmalıdır.")
        if self.commission < 0 or self.slippage_cost < 0:
            raise ValueError("Maliyetler negatif olamaz.")
        if self.closed_at < self.opened_at:
            raise ValueError("Kapanış zamanı açılıştan önce olamaz.")
        if not isinstance(self.metadata, dict):
            raise TypeError("metadata sözlük olmalıdır.")

    @property
    def net_pnl(self) -> float:
        return self.gross_pnl - self.commission - self.slippage_cost

    @property
    def return_pct(self) -> float:
        capital = self.entry_price * self.quantity
        return (self.net_pnl / capital) * 100.0 if capital else 0.0

    @property
    def duration_seconds(self) -> float:
        return (self.closed_at - self.opened_at).total_seconds()

    @property
    def result(self) -> str:
        if self.net_pnl > 0:
            return "WIN"
        if self.net_pnl < 0:
            return "LOSS"
        return "BREAKEVEN"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "opened_at": self.opened_at.isoformat(),
            "closed_at": self.closed_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "gross_pnl": self.gross_pnl,
            "commission": self.commission,
            "slippage_cost": self.slippage_cost,
            "net_pnl": self.net_pnl,
            "return_pct": self.return_pct,
            "result": self.result,
            "entry_reason": self.entry_reason,
            "exit_reason": self.exit_reason,
            "strategy": self.strategy,
            "metadata": dict(self.metadata),
        }


@dataclass(slots=True)
class JournalStats:
    trade_count: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    gross_profit: float
    gross_loss: float
    net_pnl: float
    win_rate: float
    profit_factor: float
    average_win: float
    average_loss: float
    expectancy: float
    average_return_pct: float
    average_duration_seconds: float
    largest_win: float
    largest_loss: float
    total_commission: float
    total_slippage_cost: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PeriodSummary:
    period: str
    trade_count: int
    winning_trades: int
    losing_trades: int
    net_pnl: float
    return_pct_sum: float
    commission: float
    slippage_cost: float

    @property
    def win_rate(self) -> float:
        return (self.winning_trades / self.trade_count) * 100.0 if self.trade_count else 0.0

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["win_rate"] = self.win_rate
        return data


class TradeJournal:
    def __init__(self) -> None:
        self._trades: List[TradeRecord] = []
        self._trade_ids: set[str] = set()

    def add_trade(self, trade: TradeRecord) -> TradeRecord:
        if trade.trade_id in self._trade_ids:
            return self.get_trade(trade.trade_id)
        self._trades.append(trade)
        self._trade_ids.add(trade.trade_id)
        return trade

    def add_trades(self, trades: Iterable[TradeRecord]) -> None:
        for trade in trades:
            self.add_trade(trade)

    def create_trade(
        self,
        *,
        symbol: str,
        side: str,
        quantity: float,
        entry_price: float,
        exit_price: float,
        opened_at: datetime,
        closed_at: datetime,
        gross_pnl: Optional[float] = None,
        commission: float = 0.0,
        slippage_cost: float = 0.0,
        entry_reason: str = "",
        exit_reason: str = "",
        strategy: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        trade_id: Optional[str] = None,
    ) -> TradeRecord:
        normalized_side = side.strip().upper()
        if gross_pnl is None:
            if normalized_side == "LONG":
                gross_pnl = (exit_price - entry_price) * quantity
            elif normalized_side == "SHORT":
                gross_pnl = (entry_price - exit_price) * quantity
            else:
                raise ValueError("side LONG veya SHORT olmalıdır.")
        return self.add_trade(TradeRecord(
            trade_id=trade_id or uuid4().hex,
            symbol=symbol,
            side=normalized_side,
            quantity=quantity,
            entry_price=entry_price,
            exit_price=exit_price,
            opened_at=opened_at,
            closed_at=closed_at,
            gross_pnl=gross_pnl,
            commission=commission,
            slippage_cost=slippage_cost,
            entry_reason=entry_reason,
            exit_reason=exit_reason,
            strategy=strategy,
            metadata=metadata or {},
        ))

    def get_trade(self, trade_id: str) -> TradeRecord:
        for trade in self._trades:
            if trade.trade_id == trade_id:
                return trade
        raise KeyError(trade_id)

    def trades(
        self,
        *,
        symbol: Optional[str] = None,
        strategy: Optional[str] = None,
        result: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> List[TradeRecord]:
        items = list(self._trades)
        if symbol is not None:
            value = symbol.strip().upper()
            items = [x for x in items if x.symbol == value]
        if strategy is not None:
            items = [x for x in items if x.strategy == strategy]
        if result is not None:
            value = result.strip().upper()
            items = [x for x in items if x.result == value]
        if start is not None:
            items = [x for x in items if x.closed_at >= start]
        if end is not None:
            items = [x for x in items if x.closed_at <= end]
        return items

    def stats(self, trades: Optional[Iterable[TradeRecord]] = None) -> JournalStats:
        items = list(self._trades if trades is None else trades)
        wins = [x for x in items if x.net_pnl > 0]
        losses = [x for x in items if x.net_pnl < 0]
        breakeven = [x for x in items if x.net_pnl == 0]
        count = len(items)
        gross_profit = sum(x.net_pnl for x in wins)
        gross_loss = abs(sum(x.net_pnl for x in losses))
        average_win = gross_profit / len(wins) if wins else 0.0
        average_loss = gross_loss / len(losses) if losses else 0.0
        win_ratio = len(wins) / count if count else 0.0
        loss_ratio = len(losses) / count if count else 0.0
        if gross_loss:
            profit_factor = gross_profit / gross_loss
        elif gross_profit:
            profit_factor = float("inf")
        else:
            profit_factor = 0.0
        return JournalStats(
            trade_count=count,
            winning_trades=len(wins),
            losing_trades=len(losses),
            breakeven_trades=len(breakeven),
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            net_pnl=sum(x.net_pnl for x in items),
            win_rate=win_ratio * 100.0,
            profit_factor=profit_factor,
            average_win=average_win,
            average_loss=average_loss,
            expectancy=(average_win * win_ratio) - (average_loss * loss_ratio),
            average_return_pct=sum(x.return_pct for x in items) / count if count else 0.0,
            average_duration_seconds=sum(x.duration_seconds for x in items) / count if count else 0.0,
            largest_win=max((x.net_pnl for x in wins), default=0.0),
            largest_loss=min((x.net_pnl for x in losses), default=0.0),
            total_commission=sum(x.commission for x in items),
            total_slippage_cost=sum(x.slippage_cost for x in items),
        )

    @staticmethod
    def _period_key(trade: TradeRecord, period: str) -> str:
        closed = trade.closed_at
        if period == "daily":
            return closed.date().isoformat()
        if period == "weekly":
            year, week, _ = closed.isocalendar()
            return f"{year}-W{week:02d}"
        if period == "monthly":
            return f"{closed.year:04d}-{closed.month:02d}"
        raise ValueError("period daily, weekly veya monthly olmalıdır.")

    def summarize(self, period: str) -> List[PeriodSummary]:
        groups: Dict[str, List[TradeRecord]] = {}
        for trade in self._trades:
            groups.setdefault(self._period_key(trade, period), []).append(trade)
        output = []
        for key in sorted(groups):
            items = groups[key]
            output.append(PeriodSummary(
                period=key,
                trade_count=len(items),
                winning_trades=sum(x.net_pnl > 0 for x in items),
                losing_trades=sum(x.net_pnl < 0 for x in items),
                net_pnl=sum(x.net_pnl for x in items),
                return_pct_sum=sum(x.return_pct for x in items),
                commission=sum(x.commission for x in items),
                slippage_cost=sum(x.slippage_cost for x in items),
            ))
        return output

    def export_csv(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        rows = [x.to_dict() for x in self._trades]
        fields = list(rows[0].keys()) if rows else list(TradeRecord(
            trade_id="x", symbol="X", side="LONG", quantity=1,
            entry_price=1, exit_price=1, opened_at=utc_now(),
            closed_at=utc_now(), gross_pnl=0
        ).to_dict().keys())
        with target.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                row = dict(row)
                row["metadata"] = json.dumps(row["metadata"], ensure_ascii=False, sort_keys=True)
                writer.writerow(row)
        return target

    def export_sqlite(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        create_sql = (
            "CREATE TABLE IF NOT EXISTS trades ("
            "trade_id TEXT PRIMARY KEY, symbol TEXT NOT NULL, side TEXT NOT NULL, "
            "quantity REAL NOT NULL, entry_price REAL NOT NULL, exit_price REAL NOT NULL, "
            "opened_at TEXT NOT NULL, closed_at TEXT NOT NULL, gross_pnl REAL NOT NULL, "
            "commission REAL NOT NULL, slippage_cost REAL NOT NULL, entry_reason TEXT NOT NULL, "
            "exit_reason TEXT NOT NULL, strategy TEXT NOT NULL, metadata TEXT NOT NULL)"
        )
        insert_sql = (
            "INSERT OR REPLACE INTO trades "
            "(trade_id,symbol,side,quantity,entry_price,exit_price,opened_at,closed_at,"
            "gross_pnl,commission,slippage_cost,entry_reason,exit_reason,strategy,metadata) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
        )
        with sqlite3.connect(target) as connection:
            connection.execute(create_sql)
            for x in self._trades:
                connection.execute(insert_sql, (
                    x.trade_id, x.symbol, x.side, x.quantity, x.entry_price, x.exit_price,
                    x.opened_at.isoformat(), x.closed_at.isoformat(), x.gross_pnl,
                    x.commission, x.slippage_cost, x.entry_reason, x.exit_reason,
                    x.strategy, json.dumps(x.metadata, ensure_ascii=False, sort_keys=True),
                ))
            connection.commit()
        return target

    @classmethod
    def load_sqlite(cls, path: str | Path) -> "TradeJournal":
        target = Path(path)
        journal = cls()
        if not target.exists():
            return journal
        query = (
            "SELECT trade_id,symbol,side,quantity,entry_price,exit_price,opened_at,"
            "closed_at,gross_pnl,commission,slippage_cost,entry_reason,exit_reason,"
            "strategy,metadata FROM trades ORDER BY closed_at, trade_id"
        )
        with sqlite3.connect(target) as connection:
            rows = connection.execute(query).fetchall()
        for row in rows:
            journal.add_trade(TradeRecord(
                trade_id=row[0], symbol=row[1], side=row[2], quantity=row[3],
                entry_price=row[4], exit_price=row[5],
                opened_at=datetime.fromisoformat(row[6]),
                closed_at=datetime.fromisoformat(row[7]),
                gross_pnl=row[8], commission=row[9], slippage_cost=row[10],
                entry_reason=row[11], exit_reason=row[12], strategy=row[13],
                metadata=json.loads(row[14]),
            ))
        return journal

    def dashboard(self) -> Dict[str, Any]:
        return {
            "stats": self.stats().to_dict(),
            "daily": [x.to_dict() for x in self.summarize("daily")],
            "weekly": [x.to_dict() for x in self.summarize("weekly")],
            "monthly": [x.to_dict() for x in self.summarize("monthly")],
            "latest_trades": [
                x.to_dict() for x in sorted(
                    self._trades, key=lambda item: item.closed_at, reverse=True
                )[:20]
            ],
        }
