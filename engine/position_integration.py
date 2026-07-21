from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from engine.market_orchestrator import PipelineResult, PipelineStage
from engine.position_management import (
    ManagedPosition,
    PositionAction,
    PositionManagementEngine,
    PositionSide,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class IntegrationResult:
    symbol: str
    entry_result: Optional[PipelineResult] = None
    exit_actions: List[PositionAction] = None
    synchronized: bool = False
    error: str = ""

    def __post_init__(self) -> None:
        if self.exit_actions is None:
            self.exit_actions = []

    @property
    def success(self) -> bool:
        return not self.error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "entry_result": (
                self.entry_result.to_dict()
                if self.entry_result is not None else None
            ),
            "exit_actions": [
                action.to_dict() for action in self.exit_actions
            ],
            "synchronized": self.synchronized,
            "error": self.error,
            "success": self.success,
        }


class PositionManagementIntegration:
    def __init__(
        self,
        *,
        orchestrator: Any,
        position_manager: Optional[PositionManagementEngine] = None,
        paper_trading_engine: Any = None,
    ) -> None:
        self.orchestrator = orchestrator
        self.position_manager = (
            position_manager or PositionManagementEngine()
        )
        self.paper_trading_engine = (
            paper_trading_engine
            if paper_trading_engine is not None
            else getattr(orchestrator, "paper_trading_engine", None)
        )
        self.processed_count = 0
        self.entry_count = 0
        self.exit_count = 0
        self.error_count = 0
        self.last_results: Dict[str, IntegrationResult] = {}

    def _extract_execution_data(
        self,
        pipeline_result: PipelineResult,
    ) -> Dict[str, Any]:
        execution = pipeline_result.execution_output
        if execution is None:
            return {}

        if isinstance(execution, dict):
            return dict(execution)

        if hasattr(execution, "to_dict"):
            return dict(execution.to_dict())

        return {
            key: getattr(execution, key)
            for key in (
                "symbol",
                "action",
                "quantity",
                "price",
                "fill_price",
                "market_price",
                "timestamp",
            )
            if hasattr(execution, key)
        }

    def _resolve_fill_price(
        self,
        execution_data: Dict[str, Any],
        fallback_price: float,
    ) -> float:
        for key in ("fill_price", "price", "market_price"):
            value = execution_data.get(key)
            if value is not None:
                return float(value)
        return float(fallback_price)

    def _resolve_quantity(
        self,
        pipeline_result: PipelineResult,
        execution_data: Dict[str, Any],
    ) -> float:
        quantity = execution_data.get("quantity")
        if quantity is not None:
            return float(quantity)

        if pipeline_result.signal is not None:
            return float(pipeline_result.signal.quantity)

        return 0.0

    def synchronize_entry(
        self,
        pipeline_result: PipelineResult,
        *,
        market_price: float,
        timestamp: Optional[datetime] = None,
    ) -> bool:
        if pipeline_result.stage != PipelineStage.EXECUTED:
            return False
        if pipeline_result.signal is None:
            return False

        action = pipeline_result.signal.action.upper()
        if action not in {"BUY", "SELL"}:
            return False

        symbol = pipeline_result.symbol
        existing = self.position_manager.positions.get(symbol)
        if existing is not None and not existing.closed:
            return False

        execution_data = self._extract_execution_data(pipeline_result)
        quantity = self._resolve_quantity(
            pipeline_result,
            execution_data,
        )
        if quantity <= 0:
            return False

        fill_price = self._resolve_fill_price(
            execution_data,
            market_price,
        )
        side = (
            PositionSide.LONG
            if action == "BUY"
            else PositionSide.SHORT
        )

        self.position_manager.open_position(
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=fill_price,
            opened_at=timestamp or utc_now(),
            metadata={
                "source": "UnifiedMarketOrchestrator",
                "pipeline_stage": pipeline_result.stage.value,
                "signal_reason": pipeline_result.signal.reason,
                "signal_score": pipeline_result.signal.score,
            },
        )
        self.entry_count += 1
        return True

    def _submit_exit_action(
        self,
        action: PositionAction,
        *,
        timestamp: Optional[datetime] = None,
    ) -> Any:
        if self.paper_trading_engine is None:
            return None

        submit_signal = getattr(
            self.paper_trading_engine,
            "submit_signal",
            None,
        )
        if submit_signal is None:
            raise AttributeError(
                "Paper Trading Engine submit_signal metoduna sahip değil."
            )

        return submit_signal(
            symbol=action.symbol,
            action=action.action,
            quantity=action.quantity,
            market_price=action.price,
            reason=action.reason.value,
            strategy="POSITION_MANAGEMENT",
            metadata={
                "position_management": True,
                "close_position": action.close_position,
                "pnl": action.pnl,
            },
            timestamp=timestamp or utc_now(),
        )

    def evaluate_position(
        self,
        symbol: str,
        *,
        market_price: float,
        timestamp: Optional[datetime] = None,
    ) -> List[PositionAction]:
        actions = self.position_manager.evaluate(
            symbol,
            price=market_price,
        )
        for action in actions:
            self._submit_exit_action(
                action,
                timestamp=timestamp,
            )
            self.exit_count += 1
        return actions

    async def process_symbol(
        self,
        symbol: str,
        *,
        market_data: Dict[str, Any],
        now: Optional[datetime] = None,
    ) -> IntegrationResult:
        normalized = symbol.strip().upper()
        result = IntegrationResult(symbol=normalized)
        timestamp = now or utc_now()

        try:
            if "price" not in market_data:
                raise ValueError(
                    f"{normalized} için market_data price alanı gerekli."
                )

            market_price = float(market_data["price"])
            existing = self.position_manager.positions.get(normalized)

            if existing is not None and not existing.closed:
                result.exit_actions = self.evaluate_position(
                    normalized,
                    market_price=market_price,
                    timestamp=timestamp,
                )

            if (
                existing is None
                or existing.closed
            ) and self.position_manager.can_open_new_position():
                result.entry_result = await self.orchestrator.process_symbol(
                    normalized,
                    market_data=market_data,
                    now=timestamp,
                )
                result.synchronized = self.synchronize_entry(
                    result.entry_result,
                    market_price=market_price,
                    timestamp=timestamp,
                )

        except Exception as exc:
            result.error = str(exc)
            self.error_count += 1

        self.processed_count += 1
        self.last_results[normalized] = result
        return result

    async def process_many(
        self,
        market_data_by_symbol: Dict[str, Dict[str, Any]],
        *,
        now: Optional[datetime] = None,
    ) -> Dict[str, IntegrationResult]:
        results: Dict[str, IntegrationResult] = {}
        for symbol, market_data in market_data_by_symbol.items():
            results[symbol.strip().upper()] = await self.process_symbol(
                symbol,
                market_data=market_data,
                now=now,
            )
        return results

    def sync_existing_positions(
        self,
        positions: Iterable[Dict[str, Any]],
    ) -> List[ManagedPosition]:
        synced: List[ManagedPosition] = []

        for item in positions:
            symbol = str(item["symbol"]).strip().upper()
            quantity = float(item["quantity"])
            entry_price = float(item["entry_price"])
            side_raw = str(item.get("side", "LONG")).upper()
            side = PositionSide(side_raw)

            existing = self.position_manager.positions.get(symbol)
            if existing is not None and not existing.closed:
                continue

            synced.append(
                self.position_manager.open_position(
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    entry_price=entry_price,
                    opened_at=item.get("opened_at") or utc_now(),
                    metadata=dict(item.get("metadata", {}) or {}),
                )
            )

        return synced

    def dashboard(self) -> Dict[str, Any]:
        return {
            "processed_count": self.processed_count,
            "entry_count": self.entry_count,
            "exit_count": self.exit_count,
            "error_count": self.error_count,
            "position_management": self.position_manager.dashboard(),
            "last_results": {
                symbol: result.to_dict()
                for symbol, result in sorted(self.last_results.items())
            },
        }
