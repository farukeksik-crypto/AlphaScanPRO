from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class PositionSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class PositionStatus(str, Enum):
    OPEN = "OPEN"
    PARTIAL = "PARTIAL"
    CLOSED = "CLOSED"


class ExitReason(str, Enum):
    NONE = "NONE"
    STOP_LOSS = "STOP_LOSS"
    TRAILING_STOP = "TRAILING_STOP"
    TAKE_PROFIT_1 = "TAKE_PROFIT_1"
    TAKE_PROFIT_2 = "TAKE_PROFIT_2"
    TAKE_PROFIT_3 = "TAKE_PROFIT_3"
    MANUAL = "MANUAL"


@dataclass
class SmartPositionConfig:
    atr_stop_multiplier: float = 2.0
    risk_reward_target_1: float = 1.0
    risk_reward_target_2: float = 2.0
    risk_reward_target_3: float = 3.0
    target_1_close_ratio: float = 0.40
    target_2_close_ratio: float = 0.30
    target_3_close_ratio: float = 0.30
    break_even_trigger_r: float = 1.0
    break_even_buffer_r: float = 0.10
    trailing_activation_r: float = 1.5
    trailing_distance_r: float = 0.75
    minimum_atr: float = 1e-9

    def validate(self) -> None:
        if self.atr_stop_multiplier <= 0:
            raise ValueError("atr_stop_multiplier pozitif olmalıdır.")
        if not (
            0 < self.risk_reward_target_1
            < self.risk_reward_target_2
            < self.risk_reward_target_3
        ):
            raise ValueError("Hedef risk/ödül seviyeleri artan sırada olmalıdır.")
        ratios = (
            self.target_1_close_ratio,
            self.target_2_close_ratio,
            self.target_3_close_ratio,
        )
        if any(ratio < 0 or ratio > 1 for ratio in ratios):
            raise ValueError("Hedef satış oranları 0-1 arasında olmalıdır.")
        if abs(sum(ratios) - 1.0) > 1e-9:
            raise ValueError("Hedef satış oranları toplamı 1 olmalıdır.")
        if self.break_even_trigger_r <= 0:
            raise ValueError("break_even_trigger_r pozitif olmalıdır.")
        if self.break_even_buffer_r < 0:
            raise ValueError("break_even_buffer_r negatif olamaz.")
        if self.trailing_activation_r <= 0:
            raise ValueError("trailing_activation_r pozitif olmalıdır.")
        if self.trailing_distance_r <= 0:
            raise ValueError("trailing_distance_r pozitif olmalıdır.")
        if self.minimum_atr <= 0:
            raise ValueError("minimum_atr pozitif olmalıdır.")


@dataclass
class PositionPlan:
    symbol: str
    side: PositionSide
    entry_price: float
    initial_quantity: float
    remaining_quantity: float
    atr: float
    initial_stop: float
    current_stop: float
    target_1: float
    target_2: float
    target_3: float
    highest_price: float
    lowest_price: float
    status: PositionStatus = PositionStatus.OPEN
    target_1_hit: bool = False
    target_2_hit: bool = False
    target_3_hit: bool = False
    break_even_active: bool = False
    trailing_active: bool = False
    realized_quantity: float = 0.0
    realized_pnl: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def risk_per_unit(self) -> float:
        return abs(self.entry_price - self.initial_stop)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["side"] = self.side.value
        data["status"] = self.status.value
        data["risk_per_unit"] = self.risk_per_unit
        return data


@dataclass
class PositionEvent:
    symbol: str
    event_type: str
    price: float
    quantity: float
    remaining_quantity: float
    pnl: float
    reason: ExitReason
    stop_price: float
    message: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["reason"] = self.reason.value
        return data


@dataclass
class PositionUpdate:
    position: PositionPlan
    events: list[PositionEvent]
    closed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "position": self.position.to_dict(),
            "events": [event.to_dict() for event in self.events],
            "closed": self.closed,
        }


class SmartPositionManager:
    def __init__(self, config: SmartPositionConfig | None = None) -> None:
        self.config = config or SmartPositionConfig()
        self.config.validate()
        self.positions: dict[str, PositionPlan] = {}
        self.event_history: list[PositionEvent] = []

    def create_position(
        self,
        *,
        symbol: str,
        side: PositionSide | str,
        entry_price: float,
        quantity: float,
        atr: float,
        metadata: dict[str, Any] | None = None,
    ) -> PositionPlan:
        normalized_symbol = self.normalize_symbol(symbol)
        parsed_side = self.parse_side(side)

        if entry_price <= 0:
            raise ValueError("entry_price pozitif olmalıdır.")
        if quantity <= 0:
            raise ValueError("quantity pozitif olmalıdır.")
        if atr < self.config.minimum_atr:
            raise ValueError("ATR değeri yetersiz.")

        risk_distance = atr * self.config.atr_stop_multiplier
        direction = 1.0 if parsed_side == PositionSide.LONG else -1.0

        initial_stop = entry_price - direction * risk_distance
        target_1 = entry_price + direction * risk_distance * self.config.risk_reward_target_1
        target_2 = entry_price + direction * risk_distance * self.config.risk_reward_target_2
        target_3 = entry_price + direction * risk_distance * self.config.risk_reward_target_3

        position = PositionPlan(
            symbol=normalized_symbol,
            side=parsed_side,
            entry_price=float(entry_price),
            initial_quantity=float(quantity),
            remaining_quantity=float(quantity),
            atr=float(atr),
            initial_stop=float(initial_stop),
            current_stop=float(initial_stop),
            target_1=float(target_1),
            target_2=float(target_2),
            target_3=float(target_3),
            highest_price=float(entry_price),
            lowest_price=float(entry_price),
            metadata=dict(metadata or {}),
        )
        self.positions[normalized_symbol] = position
        return position

    def update_position(
        self,
        symbol: str,
        current_price: float,
    ) -> PositionUpdate:
        normalized_symbol = self.normalize_symbol(symbol)
        if normalized_symbol not in self.positions:
            raise KeyError(f"Açık pozisyon bulunamadı: {normalized_symbol}")
        if current_price <= 0:
            raise ValueError("current_price pozitif olmalıdır.")

        position = self.positions[normalized_symbol]
        if position.status == PositionStatus.CLOSED:
            return PositionUpdate(position=position, events=[], closed=True)

        position.highest_price = max(position.highest_price, current_price)
        position.lowest_price = min(position.lowest_price, current_price)

        events: list[PositionEvent] = []

        stop_event = self._check_stop(position, current_price)
        if stop_event is not None:
            events.append(stop_event)
            self._record_events(events)
            return PositionUpdate(position=position, events=events, closed=True)

        self._activate_break_even(position, current_price)
        self._update_trailing_stop(position, current_price)

        events.extend(self._check_targets(position, current_price))

        if position.remaining_quantity <= 1e-12:
            position.remaining_quantity = 0.0
            position.status = PositionStatus.CLOSED
            self.positions.pop(normalized_symbol, None)
        elif position.realized_quantity > 0:
            position.status = PositionStatus.PARTIAL

        self._record_events(events)
        return PositionUpdate(
            position=position,
            events=events,
            closed=position.status == PositionStatus.CLOSED,
        )

    def manual_close(
        self,
        symbol: str,
        price: float,
        quantity: float | None = None,
    ) -> PositionEvent:
        normalized_symbol = self.normalize_symbol(symbol)
        if normalized_symbol not in self.positions:
            raise KeyError(f"Açık pozisyon bulunamadı: {normalized_symbol}")
        position = self.positions[normalized_symbol]

        close_quantity = (
            position.remaining_quantity
            if quantity is None
            else min(float(quantity), position.remaining_quantity)
        )
        if close_quantity <= 0:
            raise ValueError("Kapatılacak miktar pozitif olmalıdır.")

        event = self._close_quantity(
            position=position,
            price=price,
            quantity=close_quantity,
            reason=ExitReason.MANUAL,
            event_type="MANUAL_CLOSE",
            message="Pozisyon manuel olarak kapatıldı.",
        )
        self._finalize_if_empty(position)
        self._record_events([event])
        return event

    def get_position(self, symbol: str) -> PositionPlan | None:
        return self.positions.get(self.normalize_symbol(symbol))

    def dashboard(self) -> dict[str, Any]:
        return {
            "open_position_count": len(self.positions),
            "positions": [item.to_dict() for item in self.positions.values()],
            "recent_events": [item.to_dict() for item in self.event_history[-100:]],
            "total_realized_pnl": round(
                sum(event.pnl for event in self.event_history),
                8,
            ),
        }

    def _check_stop(
        self,
        position: PositionPlan,
        price: float,
    ) -> PositionEvent | None:
        hit = (
            price <= position.current_stop
            if position.side == PositionSide.LONG
            else price >= position.current_stop
        )
        if not hit:
            return None

        reason = (
            ExitReason.TRAILING_STOP
            if position.trailing_active
            else ExitReason.STOP_LOSS
        )
        event = self._close_quantity(
            position=position,
            price=price,
            quantity=position.remaining_quantity,
            reason=reason,
            event_type="STOP",
            message=f"Pozisyon {reason.value} nedeniyle kapatıldı.",
        )
        self._finalize_if_empty(position)
        return event

    def _activate_break_even(
        self,
        position: PositionPlan,
        price: float,
    ) -> None:
        if position.break_even_active:
            return

        r_multiple = self._r_multiple(position, price)
        if r_multiple < self.config.break_even_trigger_r:
            return

        buffer = position.risk_per_unit * self.config.break_even_buffer_r
        if position.side == PositionSide.LONG:
            new_stop = position.entry_price + buffer
            position.current_stop = max(position.current_stop, new_stop)
        else:
            new_stop = position.entry_price - buffer
            position.current_stop = min(position.current_stop, new_stop)

        position.break_even_active = True

    def _update_trailing_stop(
        self,
        position: PositionPlan,
        price: float,
    ) -> None:
        r_multiple = self._r_multiple(position, price)
        if r_multiple < self.config.trailing_activation_r:
            return

        position.trailing_active = True
        distance = position.risk_per_unit * self.config.trailing_distance_r

        if position.side == PositionSide.LONG:
            candidate = position.highest_price - distance
            position.current_stop = max(position.current_stop, candidate)
        else:
            candidate = position.lowest_price + distance
            position.current_stop = min(position.current_stop, candidate)

    def _check_targets(
        self,
        position: PositionPlan,
        price: float,
    ) -> list[PositionEvent]:
        events: list[PositionEvent] = []

        checks = [
            (
                "target_1_hit",
                position.target_1,
                self.config.target_1_close_ratio,
                ExitReason.TAKE_PROFIT_1,
            ),
            (
                "target_2_hit",
                position.target_2,
                self.config.target_2_close_ratio,
                ExitReason.TAKE_PROFIT_2,
            ),
            (
                "target_3_hit",
                position.target_3,
                self.config.target_3_close_ratio,
                ExitReason.TAKE_PROFIT_3,
            ),
        ]

        for attr_name, target, ratio, reason in checks:
            if getattr(position, attr_name):
                continue
            reached = (
                price >= target
                if position.side == PositionSide.LONG
                else price <= target
            )
            if not reached:
                continue

            quantity = min(
                position.initial_quantity * ratio,
                position.remaining_quantity,
            )
            if quantity <= 0:
                setattr(position, attr_name, True)
                continue

            event = self._close_quantity(
                position=position,
                price=target,
                quantity=quantity,
                reason=reason,
                event_type="TAKE_PROFIT",
                message=f"{reason.value} seviyesi gerçekleşti.",
            )
            setattr(position, attr_name, True)
            events.append(event)

        self._finalize_if_empty(position)
        return events

    def _close_quantity(
        self,
        *,
        position: PositionPlan,
        price: float,
        quantity: float,
        reason: ExitReason,
        event_type: str,
        message: str,
    ) -> PositionEvent:
        pnl_per_unit = (
            price - position.entry_price
            if position.side == PositionSide.LONG
            else position.entry_price - price
        )
        pnl = pnl_per_unit * quantity

        position.remaining_quantity = max(
            0.0,
            position.remaining_quantity - quantity,
        )
        position.realized_quantity += quantity
        position.realized_pnl += pnl

        return PositionEvent(
            symbol=position.symbol,
            event_type=event_type,
            price=float(price),
            quantity=float(quantity),
            remaining_quantity=float(position.remaining_quantity),
            pnl=float(pnl),
            reason=reason,
            stop_price=float(position.current_stop),
            message=message,
        )

    def _finalize_if_empty(self, position: PositionPlan) -> None:
        if position.remaining_quantity <= 1e-12:
            position.remaining_quantity = 0.0
            position.status = PositionStatus.CLOSED
            self.positions.pop(position.symbol, None)
        elif position.realized_quantity > 0:
            position.status = PositionStatus.PARTIAL

    def _record_events(self, events: list[PositionEvent]) -> None:
        self.event_history.extend(events)

    @staticmethod
    def _r_multiple(position: PositionPlan, price: float) -> float:
        risk = position.risk_per_unit
        if risk <= 0:
            return 0.0
        move = (
            price - position.entry_price
            if position.side == PositionSide.LONG
            else position.entry_price - price
        )
        return move / risk

    @staticmethod
    def parse_side(value: PositionSide | str) -> PositionSide:
        if isinstance(value, PositionSide):
            return value
        text = str(value).upper()
        aliases = {
            "BUY": PositionSide.LONG,
            "LONG": PositionSide.LONG,
            "SELL": PositionSide.SHORT,
            "SHORT": PositionSide.SHORT,
        }
        if text not in aliases:
            raise ValueError(f"Geçersiz pozisyon yönü: {value}")
        return aliases[text]

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        return symbol.replace("/", "").replace("-", "").upper()


class SmartPositionRuntimeBridge:
    def __init__(self, manager: SmartPositionManager) -> None:
        self.manager = manager

    def open_from_execution(
        self,
        execution_result: dict[str, Any],
        market_context: dict[str, Any],
    ) -> PositionPlan:
        side = execution_result.get("side") or execution_result.get("action")
        return self.manager.create_position(
            symbol=str(execution_result["symbol"]),
            side=side,
            entry_price=float(
                execution_result.get("price")
                or market_context["price"]
            ),
            quantity=float(
                execution_result.get("executed_quantity")
                or execution_result.get("quantity")
            ),
            atr=float(market_context["atr"]),
            metadata={
                "execution_result": dict(execution_result),
            },
        )

    def on_price(self, symbol: str, price: float) -> dict[str, Any]:
        return self.manager.update_position(symbol, price).to_dict()

    def dashboard(self) -> dict[str, Any]:
        return self.manager.dashboard()
