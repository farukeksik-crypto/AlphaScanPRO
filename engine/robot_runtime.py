from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Protocol
import time
import traceback

from engine.live_market_data import (
    KlineUpdate,
    MarketDataEvent,
    MarketDataEventType,
)


class RuntimeStatus(str, Enum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class RuntimeAction(str, Enum):
    HOLD = "HOLD"
    BUY = "BUY"
    SELL = "SELL"
    SKIP = "SKIP"
    ERROR = "ERROR"


@dataclass
class RuntimeConfig:
    symbols: list[str]
    intervals: list[str] = field(default_factory=lambda: ["1h"])
    process_only_closed_klines: bool = True
    loop_sleep_seconds: float = 0.0
    max_consecutive_errors: int = 5
    watchdog_timeout_seconds: float = 120.0
    max_cycle_history: int = 1_000

    def validate(self) -> None:
        if not self.symbols:
            raise ValueError("En az bir sembol gereklidir.")
        if not self.intervals:
            raise ValueError("En az bir zaman aralığı gereklidir.")
        if self.loop_sleep_seconds < 0:
            raise ValueError("loop_sleep_seconds negatif olamaz.")
        if self.max_consecutive_errors < 1:
            raise ValueError("max_consecutive_errors en az 1 olmalıdır.")
        if self.watchdog_timeout_seconds <= 0:
            raise ValueError("watchdog_timeout_seconds 0'dan büyük olmalıdır.")
        if self.max_cycle_history <= 0:
            raise ValueError("max_cycle_history 0'dan büyük olmalıdır.")


@dataclass
class StrategyDecision:
    symbol: str
    action: RuntimeAction
    score: float = 0.0
    reason: str = ""
    quantity: float | None = None
    price: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuntimeCycleResult:
    cycle_id: int
    symbol: str
    interval: str
    action: RuntimeAction
    score: float
    reason: str
    accepted: bool
    order_result: Any = None
    error: str | None = None
    started_at: float = 0.0
    finished_at: float = 0.0

    @property
    def duration_seconds(self) -> float:
        return max(0.0, self.finished_at - self.started_at)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["action"] = self.action.value
        data["duration_seconds"] = self.duration_seconds
        return data


@dataclass
class RuntimeHealth:
    status: RuntimeStatus
    started_at: float | None
    last_cycle_at: float | None
    last_event_at: float | None
    cycle_count: int
    processed_event_count: int
    skipped_event_count: int
    error_count: int
    consecutive_errors: int
    watchdog_ok: bool
    symbols: list[str]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


class StrategyProtocol(Protocol):
    def evaluate(
        self,
        *,
        symbol: str,
        interval: str,
        kline: KlineUpdate,
        context: dict[str, Any],
    ) -> StrategyDecision:
        ...


class RiskGateProtocol(Protocol):
    def approve(
        self,
        decision: StrategyDecision,
        context: dict[str, Any],
    ) -> tuple[bool, str]:
        ...


class ExecutionProtocol(Protocol):
    def execute(
        self,
        decision: StrategyDecision,
        context: dict[str, Any],
    ) -> Any:
        ...


class HoldStrategy:
    def evaluate(
        self,
        *,
        symbol: str,
        interval: str,
        kline: KlineUpdate,
        context: dict[str, Any],
    ) -> StrategyDecision:
        return StrategyDecision(
            symbol=symbol,
            action=RuntimeAction.HOLD,
            score=0.0,
            reason="Varsayılan HOLD stratejisi.",
            price=kline.close,
        )


class AllowAllRiskGate:
    def approve(
        self,
        decision: StrategyDecision,
        context: dict[str, Any],
    ) -> tuple[bool, str]:
        return True, "Risk gate onayladı."


class NoopExecution:
    def execute(
        self,
        decision: StrategyDecision,
        context: dict[str, Any],
    ) -> Any:
        return {
            "status": "NOOP",
            "symbol": decision.symbol,
            "action": decision.action.value,
        }


class RobotRuntime:
    def __init__(
        self,
        *,
        config: RuntimeConfig,
        market_data_engine: Any,
        strategy: StrategyProtocol | Callable[..., StrategyDecision] | None = None,
        risk_gate: RiskGateProtocol | Callable[..., tuple[bool, str]] | None = None,
        execution: ExecutionProtocol | Callable[..., Any] | None = None,
        time_fn: Callable[[], float] = time.time,
        sleep_fn: Callable[[float], None] = time.sleep,
        logger: Callable[[str], None] | None = None,
    ) -> None:
        config.validate()
        self.config = config
        self.market_data_engine = market_data_engine
        self.strategy = strategy or HoldStrategy()
        self.risk_gate = risk_gate or AllowAllRiskGate()
        self.execution = execution or NoopExecution()
        self.time_fn = time_fn
        self.sleep_fn = sleep_fn
        self.logger = logger or (lambda message: None)

        self.status = RuntimeStatus.STOPPED
        self.started_at: float | None = None
        self.last_cycle_at: float | None = None
        self.last_event_at: float | None = None
        self.stop_requested = False
        self.pause_requested = False

        self.cycle_count = 0
        self.processed_event_count = 0
        self.skipped_event_count = 0
        self.error_count = 0
        self.consecutive_errors = 0
        self.cycle_history: list[RuntimeCycleResult] = []

        self._processed_klines: set[tuple[str, str, int]] = set()
        self._callbacks_bound = False

    def bind_market_data(self) -> None:
        if self._callbacks_bound:
            return
        self.market_data_engine.add_callback(self.on_market_event)
        self._callbacks_bound = True

    def start(self, *, max_messages: int | None = None) -> int:
        if self.status == RuntimeStatus.RUNNING:
            return 0

        self.status = RuntimeStatus.STARTING
        self.stop_requested = False
        self.pause_requested = False
        self.started_at = self.time_fn()
        self.bind_market_data()
        self.status = RuntimeStatus.RUNNING
        self.logger("Robot runtime başlatıldı.")

        processed = 0
        while not self.stop_requested:
            if max_messages is not None and processed >= max_messages:
                break

            if self.pause_requested:
                self.status = RuntimeStatus.PAUSED
                if self.config.loop_sleep_seconds > 0:
                    self.sleep_fn(self.config.loop_sleep_seconds)
                continue

            self.status = RuntimeStatus.RUNNING
            try:
                event = self.market_data_engine.run_once()
                if event is not None:
                    processed += 1
                if self.config.loop_sleep_seconds > 0:
                    self.sleep_fn(self.config.loop_sleep_seconds)
            except (KeyboardInterrupt, SystemExit):
                self.stop()
                raise
            except Exception as exc:
                self._record_runtime_error(exc)
                if self.consecutive_errors >= self.config.max_consecutive_errors:
                    self.status = RuntimeStatus.FAILED
                    self.logger("Maksimum ardışık hata sayısına ulaşıldı.")
                    break

        if self.status != RuntimeStatus.FAILED:
            self.status = RuntimeStatus.STOPPED
        return processed

    def stop(self) -> None:
        self.stop_requested = True
        try:
            self.market_data_engine.disconnect()
        except Exception:
            pass
        self.status = RuntimeStatus.STOPPED
        self.logger("Robot runtime durduruldu.")

    def pause(self) -> None:
        self.pause_requested = True
        self.status = RuntimeStatus.PAUSED
        self.logger("Robot runtime duraklatıldı.")

    def resume(self) -> None:
        self.pause_requested = False
        if not self.stop_requested:
            self.status = RuntimeStatus.RUNNING
        self.logger("Robot runtime devam ediyor.")

    def on_market_event(self, event: MarketDataEvent) -> RuntimeCycleResult | None:
        self.last_event_at = self.time_fn()

        if event.event_type != MarketDataEventType.KLINE:
            self.skipped_event_count += 1
            return None

        kline = event.payload
        if self.config.process_only_closed_klines and not kline.closed:
            self.skipped_event_count += 1
            return None

        if event.symbol not in self.normalized_symbols:
            self.skipped_event_count += 1
            return None

        if kline.interval not in self.config.intervals:
            self.skipped_event_count += 1
            return None

        dedupe_key = (event.symbol, kline.interval, kline.open_time)
        if dedupe_key in self._processed_klines:
            self.skipped_event_count += 1
            return None
        self._processed_klines.add(dedupe_key)

        return self.process_kline(event.symbol, kline)

    def process_kline(
        self,
        symbol: str,
        kline: KlineUpdate,
    ) -> RuntimeCycleResult:
        started_at = self.time_fn()
        self.cycle_count += 1
        self.last_cycle_at = started_at

        context = self.build_context(symbol=symbol, kline=kline)

        try:
            decision = self._evaluate_strategy(
                symbol=symbol,
                interval=kline.interval,
                kline=kline,
                context=context,
            )
            accepted, gate_reason = self._approve_risk(decision, context)

            order_result = None
            final_reason = decision.reason
            if gate_reason:
                final_reason = f"{decision.reason} | {gate_reason}".strip(" |")

            if accepted and decision.action in {
                RuntimeAction.BUY,
                RuntimeAction.SELL,
            }:
                order_result = self._execute(decision, context)

            result = RuntimeCycleResult(
                cycle_id=self.cycle_count,
                symbol=symbol,
                interval=kline.interval,
                action=decision.action,
                score=decision.score,
                reason=final_reason,
                accepted=accepted,
                order_result=order_result,
                started_at=started_at,
                finished_at=self.time_fn(),
            )
            self.processed_event_count += 1
            self.consecutive_errors = 0
            self._append_result(result)
            return result

        except Exception as exc:
            self.error_count += 1
            self.consecutive_errors += 1
            result = RuntimeCycleResult(
                cycle_id=self.cycle_count,
                symbol=symbol,
                interval=kline.interval,
                action=RuntimeAction.ERROR,
                score=0.0,
                reason="Runtime cycle hatası.",
                accepted=False,
                error=f"{type(exc).__name__}: {exc}",
                started_at=started_at,
                finished_at=self.time_fn(),
            )
            self._append_result(result)
            self.logger(result.error or "Bilinmeyen runtime hatası.")
            return result

    def build_context(
        self,
        *,
        symbol: str,
        kline: KlineUpdate,
    ) -> dict[str, Any]:
        state = getattr(self.market_data_engine, "state", None)
        snapshot = state.snapshot() if state and hasattr(state, "snapshot") else {}
        return {
            "runtime_status": self.status.value,
            "symbol": symbol,
            "interval": kline.interval,
            "kline": kline.to_dict(),
            "market_snapshot": snapshot,
            "health": self.health_report().to_dict(),
        }

    def health_report(self) -> RuntimeHealth:
        now = self.time_fn()
        reference = self.last_cycle_at or self.last_event_at or self.started_at
        watchdog_ok = (
            reference is not None
            and now - reference <= self.config.watchdog_timeout_seconds
        )
        return RuntimeHealth(
            status=self.status,
            started_at=self.started_at,
            last_cycle_at=self.last_cycle_at,
            last_event_at=self.last_event_at,
            cycle_count=self.cycle_count,
            processed_event_count=self.processed_event_count,
            skipped_event_count=self.skipped_event_count,
            error_count=self.error_count,
            consecutive_errors=self.consecutive_errors,
            watchdog_ok=watchdog_ok,
            symbols=sorted(self.normalized_symbols),
        )

    @property
    def normalized_symbols(self) -> set[str]:
        return {
            symbol.replace("/", "").replace("-", "").upper()
            for symbol in self.config.symbols
        }

    def recent_results(self, limit: int = 20) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        return [item.to_dict() for item in self.cycle_history[-limit:]]

    def _evaluate_strategy(
        self,
        *,
        symbol: str,
        interval: str,
        kline: KlineUpdate,
        context: dict[str, Any],
    ) -> StrategyDecision:
        if hasattr(self.strategy, "evaluate"):
            decision = self.strategy.evaluate(
                symbol=symbol,
                interval=interval,
                kline=kline,
                context=context,
            )
        else:
            decision = self.strategy(
                symbol=symbol,
                interval=interval,
                kline=kline,
                context=context,
            )
        if not isinstance(decision, StrategyDecision):
            raise TypeError("Strategy sonucu StrategyDecision olmalıdır.")
        return decision

    def _approve_risk(
        self,
        decision: StrategyDecision,
        context: dict[str, Any],
    ) -> tuple[bool, str]:
        if hasattr(self.risk_gate, "approve"):
            result = self.risk_gate.approve(decision, context)
        else:
            result = self.risk_gate(decision, context)
        if not isinstance(result, tuple) or len(result) != 2:
            raise TypeError("Risk gate sonucu (bool, reason) olmalıdır.")
        return bool(result[0]), str(result[1])

    def _execute(
        self,
        decision: StrategyDecision,
        context: dict[str, Any],
    ) -> Any:
        if hasattr(self.execution, "execute"):
            return self.execution.execute(decision, context)
        return self.execution(decision, context)

    def _append_result(self, result: RuntimeCycleResult) -> None:
        self.cycle_history.append(result)
        if len(self.cycle_history) > self.config.max_cycle_history:
            del self.cycle_history[
                : len(self.cycle_history) - self.config.max_cycle_history
            ]

    def _record_runtime_error(self, exc: Exception) -> None:
        self.error_count += 1
        self.consecutive_errors += 1
        self.status = RuntimeStatus.DEGRADED
        self.logger(
            f"Runtime loop hatası: {type(exc).__name__}: {exc}\n"
            f"{traceback.format_exc()}"
        )
