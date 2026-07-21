from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, time, timezone
from enum import Enum
from typing import Any, Callable, Dict, Iterable, List, Optional


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AssetType(str, Enum):
    CRYPTO = "CRYPTO"
    STOCK = "STOCK"
    COMMODITY = "COMMODITY"


class MarketState(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    CLOSED = "CLOSED"
    ERROR = "ERROR"


@dataclass(slots=True)
class MarketSession:
    timezone_name: str = "UTC"
    open_time: Optional[time] = None
    close_time: Optional[time] = None
    weekdays: tuple[int, ...] = (0, 1, 2, 3, 4, 5, 6)
    always_open: bool = False

    def is_open(self, now: datetime) -> bool:
        if self.always_open:
            return True

        if now.weekday() not in self.weekdays:
            return False

        if self.open_time is None or self.close_time is None:
            return True

        current = now.timetz().replace(tzinfo=None)

        if self.open_time <= self.close_time:
            return self.open_time <= current <= self.close_time

        return current >= self.open_time or current <= self.close_time


@dataclass(slots=True)
class SymbolConfig:
    symbol: str
    asset_type: AssetType
    enabled: bool = True
    quote_currency: str = ""
    timeframe: str = "1h"
    source: str = ""
    session: Optional[MarketSession] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.symbol = self.symbol.strip().upper()
        if not self.symbol:
            raise ValueError("symbol boş olamaz.")
        if not self.timeframe.strip():
            raise ValueError("timeframe boş olamaz.")

        if self.session is None:
            if self.asset_type == AssetType.CRYPTO:
                self.session = MarketSession(always_open=True)
            elif self.asset_type == AssetType.STOCK:
                self.session = MarketSession(
                    open_time=time(10, 0),
                    close_time=time(18, 10),
                    weekdays=(0, 1, 2, 3, 4),
                )
            else:
                self.session = MarketSession(
                    open_time=time(0, 0),
                    close_time=time(23, 59),
                    weekdays=(0, 1, 2, 3, 4),
                )

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["asset_type"] = self.asset_type.value
        session = self.session
        data["session"] = {
            "timezone_name": session.timezone_name,
            "open_time": session.open_time.isoformat() if session.open_time else None,
            "close_time": session.close_time.isoformat() if session.close_time else None,
            "weekdays": list(session.weekdays),
            "always_open": session.always_open,
        }
        return data


@dataclass(slots=True)
class SymbolState:
    config: SymbolConfig
    market_state: MarketState = MarketState.PAUSED
    last_price: Optional[float] = None
    last_update_at: Optional[datetime] = None
    last_signal: str = ""
    last_decision: str = ""
    position_quantity: float = 0.0
    average_price: float = 0.0
    error_count: int = 0
    last_error: str = ""
    scan_count: int = 0
    decision_count: int = 0
    order_count: int = 0

    def update_price(self, price: float, *, timestamp: Optional[datetime] = None) -> None:
        if price <= 0:
            raise ValueError("price pozitif olmalıdır.")
        self.last_price = float(price)
        self.last_update_at = timestamp or utc_now()

    def register_error(self, error: Exception | str) -> None:
        self.error_count += 1
        self.last_error = str(error)
        self.market_state = MarketState.ERROR

    def clear_error(self) -> None:
        self.last_error = ""
        if self.market_state == MarketState.ERROR:
            self.market_state = MarketState.PAUSED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "market_state": self.market_state.value,
            "last_price": self.last_price,
            "last_update_at": (
                self.last_update_at.isoformat()
                if self.last_update_at else None
            ),
            "last_signal": self.last_signal,
            "last_decision": self.last_decision,
            "position_quantity": self.position_quantity,
            "average_price": self.average_price,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "scan_count": self.scan_count,
            "decision_count": self.decision_count,
            "order_count": self.order_count,
        }


@dataclass(slots=True)
class MultiAssetEngineStats:
    total_symbols: int = 0
    enabled_symbols: int = 0
    active_symbols: int = 0
    crypto_symbols: int = 0
    stock_symbols: int = 0
    commodity_symbols: int = 0
    total_scans: int = 0
    total_decisions: int = 0
    total_orders: int = 0
    total_errors: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MultiAssetSymbolEngine:
    def __init__(self) -> None:
        self._states: Dict[str, SymbolState] = {}
        self._handlers: Dict[AssetType, Callable[[SymbolState], Any]] = {}

    def add_symbol(self, config: SymbolConfig) -> SymbolState:
        if config.symbol in self._states:
            raise ValueError(f"Sembol zaten kayıtlı: {config.symbol}")
        state = SymbolState(config=config)
        self._states[config.symbol] = state
        return state

    def add_symbols(self, configs: Iterable[SymbolConfig]) -> List[SymbolState]:
        return [self.add_symbol(config) for config in configs]

    def remove_symbol(self, symbol: str) -> None:
        normalized = symbol.strip().upper()
        if normalized not in self._states:
            raise KeyError(normalized)
        self._states.pop(normalized)

    def get_state(self, symbol: str) -> SymbolState:
        normalized = symbol.strip().upper()
        if normalized not in self._states:
            raise KeyError(normalized)
        return self._states[normalized]

    def list_states(
        self,
        *,
        asset_type: Optional[AssetType] = None,
        enabled_only: bool = False,
    ) -> List[SymbolState]:
        states = list(self._states.values())
        if asset_type is not None:
            states = [
                state for state in states
                if state.config.asset_type == asset_type
            ]
        if enabled_only:
            states = [
                state for state in states
                if state.config.enabled
            ]
        return sorted(states, key=lambda item: item.config.symbol)

    def enable_symbol(self, symbol: str) -> None:
        self.get_state(symbol).config.enabled = True

    def disable_symbol(self, symbol: str) -> None:
        state = self.get_state(symbol)
        state.config.enabled = False
        state.market_state = MarketState.PAUSED

    def register_handler(
        self,
        asset_type: AssetType,
        handler: Callable[[SymbolState], Any],
    ) -> None:
        self._handlers[asset_type] = handler

    def refresh_market_states(
        self,
        *,
        now: Optional[datetime] = None,
    ) -> Dict[str, MarketState]:
        current = now or utc_now()
        output: Dict[str, MarketState] = {}

        for symbol, state in self._states.items():
            if not state.config.enabled:
                state.market_state = MarketState.PAUSED
            elif state.config.session and state.config.session.is_open(current):
                if state.market_state != MarketState.ERROR:
                    state.market_state = MarketState.ACTIVE
            else:
                state.market_state = MarketState.CLOSED
            output[symbol] = state.market_state

        return output

    def active_states(
        self,
        *,
        now: Optional[datetime] = None,
    ) -> List[SymbolState]:
        self.refresh_market_states(now=now)
        return [
            state for state in self.list_states(enabled_only=True)
            if state.market_state == MarketState.ACTIVE
        ]

    def update_price(
        self,
        symbol: str,
        price: float,
        *,
        timestamp: Optional[datetime] = None,
    ) -> SymbolState:
        state = self.get_state(symbol)
        state.update_price(price, timestamp=timestamp)
        return state

    def update_position(
        self,
        symbol: str,
        *,
        quantity: float,
        average_price: float,
    ) -> SymbolState:
        if average_price < 0:
            raise ValueError("average_price negatif olamaz.")
        state = self.get_state(symbol)
        state.position_quantity = float(quantity)
        state.average_price = float(average_price)
        return state

    def register_scan(
        self,
        symbol: str,
        *,
        signal: str = "",
        decision: str = "",
    ) -> SymbolState:
        state = self.get_state(symbol)
        state.scan_count += 1
        state.last_signal = signal
        if decision:
            state.decision_count += 1
            state.last_decision = decision
        return state

    def register_order(self, symbol: str) -> SymbolState:
        state = self.get_state(symbol)
        state.order_count += 1
        return state

    def process_active_symbols(
        self,
        *,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        results: Dict[str, Any] = {}
        for state in self.active_states(now=now):
            handler = self._handlers.get(state.config.asset_type)
            if handler is None:
                results[state.config.symbol] = None
                continue
            try:
                results[state.config.symbol] = handler(state)
            except Exception as exc:
                state.register_error(exc)
                results[state.config.symbol] = exc
        return results

    def grouped_symbols(self) -> Dict[str, List[str]]:
        return {
            asset_type.value: [
                state.config.symbol
                for state in self.list_states(asset_type=asset_type)
            ]
            for asset_type in AssetType
        }

    def stats(self) -> MultiAssetEngineStats:
        states = self.list_states()
        return MultiAssetEngineStats(
            total_symbols=len(states),
            enabled_symbols=sum(state.config.enabled for state in states),
            active_symbols=sum(
                state.market_state == MarketState.ACTIVE
                for state in states
            ),
            crypto_symbols=sum(
                state.config.asset_type == AssetType.CRYPTO
                for state in states
            ),
            stock_symbols=sum(
                state.config.asset_type == AssetType.STOCK
                for state in states
            ),
            commodity_symbols=sum(
                state.config.asset_type == AssetType.COMMODITY
                for state in states
            ),
            total_scans=sum(state.scan_count for state in states),
            total_decisions=sum(state.decision_count for state in states),
            total_orders=sum(state.order_count for state in states),
            total_errors=sum(state.error_count for state in states),
        )

    def dashboard(self) -> Dict[str, Any]:
        return {
            "stats": self.stats().to_dict(),
            "groups": self.grouped_symbols(),
            "symbols": {
                state.config.symbol: state.to_dict()
                for state in self.list_states()
            },
        }
