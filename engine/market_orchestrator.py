from __future__ import annotations

import inspect
import time as time_module
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, Iterable, List, Optional

from engine.multi_asset_engine import (
    AssetType,
    MarketState,
    MultiAssetSymbolEngine,
    SymbolConfig,
    SymbolState,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PipelineStage(str, Enum):
    RECEIVED = "RECEIVED"
    SCANNED = "SCANNED"
    DECIDED = "DECIDED"
    RISK_APPROVED = "RISK_APPROVED"
    EXECUTED = "EXECUTED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


@dataclass(slots=True)
class OrchestratorSignal:
    symbol: str
    action: str
    score: float = 0.0
    reason: str = ""
    quantity: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.symbol = self.symbol.strip().upper()
        self.action = self.action.strip().upper()
        if not self.symbol:
            raise ValueError("symbol boş olamaz.")
        if self.action not in {"BUY", "SELL", "HOLD", "SKIP"}:
            raise ValueError("action BUY, SELL, HOLD veya SKIP olmalıdır.")
        if self.quantity < 0:
            raise ValueError("quantity negatif olamaz.")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PipelineResult:
    symbol: str
    asset_type: AssetType
    stage: PipelineStage
    started_at: datetime
    finished_at: datetime
    duration_ms: float
    signal: Optional[OrchestratorSignal] = None
    scanner_output: Any = None
    decision_output: Any = None
    risk_output: Any = None
    execution_output: Any = None
    error: str = ""

    @property
    def success(self) -> bool:
        return self.stage not in {PipelineStage.ERROR}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "asset_type": self.asset_type.value,
            "stage": self.stage.value,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "duration_ms": self.duration_ms,
            "signal": self.signal.to_dict() if self.signal else None,
            "scanner_output": self.scanner_output,
            "decision_output": self.decision_output,
            "risk_output": self.risk_output,
            "execution_output": (
                self.execution_output.to_dict()
                if hasattr(self.execution_output, "to_dict")
                else self.execution_output
            ),
            "error": self.error,
            "success": self.success,
        }


@dataclass(slots=True)
class SymbolPipelineMetrics:
    processed_count: int = 0
    executed_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    total_duration_ms: float = 0.0
    last_duration_ms: float = 0.0
    last_stage: str = ""
    last_error: str = ""
    last_processed_at: Optional[datetime] = None

    @property
    def average_duration_ms(self) -> float:
        if self.processed_count == 0:
            return 0.0
        return self.total_duration_ms / self.processed_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            "processed_count": self.processed_count,
            "executed_count": self.executed_count,
            "skipped_count": self.skipped_count,
            "error_count": self.error_count,
            "total_duration_ms": self.total_duration_ms,
            "last_duration_ms": self.last_duration_ms,
            "average_duration_ms": self.average_duration_ms,
            "last_stage": self.last_stage,
            "last_error": self.last_error,
            "last_processed_at": (
                self.last_processed_at.isoformat()
                if self.last_processed_at else None
            ),
        }


ScannerCallable = Callable[[SymbolState, Dict[str, Any]], Any]
DecisionCallable = Callable[[SymbolState, Any, Dict[str, Any]], Any]
RiskCallable = Callable[[SymbolState, OrchestratorSignal, Dict[str, Any]], Any]


class UnifiedMarketOrchestrator:
    def __init__(
        self,
        *,
        multi_asset_engine: Optional[MultiAssetSymbolEngine] = None,
        paper_trading_engine: Any = None,
        scanner: Optional[ScannerCallable] = None,
        decision_engine: Optional[DecisionCallable] = None,
        risk_engine: Optional[RiskCallable] = None,
    ) -> None:
        self.multi_asset_engine = multi_asset_engine or MultiAssetSymbolEngine()
        self.paper_trading_engine = paper_trading_engine
        self.scanner = scanner
        self.decision_engine = decision_engine
        self.risk_engine = risk_engine
        self.metrics: Dict[str, SymbolPipelineMetrics] = {}
        self.last_results: Dict[str, PipelineResult] = {}
        self.history: List[PipelineResult] = []

    async def _call(self, func: Callable[..., Any], *args: Any) -> Any:
        result = func(*args)
        if inspect.isawaitable(result):
            return await result
        return result

    def _get_metrics(self, symbol: str) -> SymbolPipelineMetrics:
        normalized = symbol.strip().upper()
        if normalized not in self.metrics:
            self.metrics[normalized] = SymbolPipelineMetrics()
        return self.metrics[normalized]

    def _normalize_signal(
        self,
        symbol: str,
        decision_output: Any,
    ) -> OrchestratorSignal:
        if isinstance(decision_output, OrchestratorSignal):
            return decision_output

        if isinstance(decision_output, dict):
            return OrchestratorSignal(
                symbol=symbol,
                action=str(
                    decision_output.get("action")
                    or decision_output.get("signal")
                    or decision_output.get("decision")
                    or "HOLD"
                ),
                score=float(decision_output.get("score", 0.0) or 0.0),
                reason=str(decision_output.get("reason", "")),
                quantity=float(decision_output.get("quantity", 0.0) or 0.0),
                metadata=dict(decision_output.get("metadata", {}) or {}),
            )

        if isinstance(decision_output, str):
            mapping = {
                "NET AL": "BUY",
                "AL": "BUY",
                "BUY": "BUY",
                "SAT": "SELL",
                "SELL": "SELL",
                "BEKLE": "HOLD",
                "İZLE": "HOLD",
                "IZLE": "HOLD",
                "HOLD": "HOLD",
            }
            return OrchestratorSignal(
                symbol=symbol,
                action=mapping.get(decision_output.strip().upper(), "HOLD"),
                reason=decision_output,
            )

        return OrchestratorSignal(symbol=symbol, action="HOLD")

    def _risk_approved(self, risk_output: Any) -> bool:
        if isinstance(risk_output, bool):
            return risk_output
        if isinstance(risk_output, dict):
            if "approved" in risk_output:
                return bool(risk_output["approved"])
            if "allowed" in risk_output:
                return bool(risk_output["allowed"])
        if hasattr(risk_output, "approved"):
            return bool(risk_output.approved)
        return bool(risk_output)

    def _risk_quantity(
        self,
        signal: OrchestratorSignal,
        risk_output: Any,
    ) -> float:
        if isinstance(risk_output, dict):
            quantity = risk_output.get("quantity")
            if quantity is not None:
                return float(quantity)
        if hasattr(risk_output, "quantity"):
            return float(risk_output.quantity)
        return signal.quantity

    async def process_symbol(
        self,
        symbol: str,
        *,
        market_data: Optional[Dict[str, Any]] = None,
        now: Optional[datetime] = None,
    ) -> PipelineResult:
        started_at = now or utc_now()
        perf_start = time_module.perf_counter()
        state = self.multi_asset_engine.get_state(symbol)
        data = dict(market_data or {})
        stage = PipelineStage.RECEIVED
        scanner_output = None
        decision_output = None
        risk_output = None
        execution_output = None
        signal: Optional[OrchestratorSignal] = None
        error = ""

        try:
            if not state.config.enabled:
                stage = PipelineStage.SKIPPED
            elif state.market_state not in {
                MarketState.ACTIVE,
                MarketState.PAUSED,
            }:
                stage = PipelineStage.SKIPPED
            else:
                if "price" in data and data["price"] is not None:
                    self.multi_asset_engine.update_price(
                        state.config.symbol,
                        float(data["price"]),
                        timestamp=started_at,
                    )

                if self.scanner is not None:
                    scanner_output = await self._call(
                        self.scanner,
                        state,
                        data,
                    )
                stage = PipelineStage.SCANNED
                state.scan_count += 1

                if self.decision_engine is not None:
                    decision_output = await self._call(
                        self.decision_engine,
                        state,
                        scanner_output,
                        data,
                    )
                else:
                    decision_output = scanner_output

                signal = self._normalize_signal(
                    state.config.symbol,
                    decision_output,
                )
                stage = PipelineStage.DECIDED
                state.decision_count += 1
                state.last_signal = signal.action
                state.last_decision = signal.reason or signal.action

                if signal.action in {"HOLD", "SKIP"}:
                    stage = PipelineStage.SKIPPED
                else:
                    if self.risk_engine is not None:
                        risk_output = await self._call(
                            self.risk_engine,
                            state,
                            signal,
                            data,
                        )
                    else:
                        risk_output = {
                            "approved": True,
                            "quantity": signal.quantity,
                        }

                    if not self._risk_approved(risk_output):
                        stage = PipelineStage.SKIPPED
                    else:
                        stage = PipelineStage.RISK_APPROVED
                        quantity = self._risk_quantity(signal, risk_output)

                        if quantity <= 0:
                            stage = PipelineStage.SKIPPED
                        elif self.paper_trading_engine is None:
                            stage = PipelineStage.SKIPPED
                        else:
                            market_price = (
                                data.get("price")
                                or state.last_price
                            )
                            if market_price is None:
                                raise ValueError(
                                    f"{state.config.symbol} için market price yok."
                                )

                            execution_output = self.paper_trading_engine.submit_signal(
                                symbol=state.config.symbol,
                                action=signal.action,
                                quantity=quantity,
                                market_price=float(market_price),
                                reason=signal.reason,
                                strategy=str(
                                    signal.metadata.get("strategy", "")
                                ),
                                metadata={
                                    **signal.metadata,
                                    "asset_type": state.config.asset_type.value,
                                    "timeframe": state.config.timeframe,
                                },
                                timestamp=started_at,
                            )
                            state.order_count += 1
                            stage = PipelineStage.EXECUTED

        except Exception as exc:
            stage = PipelineStage.ERROR
            error = str(exc)
            state.register_error(exc)

        finished_at = utc_now()
        duration_ms = (time_module.perf_counter() - perf_start) * 1000.0
        result = PipelineResult(
            symbol=state.config.symbol,
            asset_type=state.config.asset_type,
            stage=stage,
            started_at=started_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            signal=signal,
            scanner_output=scanner_output,
            decision_output=decision_output,
            risk_output=risk_output,
            execution_output=execution_output,
            error=error,
        )

        self.last_results[state.config.symbol] = result
        self.history.append(result)
        metrics = self._get_metrics(state.config.symbol)
        metrics.processed_count += 1
        metrics.total_duration_ms += duration_ms
        metrics.last_duration_ms = duration_ms
        metrics.last_stage = stage.value
        metrics.last_error = error
        metrics.last_processed_at = finished_at
        if stage == PipelineStage.EXECUTED:
            metrics.executed_count += 1
        elif stage == PipelineStage.SKIPPED:
            metrics.skipped_count += 1
        elif stage == PipelineStage.ERROR:
            metrics.error_count += 1

        return result

    async def process_many(
        self,
        market_data_by_symbol: Dict[str, Dict[str, Any]],
        *,
        now: Optional[datetime] = None,
    ) -> Dict[str, PipelineResult]:
        results: Dict[str, PipelineResult] = {}
        for symbol, market_data in market_data_by_symbol.items():
            try:
                results[symbol.strip().upper()] = await self.process_symbol(
                    symbol,
                    market_data=market_data,
                    now=now,
                )
            except Exception as exc:
                normalized = symbol.strip().upper()
                state = self.multi_asset_engine.get_state(normalized)
                timestamp = now or utc_now()
                result = PipelineResult(
                    symbol=normalized,
                    asset_type=state.config.asset_type,
                    stage=PipelineStage.ERROR,
                    started_at=timestamp,
                    finished_at=utc_now(),
                    duration_ms=0.0,
                    error=str(exc),
                )
                results[normalized] = result
                self.last_results[normalized] = result
                self.history.append(result)
        return results

    def add_symbol(self, config: SymbolConfig) -> SymbolState:
        return self.multi_asset_engine.add_symbol(config)

    def add_symbols(self, configs: Iterable[SymbolConfig]) -> List[SymbolState]:
        return self.multi_asset_engine.add_symbols(configs)

    def metrics_summary(self) -> Dict[str, Any]:
        total_processed = sum(
            item.processed_count for item in self.metrics.values()
        )
        total_executed = sum(
            item.executed_count for item in self.metrics.values()
        )
        total_skipped = sum(
            item.skipped_count for item in self.metrics.values()
        )
        total_errors = sum(
            item.error_count for item in self.metrics.values()
        )
        total_duration = sum(
            item.total_duration_ms for item in self.metrics.values()
        )
        return {
            "total_processed": total_processed,
            "total_executed": total_executed,
            "total_skipped": total_skipped,
            "total_errors": total_errors,
            "average_duration_ms": (
                total_duration / total_processed
                if total_processed else 0.0
            ),
        }

    def dashboard(self) -> Dict[str, Any]:
        return {
            "summary": self.metrics_summary(),
            "multi_asset": self.multi_asset_engine.dashboard(),
            "metrics": {
                symbol: metrics.to_dict()
                for symbol, metrics in sorted(self.metrics.items())
            },
            "last_results": {
                symbol: result.to_dict()
                for symbol, result in sorted(self.last_results.items())
            },
            "history_count": len(self.history),
        }
