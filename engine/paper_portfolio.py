from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from engine.paper_broker import PaperFill, PaperOrderSide


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class PortfolioPosition:
    symbol: str
    quantity: float = 0.0
    average_cost: float = 0.0
    realized_pnl: float = 0.0
    total_commission: float = 0.0
    last_price: Optional[float] = None
    updated_at: datetime = field(default_factory=utc_now)

    @property
    def market_value(self) -> float:
        if self.last_price is None:
            return 0.0
        return self.quantity * self.last_price

    @property
    def cost_basis(self) -> float:
        return self.quantity * self.average_cost

    @property
    def unrealized_pnl(self) -> float:
        if self.last_price is None:
            return 0.0
        return (self.last_price - self.average_cost) * self.quantity

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "average_cost": self.average_cost,
            "last_price": self.last_price,
            "market_value": self.market_value,
            "cost_basis": self.cost_basis,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "total_commission": self.total_commission,
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(slots=True)
class EquityPoint:
    timestamp: datetime
    cash: float
    positions_value: float
    equity: float
    realized_pnl: float
    unrealized_pnl: float
    drawdown: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "cash": self.cash,
            "positions_value": self.positions_value,
            "equity": self.equity,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "drawdown": self.drawdown,
        }


@dataclass(slots=True)
class DailyPerformance:
    day: date
    start_equity: float
    end_equity: float
    realized_pnl: float
    unrealized_pnl: float
    commission: float
    trade_count: int

    @property
    def net_pnl(self) -> float:
        return self.end_equity - self.start_equity

    @property
    def return_pct(self) -> float:
        if self.start_equity == 0:
            return 0.0
        return (self.net_pnl / self.start_equity) * 100.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "day": self.day.isoformat(),
            "start_equity": self.start_equity,
            "end_equity": self.end_equity,
            "net_pnl": self.net_pnl,
            "return_pct": self.return_pct,
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "commission": self.commission,
            "trade_count": self.trade_count,
        }


class PaperPortfolio:
    def __init__(self, starting_cash: float = 1_000_000.0) -> None:
        if starting_cash < 0:
            raise ValueError("starting_cash negatif olamaz.")

        self.starting_cash = float(starting_cash)
        self.cash = float(starting_cash)
        self.positions: Dict[str, PortfolioPosition] = {}
        self._processed_fill_ids: set[str] = set()
        self._equity_history: List[EquityPoint] = []
        self._daily: Dict[date, DailyPerformance] = {}
        self._peak_equity = float(starting_cash)
        self._trade_count = 0
        self._total_commission = 0.0
        self._gross_realized_pnl = 0.0

    def apply_fill(self, fill: PaperFill) -> PortfolioPosition:
        if fill.fill_id in self._processed_fill_ids:
            return self.positions.get(
                fill.symbol,
                PortfolioPosition(symbol=fill.symbol),
            )

        symbol = fill.symbol.strip().upper()
        position = self.positions.get(symbol)
        if position is None:
            position = PortfolioPosition(symbol=symbol)
            self.positions[symbol] = position

        if fill.side == PaperOrderSide.BUY:
            self._apply_buy(position, fill)
        elif fill.side == PaperOrderSide.SELL:
            self._apply_sell(position, fill)
        else:
            raise ValueError(f"Desteklenmeyen fill yönü: {fill.side}")

        self.cash += fill.net_cash_effect
        self._processed_fill_ids.add(fill.fill_id)
        self._trade_count += 1
        self._total_commission += fill.commission
        position.total_commission += fill.commission
        position.updated_at = fill.created_at

        if abs(position.quantity) <= 1e-12:
            position.quantity = 0.0
            position.average_cost = 0.0

        self._update_daily_from_fill(fill)
        return position

    def apply_fills(self, fills: Iterable[PaperFill]) -> None:
        for fill in fills:
            self.apply_fill(fill)

    def _apply_buy(self, position: PortfolioPosition, fill: PaperFill) -> None:
        if position.quantity >= 0:
            new_quantity = position.quantity + fill.quantity
            existing_cost = position.quantity * position.average_cost
            added_cost = fill.quantity * fill.price
            position.quantity = new_quantity
            position.average_cost = (
                (existing_cost + added_cost) / new_quantity
                if new_quantity > 0
                else 0.0
            )
            return

        short_quantity = abs(position.quantity)
        closing_quantity = min(fill.quantity, short_quantity)
        gross_pnl = (position.average_cost - fill.price) * closing_quantity
        position.realized_pnl += gross_pnl
        self._gross_realized_pnl += gross_pnl
        remaining_buy = fill.quantity - closing_quantity
        position.quantity += closing_quantity

        if abs(position.quantity) <= 1e-12:
            position.quantity = 0.0
            position.average_cost = 0.0

        if remaining_buy > 0:
            position.quantity = remaining_buy
            position.average_cost = fill.price

    def _apply_sell(self, position: PortfolioPosition, fill: PaperFill) -> None:
        if position.quantity > 0:
            closing_quantity = min(fill.quantity, position.quantity)
            gross_pnl = (fill.price - position.average_cost) * closing_quantity
            position.realized_pnl += gross_pnl
            self._gross_realized_pnl += gross_pnl
            remaining_sell = fill.quantity - closing_quantity
            position.quantity -= closing_quantity

            if abs(position.quantity) <= 1e-12:
                position.quantity = 0.0
                position.average_cost = 0.0

            if remaining_sell > 0:
                position.quantity = -remaining_sell
                position.average_cost = fill.price
            return

        if position.quantity <= 0:
            current_short = abs(position.quantity)
            new_short = current_short + fill.quantity
            existing_value = current_short * position.average_cost
            added_value = fill.quantity * fill.price
            position.quantity = -new_short
            position.average_cost = (
                (existing_value + added_value) / new_short
                if new_short > 0
                else 0.0
            )

    def update_market_price(
        self,
        symbol: str,
        price: float,
        *,
        timestamp: Optional[datetime] = None,
    ) -> None:
        if price <= 0:
            raise ValueError("price pozitif olmalıdır.")
        normalized = symbol.strip().upper()
        position = self.positions.get(normalized)
        if position is None:
            return
        position.last_price = float(price)
        position.updated_at = timestamp or utc_now()

    def update_market_prices(
        self,
        prices: Dict[str, float],
        *,
        timestamp: Optional[datetime] = None,
    ) -> None:
        for symbol, price in prices.items():
            self.update_market_price(symbol, price, timestamp=timestamp)

    @property
    def gross_realized_pnl(self) -> float:
        return self._gross_realized_pnl

    @property
    def net_realized_pnl(self) -> float:
        return self._gross_realized_pnl - self._total_commission

    @property
    def unrealized_pnl(self) -> float:
        return sum(position.unrealized_pnl for position in self.positions.values())

    @property
    def positions_value(self) -> float:
        return sum(position.market_value for position in self.positions.values())

    @property
    def equity(self) -> float:
        return self.cash + self.positions_value

    @property
    def total_return(self) -> float:
        return self.equity - self.starting_cash

    @property
    def total_return_pct(self) -> float:
        if self.starting_cash == 0:
            return 0.0
        return (self.total_return / self.starting_cash) * 100.0

    @property
    def total_commission(self) -> float:
        return self._total_commission

    @property
    def trade_count(self) -> int:
        return self._trade_count

    @property
    def peak_equity(self) -> float:
        return self._peak_equity

    @property
    def current_drawdown(self) -> float:
        if self._peak_equity <= 0:
            return 0.0
        return max((self._peak_equity - self.equity) / self._peak_equity, 0.0)

    @property
    def max_drawdown(self) -> float:
        if not self._equity_history:
            return self.current_drawdown
        return max(point.drawdown for point in self._equity_history)

    def record_equity(
        self,
        *,
        timestamp: Optional[datetime] = None,
    ) -> EquityPoint:
        ts = timestamp or utc_now()
        current_equity = self.equity
        self._peak_equity = max(self._peak_equity, current_equity)
        drawdown = (
            (self._peak_equity - current_equity) / self._peak_equity
            if self._peak_equity > 0
            else 0.0
        )

        point = EquityPoint(
            timestamp=ts,
            cash=self.cash,
            positions_value=self.positions_value,
            equity=current_equity,
            realized_pnl=self.net_realized_pnl,
            unrealized_pnl=self.unrealized_pnl,
            drawdown=max(drawdown, 0.0),
        )
        self._equity_history.append(point)
        self._update_daily_from_equity(point)
        return point

    def equity_history(self) -> List[EquityPoint]:
        return list(self._equity_history)

    def _update_daily_from_fill(self, fill: PaperFill) -> None:
        day = fill.created_at.date()
        record = self._daily.get(day)
        if record is None:
            record = DailyPerformance(
                day=day,
                start_equity=self.equity,
                end_equity=self.equity,
                realized_pnl=self.net_realized_pnl,
                unrealized_pnl=self.unrealized_pnl,
                commission=0.0,
                trade_count=0,
            )
            self._daily[day] = record
        record.commission += fill.commission
        record.trade_count += 1
        record.realized_pnl = self.net_realized_pnl
        record.unrealized_pnl = self.unrealized_pnl
        record.end_equity = self.equity

    def _update_daily_from_equity(self, point: EquityPoint) -> None:
        day = point.timestamp.date()
        record = self._daily.get(day)
        if record is None:
            record = DailyPerformance(
                day=day,
                start_equity=point.equity,
                end_equity=point.equity,
                realized_pnl=point.realized_pnl,
                unrealized_pnl=point.unrealized_pnl,
                commission=0.0,
                trade_count=0,
            )
            self._daily[day] = record
        record.end_equity = point.equity
        record.realized_pnl = point.realized_pnl
        record.unrealized_pnl = point.unrealized_pnl

    def daily_performance(self) -> List[DailyPerformance]:
        return [self._daily[key] for key in sorted(self._daily)]

    def get_position(self, symbol: str) -> Optional[PortfolioPosition]:
        return self.positions.get(symbol.strip().upper())

    def active_positions(self) -> List[PortfolioPosition]:
        return [
            position
            for position in self.positions.values()
            if abs(position.quantity) > 1e-12
        ]

    def snapshot(self) -> Dict[str, Any]:
        return {
            "starting_cash": self.starting_cash,
            "cash": self.cash,
            "positions_value": self.positions_value,
            "equity": self.equity,
            "gross_realized_pnl": self.gross_realized_pnl,
            "net_realized_pnl": self.net_realized_pnl,
            "unrealized_pnl": self.unrealized_pnl,
            "total_return": self.total_return,
            "total_return_pct": self.total_return_pct,
            "total_commission": self.total_commission,
            "trade_count": self.trade_count,
            "peak_equity": self.peak_equity,
            "current_drawdown": self.current_drawdown,
            "max_drawdown": self.max_drawdown,
            "active_position_count": len(self.active_positions()),
            "positions": {
                symbol: position.to_dict()
                for symbol, position in sorted(self.positions.items())
            },
        }
