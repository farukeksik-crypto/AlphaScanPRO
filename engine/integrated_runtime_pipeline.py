from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Protocol

from engine.intelligent_decision_filter import (
    DecisionVerdict,
    IntelligentDecisionFilter,
)
from engine.multi_timeframe_confirmation import (
    MultiTimeframeConfirmationEngine,
    TimeframeVerdict,
)
from engine.robot_runtime import RuntimeAction, StrategyDecision
from engine.smart_position_manager import (
    PositionPlan,
    SmartPositionManager,
)


class PipelineStage(str, Enum):
    RECEIVED = "RECEIVED"
    DECISION_FILTER = "DECISION_FILTER"
    MULTI_TIMEFRAME = "MULTI_TIMEFRAME"
    EXECUTION = "EXECUTION"
    POSITION_MANAGER = "POSITION_MANAGER"
    SYNC = "SYNC"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


class PipelineStatus(str, Enum):
    EXECUTED = "EXECUTED"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


class ExecutionProtocol(Protocol):
    def execute(
        self,
        decision: StrategyDecision,
        market_context: dict[str, Any],
    ) -> Any:
        ...


class SyncProtocol(Protocol):
    def sync_all(self) -> Any:
        ...


@dataclass
class IntegratedRuntimeConfig:
    enabled: bool = True
    require_market_price: bool = True
    require_atr_for_position: bool = True
    auto_open_position: bool = True
    auto_sync_after_execution: bool = True
    continue_when_sync_fails: bool = True
    block_duplicate_open_position: bool = True
    allowed_actions: tuple[RuntimeAction, ...] = (
        RuntimeAction.BUY,
        RuntimeAction.SELL,
    )

    def validate(self) -> None:
        if not self.allowed_actions:
            raise ValueError("En az bir işlem aksiyonu tanımlanmalıdır.")
        if any(not isinstance(item, RuntimeAction) for item in self.allowed_actions):
            raise ValueError("allowed_actions RuntimeAction değerlerinden oluşmalıdır.")


@dataclass
class StageRecord:
    stage: PipelineStage
    success: bool
    message: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["stage"] = self.stage.value
        return data


@dataclass
class PipelineResult:
    symbol: str
    status: PipelineStatus
    original_decision: StrategyDecision
    final_decision: StrategyDecision
    stages: list[StageRecord]
    execution_result: Any = None
    position: PositionPlan | None = None
    sync_result: Any = None
    error: str | None = None

    @property
    def executed(self) -> bool:
        return self.status == PipelineStatus.EXECUTED

    @property
    def blocked(self) -> bool:
        return self.status == PipelineStatus.BLOCKED

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "status": self.status.value,
            "original_decision": _decision_to_dict(self.original_decision),
            "final_decision": _decision_to_dict(self.final_decision),
            "stages": [item.to_dict() for item in self.stages],
            "execution_result": _safe_payload(self.execution_result),
            "position": self.position.to_dict() if self.position else None,
            "sync_result": _safe_payload(self.sync_result),
            "error": self.error,
            "executed": self.executed,
            "blocked": self.blocked,
        }


class IntegratedRuntimePipeline:
    def __init__(
        self,
        *,
        decision_filter: IntelligentDecisionFilter,
        timeframe_engine: MultiTimeframeConfirmationEngine,
        position_manager: SmartPositionManager,
        execution_engine: ExecutionProtocol | Any,
        sync_manager: SyncProtocol | Any | None = None,
        config: IntegratedRuntimeConfig | None = None,
    ) -> None:
        self.decision_filter = decision_filter
        self.timeframe_engine = timeframe_engine
        self.position_manager = position_manager
        self.execution_engine = execution_engine
        self.sync_manager = sync_manager
        self.config = config or IntegratedRuntimeConfig()
        self.config.validate()
        self.history: list[PipelineResult] = []

    def process(
        self,
        decision: StrategyDecision,
        *,
        market_context: dict[str, Any] | None = None,
        timeframe_signals: dict[str, Any] | None = None,
    ) -> PipelineResult:
        market_context = dict(market_context or {})
        timeframe_signals = dict(timeframe_signals or {})
        stages: list[StageRecord] = [
            StageRecord(
                stage=PipelineStage.RECEIVED,
                success=True,
                message="Strateji kararı runtime hattına alındı.",
                payload={"decision": _decision_to_dict(decision)},
            )
        ]

        if not self.config.enabled:
            result = self._result(
                decision=decision,
                final_decision=decision,
                status=PipelineStatus.SKIPPED,
                stages=stages
                + [
                    StageRecord(
                        PipelineStage.COMPLETED,
                        True,
                        "Runtime entegrasyonu devre dışı.",
                    )
                ],
            )
            return self._remember(result)

        if decision.action not in self.config.allowed_actions:
            result = self._result(
                decision=decision,
                final_decision=decision,
                status=PipelineStatus.SKIPPED,
                stages=stages
                + [
                    StageRecord(
                        PipelineStage.COMPLETED,
                        True,
                        "BUY/SELL dışındaki karar için execution uygulanmadı.",
                    )
                ],
            )
            return self._remember(result)

        try:
            self._validate_market_context(market_context)
            self._validate_duplicate_position(decision)

            filter_result = self.decision_filter.evaluate(decision, market_context)
            filtered_decision = filter_result.filtered_decision
            stages.append(
                StageRecord(
                    PipelineStage.DECISION_FILTER,
                    filter_result.verdict != DecisionVerdict.REJECTED,
                    f"Akıllı filtre sonucu: {filter_result.verdict.value}",
                    filter_result.to_dict(),
                )
            )
            if filter_result.verdict == DecisionVerdict.REJECTED:
                stages.append(
                    StageRecord(
                        PipelineStage.BLOCKED,
                        True,
                        "İşlem akıllı karar filtresinde engellendi.",
                    )
                )
                return self._remember(
                    self._result(
                        decision=decision,
                        final_decision=filtered_decision,
                        status=PipelineStatus.BLOCKED,
                        stages=stages,
                    )
                )

            mtf_result = self.timeframe_engine.evaluate(
                filtered_decision,
                timeframe_signals,
            )
            final_decision = mtf_result.filtered_decision
            stages.append(
                StageRecord(
                    PipelineStage.MULTI_TIMEFRAME,
                    mtf_result.verdict != TimeframeVerdict.REJECTED,
                    f"Çoklu zaman dilimi sonucu: {mtf_result.verdict.value}",
                    mtf_result.to_dict(),
                )
            )
            if mtf_result.verdict == TimeframeVerdict.REJECTED:
                stages.append(
                    StageRecord(
                        PipelineStage.BLOCKED,
                        True,
                        "İşlem çoklu zaman dilimi kontrolünde engellendi.",
                    )
                )
                return self._remember(
                    self._result(
                        decision=decision,
                        final_decision=final_decision,
                        status=PipelineStatus.BLOCKED,
                        stages=stages,
                    )
                )

            execution_result = self._execute(final_decision, market_context)
            stages.append(
                StageRecord(
                    PipelineStage.EXECUTION,
                    True,
                    "Emir execution katmanına iletildi.",
                    _safe_payload(execution_result),
                )
            )

            position = None
            if self.config.auto_open_position:
                position = self._open_position(
                    final_decision,
                    execution_result,
                    market_context,
                )
                stages.append(
                    StageRecord(
                        PipelineStage.POSITION_MANAGER,
                        True,
                        "Akıllı pozisyon yönetimi başlatıldı.",
                        position.to_dict(),
                    )
                )

            sync_result = None
            if self.sync_manager is not None and self.config.auto_sync_after_execution:
                try:
                    sync_result = self._sync()
                    stages.append(
                        StageRecord(
                            PipelineStage.SYNC,
                            True,
                            "Execution sonrası senkronizasyon tamamlandı.",
                            _safe_payload(sync_result),
                        )
                    )
                except Exception as sync_exc:
                    stages.append(
                        StageRecord(
                            PipelineStage.SYNC,
                            False,
                            f"Senkronizasyon hatası: {sync_exc}",
                        )
                    )
                    if not self.config.continue_when_sync_fails:
                        raise

            stages.append(
                StageRecord(
                    PipelineStage.COMPLETED,
                    True,
                    "Uçtan uca işlem hattı tamamlandı.",
                )
            )
            return self._remember(
                self._result(
                    decision=decision,
                    final_decision=final_decision,
                    status=PipelineStatus.EXECUTED,
                    stages=stages,
                    execution_result=execution_result,
                    position=position,
                    sync_result=sync_result,
                )
            )

        except Exception as exc:
            stages.append(
                StageRecord(
                    PipelineStage.FAILED,
                    False,
                    f"Runtime pipeline hatası: {exc}",
                )
            )
            return self._remember(
                self._result(
                    decision=decision,
                    final_decision=decision,
                    status=PipelineStatus.FAILED,
                    stages=stages,
                    error=str(exc),
                )
            )

    def on_price(self, symbol: str, price: float) -> dict[str, Any]:
        update = self.position_manager.update_position(symbol, price)
        return update.to_dict()

    def dashboard(self, limit: int = 100) -> dict[str, Any]:
        items = self.history[-limit:] if limit > 0 else self.history
        counts = {status.value: 0 for status in PipelineStatus}
        for item in items:
            counts[item.status.value] += 1
        return {
            "total_runs": len(items),
            "counts": counts,
            "open_positions": self.position_manager.dashboard(),
            "decision_filter": self.decision_filter.summary(limit=limit),
            "multi_timeframe": self.timeframe_engine.summary(limit=limit),
            "recent_runs": [item.to_dict() for item in items[-20:]],
        }

    def clear_history(self) -> None:
        self.history.clear()

    def _execute(
        self,
        decision: StrategyDecision,
        market_context: dict[str, Any],
    ) -> Any:
        if hasattr(self.execution_engine, "execute"):
            return self.execution_engine.execute(decision, market_context)
        if hasattr(self.execution_engine, "process"):
            return self.execution_engine.process(decision, market_context)
        if callable(self.execution_engine):
            return self.execution_engine(decision, market_context)
        raise TypeError("Execution engine execute/process metodu sağlamıyor.")

    def _sync(self) -> Any:
        if hasattr(self.sync_manager, "sync_all"):
            return self.sync_manager.sync_all()
        if hasattr(self.sync_manager, "synchronize"):
            return self.sync_manager.synchronize()
        if callable(self.sync_manager):
            return self.sync_manager()
        raise TypeError("Sync manager sync_all/synchronize metodu sağlamıyor.")

    def _open_position(
        self,
        decision: StrategyDecision,
        execution_result: Any,
        market_context: dict[str, Any],
    ) -> PositionPlan:
        payload = _safe_payload(execution_result)
        symbol = str(payload.get("symbol") or decision.symbol)
        side = payload.get("side") or payload.get("action") or decision.action.value
        price = (
            payload.get("average_price")
            or payload.get("avg_price")
            or payload.get("price")
            or decision.price
            or market_context.get("price")
        )
        quantity = (
            payload.get("executed_quantity")
            or payload.get("filled_quantity")
            or payload.get("quantity")
            or decision.quantity
        )
        atr = market_context.get("atr")

        if price is None:
            raise ValueError("Pozisyon açmak için execution fiyatı bulunamadı.")
        if quantity is None or float(quantity) <= 0:
            raise ValueError("Pozisyon açmak için gerçekleşen miktar bulunamadı.")
        if self.config.require_atr_for_position and atr is None:
            raise ValueError("Pozisyon yönetimi için ATR gereklidir.")
        if atr is None:
            atr = max(float(price) * 0.01, 1e-9)

        return self.position_manager.create_position(
            symbol=symbol,
            side=side,
            entry_price=float(price),
            quantity=float(quantity),
            atr=float(atr),
            metadata={
                "pipeline": True,
                "execution_result": payload,
            },
        )

    def _validate_market_context(self, market_context: dict[str, Any]) -> None:
        if self.config.require_market_price:
            price = market_context.get("price")
            if price is None or float(price) <= 0:
                raise ValueError("Geçerli market_context.price gereklidir.")

    def _validate_duplicate_position(self, decision: StrategyDecision) -> None:
        if not self.config.block_duplicate_open_position:
            return
        if self.position_manager.get_position(decision.symbol) is not None:
            raise ValueError(
                f"Aynı sembolde açık pozisyon mevcut: {decision.symbol}"
            )

    def _result(
        self,
        *,
        decision: StrategyDecision,
        final_decision: StrategyDecision,
        status: PipelineStatus,
        stages: list[StageRecord],
        execution_result: Any = None,
        position: PositionPlan | None = None,
        sync_result: Any = None,
        error: str | None = None,
    ) -> PipelineResult:
        return PipelineResult(
            symbol=self.position_manager.normalize_symbol(decision.symbol),
            status=status,
            original_decision=decision,
            final_decision=final_decision,
            stages=stages,
            execution_result=execution_result,
            position=position,
            sync_result=sync_result,
            error=error,
        )

    def _remember(self, result: PipelineResult) -> PipelineResult:
        self.history.append(result)
        return result


def _decision_to_dict(decision: StrategyDecision) -> dict[str, Any]:
    return {
        "symbol": decision.symbol,
        "action": decision.action.value,
        "score": decision.score,
        "reason": decision.reason,
        "quantity": decision.quantity,
        "price": decision.price,
        "metadata": dict(decision.metadata),
    }


def _safe_payload(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "to_dict"):
        result = value.to_dict()
        return dict(result) if isinstance(result, dict) else {"value": result}
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    return {"value": value}
