from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Iterable

from engine.live_robot_core import SignalEvent
from engine.robot_orchestrator import RobotPaperOrchestrator


@dataclass
class StrategyAdapterConfig:
    buy_labels: tuple[str, ...] = ("NET AL", "AL ADAY", "BUY")
    minimum_score: float = 60.0
    default_market: str = "CRYPTO"
    default_sector: str | None = None
    stop_loss_pct: float = 5.0
    take_profit_pct: float = 10.0
    requested_quantity: float = 1_000.0


@dataclass
class AdaptedSignal:
    accepted: bool
    code: str
    reason: str
    signal: SignalEvent | None = None
    market_price: float | None = None
    stop_price: float | None = None
    take_profit: float | None = None
    requested_quantity: float = 0.0
    sector: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.signal is not None:
            data["signal"] = self.signal.to_dict()
        return data


@dataclass
class ScanCycleResult:
    cycle_id: int
    scanned_count: int
    adapted_count: int
    executed_count: int
    rejected_count: int
    errors: list[str]
    decisions: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StrategySignalAdapter:
    def __init__(
        self,
        config: StrategyAdapterConfig | None = None,
    ) -> None:
        self.config = config or StrategyAdapterConfig()

    def adapt(self, row: dict[str, Any]) -> AdaptedSignal:
        symbol = self._first(row, "symbol", "Symbol", "Kod", "Hisse")
        decision = self._first(
            row,
            "decision",
            "Decision",
            "Karar",
            "signal",
            "Signal",
        )
        score = self._number(
            self._first(row, "score", "Score", "Puan"),
            default=0.0,
        )
        price = self._number(
            self._first(row, "price", "Price", "Fiyat", "close", "Close"),
            default=0.0,
        )
        market = str(
            self._first(row, "market", "Market")
            or self.config.default_market
        ).upper()
        sector = self._first(row, "sector", "Sector", "Sektor")
        if sector is None:
            sector = self.config.default_sector

        if not symbol:
            return self._reject("MISSING_SYMBOL", "Sembol bulunamadı.", row)

        if not decision:
            return self._reject("MISSING_DECISION", "Karar bulunamadı.", row)

        normalized_decision = str(decision).strip().upper()
        allowed_labels = {
            label.strip().upper()
            for label in self.config.buy_labels
        }
        if normalized_decision not in allowed_labels:
            return self._reject(
                "NON_BUY_DECISION",
                "Tarama kararı alış sinyali değil.",
                row,
            )

        if score < self.config.minimum_score:
            return self._reject(
                "SCORE_TOO_LOW",
                "Tarama puanı minimum eşik altında.",
                row,
            )

        if price <= 0:
            return self._reject(
                "INVALID_PRICE",
                "Geçerli fiyat bulunamadı.",
                row,
            )

        stop_price = self._number(
            self._first(row, "stop_price", "Stop", "stop", "Stop Fiyat"),
            default=price * (1 - self.config.stop_loss_pct / 100),
        )
        take_profit = self._number(
            self._first(
                row,
                "take_profit",
                "Target",
                "Hedef",
                "target_price",
            ),
            default=price * (1 + self.config.take_profit_pct / 100),
        )
        requested_quantity = self._number(
            self._first(
                row,
                "requested_quantity",
                "quantity",
                "Quantity",
                "Miktar",
            ),
            default=self.config.requested_quantity,
        )

        if stop_price <= 0 or stop_price >= price:
            return self._reject(
                "INVALID_STOP",
                "Stop fiyatı giriş fiyatından düşük ve pozitif olmalıdır.",
                row,
            )
        if take_profit <= price:
            return self._reject(
                "INVALID_TARGET",
                "Hedef fiyat giriş fiyatından yüksek olmalıdır.",
                row,
            )
        if requested_quantity <= 0:
            return self._reject(
                "INVALID_QUANTITY",
                "İstenen miktar 0'dan büyük olmalıdır.",
                row,
            )

        signal = SignalEvent(
            symbol=str(symbol),
            market=market,
            signal="BUY",
            score=float(score),
            metadata={
                "source": "strategy_adapter",
                "decision": normalized_decision,
                "raw": dict(row),
            },
        )

        return AdaptedSignal(
            accepted=True,
            code="ADAPTED",
            reason="Tarama sonucu standart BUY sinyaline dönüştürüldü.",
            signal=signal,
            market_price=float(price),
            stop_price=float(stop_price),
            take_profit=float(take_profit),
            requested_quantity=float(requested_quantity),
            sector=None if sector is None else str(sector),
            raw=dict(row),
        )

    def adapt_many(
        self,
        rows: Iterable[dict[str, Any]],
    ) -> list[AdaptedSignal]:
        return [self.adapt(dict(row)) for row in rows]

    @staticmethod
    def _first(row: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in row and row[key] is not None:
                return row[key]
        return None

    @staticmethod
    def _number(value: Any, *, default: float) -> float:
        if value is None:
            return float(default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    @staticmethod
    def _reject(
        code: str,
        reason: str,
        row: dict[str, Any],
    ) -> AdaptedSignal:
        return AdaptedSignal(
            accepted=False,
            code=code,
            reason=reason,
            raw=dict(row),
        )


class ScanCycleEngine:
    def __init__(
        self,
        *,
        orchestrator: RobotPaperOrchestrator,
        scanner: Callable[[], Iterable[dict[str, Any]]],
        adapter: StrategySignalAdapter | None = None,
    ) -> None:
        self.orchestrator = orchestrator
        self.scanner = scanner
        self.adapter = adapter or StrategySignalAdapter()
        self.cycle_count = 0
        self.history: list[dict[str, Any]] = []

    def run_cycle(
        self,
        *,
        initial_equity: float,
        starting_equity: float,
        current_equity: float,
        daily_trade_count: int,
        consecutive_losses: int,
        current_total_risk_pct: float,
        correlations_by_symbol: dict[str, dict[str, float]] | None = None,
        available_liquidity_by_symbol: dict[str, float] | None = None,
    ) -> ScanCycleResult:
        self.cycle_count += 1
        raw_rows = list(self.scanner())
        decisions: list[dict[str, Any]] = []
        errors: list[str] = []
        adapted_count = 0
        executed_count = 0
        rejected_count = 0

        for index, raw in enumerate(raw_rows):
            try:
                adapted = self.adapter.adapt(dict(raw))
                if not adapted.accepted:
                    rejected_count += 1
                    decisions.append(
                        {
                            "index": index,
                            "adapter": adapted.to_dict(),
                            "orchestrator": None,
                        }
                    )
                    continue

                adapted_count += 1
                symbol = adapted.signal.symbol
                result = self.orchestrator.process_signal(
                    signal=adapted.signal,
                    market_price=float(adapted.market_price),
                    stop_price=float(adapted.stop_price),
                    requested_quantity=float(adapted.requested_quantity),
                    initial_equity=initial_equity,
                    starting_equity=starting_equity,
                    current_equity=current_equity,
                    daily_trade_count=daily_trade_count + executed_count,
                    consecutive_losses=consecutive_losses,
                    current_total_risk_pct=current_total_risk_pct,
                    sector=adapted.sector,
                    minimum_signal_score=self.adapter.config.minimum_score,
                    correlations=(
                        correlations_by_symbol or {}
                    ).get(symbol, {}),
                    take_profit=adapted.take_profit,
                    available_liquidity=(
                        available_liquidity_by_symbol or {}
                    ).get(symbol),
                )

                if result.accepted:
                    executed_count += 1
                else:
                    rejected_count += 1

                decisions.append(
                    {
                        "index": index,
                        "adapter": adapted.to_dict(),
                        "orchestrator": result.to_dict(),
                    }
                )
            except Exception as exc:
                message = f"Satır {index}: {exc}"
                errors.append(message)
                rejected_count += 1
                decisions.append(
                    {
                        "index": index,
                        "adapter": None,
                        "orchestrator": None,
                        "error": message,
                        "raw": dict(raw),
                    }
                )

        result = ScanCycleResult(
            cycle_id=self.cycle_count,
            scanned_count=len(raw_rows),
            adapted_count=adapted_count,
            executed_count=executed_count,
            rejected_count=rejected_count,
            errors=errors,
            decisions=decisions,
        )
        self.history.append(result.to_dict())
        return result

    def cycle_report(self) -> dict[str, Any]:
        return {
            "cycle_count": self.cycle_count,
            "history": list(self.history),
            "orchestrator": self.orchestrator.combined_report(),
        }
