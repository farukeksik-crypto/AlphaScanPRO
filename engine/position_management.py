from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ExitReason(str, Enum):
    NONE = "NONE"
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    TRAILING_STOP = "TRAILING_STOP"
    BREAK_EVEN = "BREAK_EVEN"
    PARTIAL_TAKE_PROFIT = "PARTIAL_TAKE_PROFIT"
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"
    MANUAL = "MANUAL"


class PositionSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass(slots=True)
class PositionManagementConfig:
    stop_loss_pct: float = 0.03
    take_profit_pct: float = 0.06
    trailing_stop_pct: float = 0.025
    break_even_trigger_pct: float = 0.03
    break_even_offset_pct: float = 0.002
    partial_take_profit_pct: float = 0.04
    partial_close_ratio: float = 0.50
    daily_loss_limit_pct: float = 0.04
    enable_stop_loss: bool = True
    enable_take_profit: bool = True
    enable_trailing_stop: bool = True
    enable_break_even: bool = True
    enable_partial_take_profit: bool = True

    def __post_init__(self) -> None:
        for name in (
            "stop_loss_pct",
            "take_profit_pct",
            "trailing_stop_pct",
            "break_even_trigger_pct",
            "break_even_offset_pct",
            "partial_take_profit_pct",
            "daily_loss_limit_pct",
        ):
            value = getattr(self, name)
            if value < 0:
                raise ValueError(f"{name} negatif olamaz.")
        if not 0 < self.partial_close_ratio <= 1:
            raise ValueError("partial_close_ratio 0-1 arasında olmalıdır.")


@dataclass(slots=True)
class ManagedPosition:
    symbol: str
    side: PositionSide
    quantity: float
    entry_price: float
    opened_at: datetime
    highest_price: float
    lowest_price: float
    stop_price: float
    take_profit_price: float
    trailing_stop_price: Optional[float] = None
    break_even_active: bool = False
    partial_taken: bool = False
    closed: bool = False
    remaining_quantity: float = 0.0
    realized_pnl: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.symbol = self.symbol.strip().upper()
        if not self.symbol:
            raise ValueError("symbol boş olamaz.")
        if self.quantity <= 0:
            raise ValueError("quantity pozitif olmalıdır.")
        if self.entry_price <= 0:
            raise ValueError("entry_price pozitif olmalıdır.")
        if self.remaining_quantity == 0:
            self.remaining_quantity = self.quantity

    def unrealized_pnl(self, price: float) -> float:
        if self.side == PositionSide.LONG:
            return (price - self.entry_price) * self.remaining_quantity
        return (self.entry_price - price) * self.remaining_quantity

    def return_pct(self, price: float) -> float:
        if self.side == PositionSide.LONG:
            return (price / self.entry_price) - 1
        return (self.entry_price / price) - 1

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["side"] = self.side.value
        data["opened_at"] = self.opened_at.isoformat()
        return data


@dataclass(slots=True)
class PositionAction:
    symbol: str
    reason: ExitReason
    action: str
    quantity: float
    price: float
    pnl: float = 0.0
    close_position: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["reason"] = self.reason.value
        return data


@dataclass(slots=True)
class DailyRiskState:
    trading_date: date
    starting_equity: float
    realized_pnl: float = 0.0
    blocked: bool = False

    @property
    def loss_pct(self) -> float:
        if self.starting_equity <= 0:
            return 0.0
        return max(0.0, -self.realized_pnl / self.starting_equity)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trading_date": self.trading_date.isoformat(),
            "starting_equity": self.starting_equity,
            "realized_pnl": self.realized_pnl,
            "loss_pct": self.loss_pct,
            "blocked": self.blocked,
        }


class PositionManagementEngine:
    def __init__(
        self,
        config: Optional[PositionManagementConfig] = None,
    ) -> None:
        self.config = config or PositionManagementConfig()
        self.positions: Dict[str, ManagedPosition] = {}
        self.actions: List[PositionAction] = []
        self.daily_risk: Optional[DailyRiskState] = None

    def start_trading_day(
        self,
        *,
        trading_date: date,
        starting_equity: float,
    ) -> DailyRiskState:
        if starting_equity <= 0:
            raise ValueError("starting_equity pozitif olmalıdır.")
        self.daily_risk = DailyRiskState(
            trading_date=trading_date,
            starting_equity=float(starting_equity),
        )
        return self.daily_risk

    def open_position(
        self,
        *,
        symbol: str,
        side: PositionSide,
        quantity: float,
        entry_price: float,
        opened_at: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ManagedPosition:
        normalized = symbol.strip().upper()
        if normalized in self.positions and not self.positions[normalized].closed:
            raise ValueError(f"Açık pozisyon zaten mevcut: {normalized}")

        if side == PositionSide.LONG:
            stop_price = entry_price * (1 - self.config.stop_loss_pct)
            take_profit_price = entry_price * (1 + self.config.take_profit_pct)
        else:
            stop_price = entry_price * (1 + self.config.stop_loss_pct)
            take_profit_price = entry_price * (1 - self.config.take_profit_pct)

        position = ManagedPosition(
            symbol=normalized,
            side=side,
            quantity=float(quantity),
            entry_price=float(entry_price),
            opened_at=opened_at or utc_now(),
            highest_price=float(entry_price),
            lowest_price=float(entry_price),
            stop_price=float(stop_price),
            take_profit_price=float(take_profit_price),
            metadata=dict(metadata or {}),
        )
        self.positions[normalized] = position
        return position

    def get_position(self, symbol: str) -> ManagedPosition:
        normalized = symbol.strip().upper()
        if normalized not in self.positions:
            raise KeyError(normalized)
        return self.positions[normalized]

    def _update_extremes(self, position: ManagedPosition, price: float) -> None:
        position.highest_price = max(position.highest_price, price)
        position.lowest_price = min(position.lowest_price, price)

    def _activate_break_even(
        self,
        position: ManagedPosition,
        price: float,
    ) -> None:
        if not self.config.enable_break_even or position.break_even_active:
            return
        if position.return_pct(price) < self.config.break_even_trigger_pct:
            return

        position.break_even_active = True
        if position.side == PositionSide.LONG:
            position.stop_price = max(
                position.stop_price,
                position.entry_price * (1 + self.config.break_even_offset_pct),
            )
        else:
            position.stop_price = min(
                position.stop_price,
                position.entry_price * (1 - self.config.break_even_offset_pct),
            )

    def _update_trailing_stop(
        self,
        position: ManagedPosition,
        price: float,
    ) -> None:
        if not self.config.enable_trailing_stop:
            return

        if position.side == PositionSide.LONG:
            candidate = position.highest_price * (1 - self.config.trailing_stop_pct)
            if position.trailing_stop_price is None:
                position.trailing_stop_price = candidate
            else:
                position.trailing_stop_price = max(
                    position.trailing_stop_price,
                    candidate,
                )
        else:
            candidate = position.lowest_price * (1 + self.config.trailing_stop_pct)
            if position.trailing_stop_price is None:
                position.trailing_stop_price = candidate
            else:
                position.trailing_stop_price = min(
                    position.trailing_stop_price,
                    candidate,
                )

    def _close_quantity(
        self,
        position: ManagedPosition,
        *,
        quantity: float,
        price: float,
        reason: ExitReason,
        close_position: bool,
    ) -> PositionAction:
        quantity = min(float(quantity), position.remaining_quantity)
        if quantity <= 0:
            raise ValueError("Kapatılacak quantity pozitif olmalıdır.")

        if position.side == PositionSide.LONG:
            pnl = (price - position.entry_price) * quantity
            action_name = "SELL"
        else:
            pnl = (position.entry_price - price) * quantity
            action_name = "BUY_TO_COVER"

        position.remaining_quantity -= quantity
        position.realized_pnl += pnl
        if close_position or position.remaining_quantity <= 1e-12:
            position.remaining_quantity = 0.0
            position.closed = True

        action = PositionAction(
            symbol=position.symbol,
            reason=reason,
            action=action_name,
            quantity=quantity,
            price=float(price),
            pnl=float(pnl),
            close_position=position.closed,
        )
        self.actions.append(action)

        if self.daily_risk is not None:
            self.daily_risk.realized_pnl += pnl
            if self.daily_risk.loss_pct >= self.config.daily_loss_limit_pct:
                self.daily_risk.blocked = True

        return action

    def evaluate(
        self,
        symbol: str,
        *,
        price: float,
    ) -> List[PositionAction]:
        if price <= 0:
            raise ValueError("price pozitif olmalıdır.")

        position = self.get_position(symbol)
        if position.closed:
            return []

        actions: List[PositionAction] = []
        self._update_extremes(position, price)
        self._activate_break_even(position, price)
        self._update_trailing_stop(position, price)

        if self.daily_risk is not None and self.daily_risk.blocked:
            actions.append(
                self._close_quantity(
                    position,
                    quantity=position.remaining_quantity,
                    price=price,
                    reason=ExitReason.DAILY_LOSS_LIMIT,
                    close_position=True,
                )
            )
            return actions

        if (
            self.config.enable_partial_take_profit
            and not position.partial_taken
            and position.return_pct(price) >= self.config.partial_take_profit_pct
        ):
            qty = position.quantity * self.config.partial_close_ratio
            action = self._close_quantity(
                position,
                quantity=qty,
                price=price,
                reason=ExitReason.PARTIAL_TAKE_PROFIT,
                close_position=False,
            )
            position.partial_taken = True
            actions.append(action)
            if position.closed:
                return actions

        if position.side == PositionSide.LONG:
            if self.config.enable_stop_loss and price <= position.stop_price:
                reason = (
                    ExitReason.BREAK_EVEN
                    if position.break_even_active
                    else ExitReason.STOP_LOSS
                )
                actions.append(
                    self._close_quantity(
                        position,
                        quantity=position.remaining_quantity,
                        price=price,
                        reason=reason,
                        close_position=True,
                    )
                )
                return actions

            if (
                self.config.enable_trailing_stop
                and position.trailing_stop_price is not None
                and price <= position.trailing_stop_price
                and price > position.entry_price
            ):
                actions.append(
                    self._close_quantity(
                        position,
                        quantity=position.remaining_quantity,
                        price=price,
                        reason=ExitReason.TRAILING_STOP,
                        close_position=True,
                    )
                )
                return actions

            if (
                self.config.enable_take_profit
                and price >= position.take_profit_price
            ):
                actions.append(
                    self._close_quantity(
                        position,
                        quantity=position.remaining_quantity,
                        price=price,
                        reason=ExitReason.TAKE_PROFIT,
                        close_position=True,
                    )
                )
                return actions

        else:
            if self.config.enable_stop_loss and price >= position.stop_price:
                reason = (
                    ExitReason.BREAK_EVEN
                    if position.break_even_active
                    else ExitReason.STOP_LOSS
                )
                actions.append(
                    self._close_quantity(
                        position,
                        quantity=position.remaining_quantity,
                        price=price,
                        reason=reason,
                        close_position=True,
                    )
                )
                return actions

            if (
                self.config.enable_trailing_stop
                and position.trailing_stop_price is not None
                and price >= position.trailing_stop_price
                and price < position.entry_price
            ):
                actions.append(
                    self._close_quantity(
                        position,
                        quantity=position.remaining_quantity,
                        price=price,
                        reason=ExitReason.TRAILING_STOP,
                        close_position=True,
                    )
                )
                return actions

            if (
                self.config.enable_take_profit
                and price <= position.take_profit_price
            ):
                actions.append(
                    self._close_quantity(
                        position,
                        quantity=position.remaining_quantity,
                        price=price,
                        reason=ExitReason.TAKE_PROFIT,
                        close_position=True,
                    )
                )
                return actions

        return actions

    def manual_close(
        self,
        symbol: str,
        *,
        price: float,
    ) -> PositionAction:
        position = self.get_position(symbol)
        return self._close_quantity(
            position,
            quantity=position.remaining_quantity,
            price=price,
            reason=ExitReason.MANUAL,
            close_position=True,
        )

    def register_external_pnl(self, pnl: float) -> None:
        if self.daily_risk is None:
            raise RuntimeError("Önce start_trading_day çağrılmalıdır.")
        self.daily_risk.realized_pnl += float(pnl)
        if self.daily_risk.loss_pct >= self.config.daily_loss_limit_pct:
            self.daily_risk.blocked = True

    def can_open_new_position(self) -> bool:
        return not (self.daily_risk is not None and self.daily_risk.blocked)

    def open_positions(self) -> List[ManagedPosition]:
        return sorted(
            [
                position
                for position in self.positions.values()
                if not position.closed
            ],
            key=lambda item: item.symbol,
        )

    def dashboard(self) -> Dict[str, Any]:
        return {
            "config": asdict(self.config),
            "daily_risk": (
                self.daily_risk.to_dict()
                if self.daily_risk else None
            ),
            "open_position_count": len(self.open_positions()),
            "positions": {
                symbol: position.to_dict()
                for symbol, position in sorted(self.positions.items())
            },
            "action_count": len(self.actions),
            "actions": [action.to_dict() for action in self.actions],
        }
