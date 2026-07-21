from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from math import sqrt
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence


class BacktestSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class BacktestExitReason(str, Enum):
    SIGNAL = "SIGNAL"
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    TRAILING_STOP = "TRAILING_STOP"
    PARTIAL_TAKE_PROFIT = "PARTIAL_TAKE_PROFIT"
    END_OF_DATA = "END_OF_DATA"


@dataclass(slots=True)
class BacktestConfig:
    initial_capital: float = 100_000.0
    commission_pct: float = 0.001
    slippage_pct: float = 0.0005
    position_size_pct: float = 0.25
    stop_loss_pct: float = 0.03
    take_profit_pct: float = 0.06
    trailing_stop_pct: float = 0.025
    partial_take_profit_pct: float = 0.04
    partial_close_ratio: float = 0.50
    enable_short: bool = False
    force_close_at_end: bool = True

    def __post_init__(self) -> None:
        if self.initial_capital <= 0:
            raise ValueError("initial_capital pozitif olmalıdır.")
        for name in (
            "commission_pct",
            "slippage_pct",
            "position_size_pct",
            "stop_loss_pct",
            "take_profit_pct",
            "trailing_stop_pct",
            "partial_take_profit_pct",
        ):
            value = getattr(self, name)
            if value < 0:
                raise ValueError(f"{name} negatif olamaz.")
        if not 0 < self.position_size_pct <= 1:
            raise ValueError("position_size_pct 0-1 arasında olmalıdır.")
        if not 0 < self.partial_close_ratio <= 1:
            raise ValueError("partial_close_ratio 0-1 arasında olmalıdır.")


@dataclass(slots=True)
class BacktestBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("OHLC fiyatları pozitif olmalıdır.")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high değeri OHLC yapısına aykırı.")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low değeri OHLC yapısına aykırı.")


@dataclass(slots=True)
class BacktestPosition:
    side: BacktestSide
    quantity: float
    entry_price: float
    entry_time: datetime
    remaining_quantity: float
    highest_price: float
    lowest_price: float
    partial_taken: bool = False
    realized_pnl: float = 0.0
    total_commission: float = 0.0

    def unrealized_pnl(self, price: float) -> float:
        if self.side == BacktestSide.LONG:
            return (price - self.entry_price) * self.remaining_quantity
        return (self.entry_price - price) * self.remaining_quantity


@dataclass(slots=True)
class BacktestTrade:
    side: BacktestSide
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    quantity: float
    gross_pnl: float
    commission: float
    net_pnl: float
    return_pct: float
    exit_reason: BacktestExitReason
    partial: bool = False

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["side"] = self.side.value
        data["exit_reason"] = self.exit_reason.value
        data["entry_time"] = self.entry_time.isoformat()
        data["exit_time"] = self.exit_time.isoformat()
        return data


@dataclass(slots=True)
class EquityPoint:
    timestamp: datetime
    equity: float
    cash: float
    unrealized_pnl: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "equity": self.equity,
            "cash": self.cash,
            "unrealized_pnl": self.unrealized_pnl,
        }


@dataclass(slots=True)
class BacktestResult:
    config: BacktestConfig
    initial_capital: float
    final_equity: float
    net_profit: float
    net_profit_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: float
    max_drawdown_pct: float
    sharpe_ratio: float
    total_commission: float
    trades: List[BacktestTrade]
    equity_curve: List[EquityPoint]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "config": asdict(self.config),
            "initial_capital": self.initial_capital,
            "final_equity": self.final_equity,
            "net_profit": self.net_profit,
            "net_profit_pct": self.net_profit_pct,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "max_drawdown_pct": self.max_drawdown_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "total_commission": self.total_commission,
            "trades": [trade.to_dict() for trade in self.trades],
            "equity_curve": [point.to_dict() for point in self.equity_curve],
        }


SignalFunction = Callable[[int, BacktestBar, Sequence[BacktestBar]], str]


class BacktestEngineV2:
    def __init__(self, config: Optional[BacktestConfig] = None) -> None:
        self.config = config or BacktestConfig()
        self.cash = self.config.initial_capital
        self.position: Optional[BacktestPosition] = None
        self.trades: List[BacktestTrade] = []
        self.equity_curve: List[EquityPoint] = []
        self.total_commission = 0.0

    def _execution_price(self, price: float, *, is_buy: bool) -> float:
        if is_buy:
            return price * (1 + self.config.slippage_pct)
        return price * (1 - self.config.slippage_pct)

    def _commission(self, price: float, quantity: float) -> float:
        return abs(price * quantity) * self.config.commission_pct

    def _open_position(
        self,
        *,
        side: BacktestSide,
        price: float,
        timestamp: datetime,
    ) -> None:
        if self.position is not None:
            return
        if side == BacktestSide.SHORT and not self.config.enable_short:
            return

        is_buy = side == BacktestSide.LONG
        fill_price = self._execution_price(price, is_buy=is_buy)
        budget = self.cash * self.config.position_size_pct
        quantity = budget / fill_price
        commission = self._commission(fill_price, quantity)

        if quantity <= 0 or commission >= self.cash:
            return

        self.cash -= commission
        self.total_commission += commission
        self.position = BacktestPosition(
            side=side,
            quantity=quantity,
            entry_price=fill_price,
            entry_time=timestamp,
            remaining_quantity=quantity,
            highest_price=fill_price,
            lowest_price=fill_price,
            total_commission=commission,
        )

    def _close_quantity(
        self,
        *,
        bar: BacktestBar,
        quantity: float,
        reason: BacktestExitReason,
        partial: bool,
    ) -> BacktestTrade:
        if self.position is None:
            raise RuntimeError("Açık pozisyon yok.")

        position = self.position
        quantity = min(quantity, position.remaining_quantity)
        is_buy = position.side == BacktestSide.SHORT
        exit_price = self._execution_price(bar.close, is_buy=is_buy)
        commission = self._commission(exit_price, quantity)

        if position.side == BacktestSide.LONG:
            gross_pnl = (exit_price - position.entry_price) * quantity
        else:
            gross_pnl = (position.entry_price - exit_price) * quantity

        allocated_entry_commission = (
            position.total_commission * (quantity / position.quantity)
        )
        net_pnl = gross_pnl - commission - allocated_entry_commission
        self.cash += gross_pnl - commission
        self.total_commission += commission
        position.realized_pnl += net_pnl
        position.remaining_quantity -= quantity

        notional = position.entry_price * quantity
        return_pct = net_pnl / notional if notional else 0.0

        trade = BacktestTrade(
            side=position.side,
            entry_time=position.entry_time,
            exit_time=bar.timestamp,
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=quantity,
            gross_pnl=gross_pnl,
            commission=commission + allocated_entry_commission,
            net_pnl=net_pnl,
            return_pct=return_pct,
            exit_reason=reason,
            partial=partial,
        )
        self.trades.append(trade)

        if position.remaining_quantity <= 1e-12:
            self.position = None

        return trade

    def _evaluate_position(
        self,
        bar: BacktestBar,
        signal: str,
    ) -> None:
        if self.position is None:
            return

        position = self.position
        position.highest_price = max(position.highest_price, bar.high)
        position.lowest_price = min(position.lowest_price, bar.low)

        if (
            not position.partial_taken
            and self.config.partial_take_profit_pct > 0
        ):
            if position.side == BacktestSide.LONG:
                partial_trigger = position.entry_price * (
                    1 + self.config.partial_take_profit_pct
                )
                hit_partial = bar.high >= partial_trigger
            else:
                partial_trigger = position.entry_price * (
                    1 - self.config.partial_take_profit_pct
                )
                hit_partial = bar.low <= partial_trigger

            if hit_partial:
                quantity = position.quantity * self.config.partial_close_ratio
                self._close_quantity(
                    bar=BacktestBar(
                        timestamp=bar.timestamp,
                        open=partial_trigger,
                        high=partial_trigger,
                        low=partial_trigger,
                        close=partial_trigger,
                        volume=bar.volume,
                    ),
                    quantity=quantity,
                    reason=BacktestExitReason.PARTIAL_TAKE_PROFIT,
                    partial=True,
                )
                if self.position is None:
                    return
                self.position.partial_taken = True
                position = self.position

        if position.side == BacktestSide.LONG:
            stop_price = position.entry_price * (1 - self.config.stop_loss_pct)
            take_profit = position.entry_price * (
                1 + self.config.take_profit_pct
            )
            trailing = position.highest_price * (
                1 - self.config.trailing_stop_pct
            )

            if bar.low <= stop_price:
                close_bar = BacktestBar(
                    bar.timestamp, stop_price, stop_price, stop_price, stop_price
                )
                self._close_quantity(
                    bar=close_bar,
                    quantity=position.remaining_quantity,
                    reason=BacktestExitReason.STOP_LOSS,
                    partial=False,
                )
                return
            if bar.low <= trailing and trailing > position.entry_price:
                close_bar = BacktestBar(
                    bar.timestamp, trailing, trailing, trailing, trailing
                )
                self._close_quantity(
                    bar=close_bar,
                    quantity=position.remaining_quantity,
                    reason=BacktestExitReason.TRAILING_STOP,
                    partial=False,
                )
                return
            if bar.high >= take_profit:
                close_bar = BacktestBar(
                    bar.timestamp,
                    take_profit,
                    take_profit,
                    take_profit,
                    take_profit,
                )
                self._close_quantity(
                    bar=close_bar,
                    quantity=position.remaining_quantity,
                    reason=BacktestExitReason.TAKE_PROFIT,
                    partial=False,
                )
                return
            if signal in {"SELL", "EXIT"}:
                self._close_quantity(
                    bar=bar,
                    quantity=position.remaining_quantity,
                    reason=BacktestExitReason.SIGNAL,
                    partial=False,
                )
                return
        else:
            stop_price = position.entry_price * (1 + self.config.stop_loss_pct)
            take_profit = position.entry_price * (
                1 - self.config.take_profit_pct
            )
            trailing = position.lowest_price * (
                1 + self.config.trailing_stop_pct
            )

            if bar.high >= stop_price:
                close_bar = BacktestBar(
                    bar.timestamp, stop_price, stop_price, stop_price, stop_price
                )
                self._close_quantity(
                    bar=close_bar,
                    quantity=position.remaining_quantity,
                    reason=BacktestExitReason.STOP_LOSS,
                    partial=False,
                )
                return
            if bar.high >= trailing and trailing < position.entry_price:
                close_bar = BacktestBar(
                    bar.timestamp, trailing, trailing, trailing, trailing
                )
                self._close_quantity(
                    bar=close_bar,
                    quantity=position.remaining_quantity,
                    reason=BacktestExitReason.TRAILING_STOP,
                    partial=False,
                )
                return
            if bar.low <= take_profit:
                close_bar = BacktestBar(
                    bar.timestamp,
                    take_profit,
                    take_profit,
                    take_profit,
                    take_profit,
                )
                self._close_quantity(
                    bar=close_bar,
                    quantity=position.remaining_quantity,
                    reason=BacktestExitReason.TAKE_PROFIT,
                    partial=False,
                )
                return
            if signal in {"BUY", "EXIT"}:
                self._close_quantity(
                    bar=bar,
                    quantity=position.remaining_quantity,
                    reason=BacktestExitReason.SIGNAL,
                    partial=False,
                )
                return

    def _mark_equity(self, bar: BacktestBar) -> None:
        unrealized = (
            self.position.unrealized_pnl(bar.close)
            if self.position is not None else 0.0
        )
        self.equity_curve.append(
            EquityPoint(
                timestamp=bar.timestamp,
                equity=self.cash + unrealized,
                cash=self.cash,
                unrealized_pnl=unrealized,
            )
        )

    def run(
        self,
        bars: Iterable[BacktestBar],
        signal_function: SignalFunction,
    ) -> BacktestResult:
        sequence = list(bars)
        if not sequence:
            raise ValueError("Backtest için veri gereklidir.")

        self.cash = self.config.initial_capital
        self.position = None
        self.trades = []
        self.equity_curve = []
        self.total_commission = 0.0

        for index, bar in enumerate(sequence):
            signal = str(
                signal_function(index, bar, sequence)
            ).upper().strip()

            if self.position is not None:
                self._evaluate_position(bar, signal)

            if self.position is None:
                if signal == "BUY":
                    self._open_position(
                        side=BacktestSide.LONG,
                        price=bar.close,
                        timestamp=bar.timestamp,
                    )
                elif signal == "SELL" and self.config.enable_short:
                    self._open_position(
                        side=BacktestSide.SHORT,
                        price=bar.close,
                        timestamp=bar.timestamp,
                    )

            self._mark_equity(bar)

        if self.position is not None and self.config.force_close_at_end:
            final_bar = sequence[-1]
            self._close_quantity(
                bar=final_bar,
                quantity=self.position.remaining_quantity,
                reason=BacktestExitReason.END_OF_DATA,
                partial=False,
            )
            self._mark_equity(final_bar)

        return self._build_result()

    def _build_result(self) -> BacktestResult:
        final_equity = (
            self.equity_curve[-1].equity
            if self.equity_curve else self.cash
        )
        net_profit = final_equity - self.config.initial_capital
        net_profit_pct = net_profit / self.config.initial_capital

        winning = [trade for trade in self.trades if trade.net_pnl > 0]
        losing = [trade for trade in self.trades if trade.net_pnl < 0]
        gross_profit = sum(trade.net_pnl for trade in winning)
        gross_loss = abs(sum(trade.net_pnl for trade in losing))
        profit_factor = (
            gross_profit / gross_loss
            if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0
        )

        returns: List[float] = []
        for previous, current in zip(
            self.equity_curve,
            self.equity_curve[1:],
        ):
            if previous.equity != 0:
                returns.append(
                    (current.equity / previous.equity) - 1
                )

        sharpe = 0.0
        if len(returns) > 1:
            mean_return = sum(returns) / len(returns)
            variance = sum(
                (value - mean_return) ** 2
                for value in returns
            ) / (len(returns) - 1)
            std = sqrt(variance)
            if std > 0:
                sharpe = (mean_return / std) * sqrt(252)

        peak = float("-inf")
        max_drawdown = 0.0
        for point in self.equity_curve:
            peak = max(peak, point.equity)
            if peak > 0:
                drawdown = (peak - point.equity) / peak
                max_drawdown = max(max_drawdown, drawdown)

        total_trades = len(self.trades)
        win_rate = len(winning) / total_trades if total_trades else 0.0

        return BacktestResult(
            config=self.config,
            initial_capital=self.config.initial_capital,
            final_equity=final_equity,
            net_profit=net_profit,
            net_profit_pct=net_profit_pct,
            total_trades=total_trades,
            winning_trades=len(winning),
            losing_trades=len(losing),
            win_rate=win_rate,
            profit_factor=profit_factor,
            max_drawdown_pct=max_drawdown,
            sharpe_ratio=sharpe,
            total_commission=self.total_commission,
            trades=list(self.trades),
            equity_curve=list(self.equity_curve),
        )
