from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from engine.robot_runtime import RuntimeAction, StrategyDecision


class TimeframeTrend(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"


class TimeframeVerdict(str, Enum):
    CONFIRMED = "CONFIRMED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    SKIPPED = "SKIPPED"


@dataclass
class TimeframeRule:
    timeframe: str
    weight: float
    required: bool = False

    def validate(self) -> None:
        if not self.timeframe:
            raise ValueError("timeframe boş olamaz.")
        if self.weight <= 0:
            raise ValueError("timeframe weight pozitif olmalıdır.")


@dataclass
class MultiTimeframeConfig:
    enabled: bool = True
    minimum_confirmation_score: float = 60.0
    full_confirmation_score: float = 80.0
    partial_position_factor: float = 0.50
    reject_on_required_conflict: bool = True
    reject_on_daily_conflict: bool = True
    allow_unknown_optional: bool = True
    rules: list[TimeframeRule] = field(
        default_factory=lambda: [
            TimeframeRule("15m", 0.15, False),
            TimeframeRule("1h", 0.30, True),
            TimeframeRule("4h", 0.35, True),
            TimeframeRule("1d", 0.20, False),
        ]
    )

    def validate(self) -> None:
        if not 0 <= self.minimum_confirmation_score <= 100:
            raise ValueError("minimum_confirmation_score 0-100 arasında olmalıdır.")
        if not 0 <= self.full_confirmation_score <= 100:
            raise ValueError("full_confirmation_score 0-100 arasında olmalıdır.")
        if self.full_confirmation_score < self.minimum_confirmation_score:
            raise ValueError(
                "full_confirmation_score minimum_confirmation_score değerinden küçük olamaz."
            )
        if not 0 < self.partial_position_factor <= 1:
            raise ValueError("partial_position_factor 0-1 arasında olmalıdır.")
        if not self.rules:
            raise ValueError("En az bir timeframe kuralı gereklidir.")
        for rule in self.rules:
            rule.validate()


@dataclass
class TimeframeSignal:
    timeframe: str
    trend: TimeframeTrend
    score: float = 50.0
    close: float | None = None
    ema_fast: float | None = None
    ema_slow: float | None = None
    rsi: float | None = None
    adx: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["trend"] = self.trend.value
        return data


@dataclass
class TimeframeEvaluation:
    timeframe: str
    expected: TimeframeTrend
    actual: TimeframeTrend
    aligned: bool
    required: bool
    weight: float
    contribution: float
    detail: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["expected"] = self.expected.value
        data["actual"] = self.actual.value
        return data


@dataclass
class MultiTimeframeResult:
    symbol: str
    original_action: RuntimeAction
    final_action: RuntimeAction
    verdict: TimeframeVerdict
    confirmation_score: float
    position_factor: float
    reasons: list[str]
    evaluations: list[TimeframeEvaluation]
    filtered_decision: StrategyDecision

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "original_action": self.original_action.value,
            "final_action": self.final_action.value,
            "verdict": self.verdict.value,
            "confirmation_score": self.confirmation_score,
            "position_factor": self.position_factor,
            "reasons": list(self.reasons),
            "evaluations": [item.to_dict() for item in self.evaluations],
            "filtered_decision": {
                "symbol": self.filtered_decision.symbol,
                "action": self.filtered_decision.action.value,
                "score": self.filtered_decision.score,
                "reason": self.filtered_decision.reason,
                "quantity": self.filtered_decision.quantity,
                "price": self.filtered_decision.price,
                "metadata": dict(self.filtered_decision.metadata),
            },
        }


class MultiTimeframeConfirmationEngine:
    def __init__(self, config: MultiTimeframeConfig | None = None) -> None:
        self.config = config or MultiTimeframeConfig()
        self.config.validate()
        self.history: list[MultiTimeframeResult] = []

    def evaluate(
        self,
        decision: StrategyDecision,
        signals: dict[str, TimeframeSignal | dict[str, Any]] | None = None,
    ) -> MultiTimeframeResult:
        signals = signals or {}

        if decision.action not in {RuntimeAction.BUY, RuntimeAction.SELL}:
            result = self._build_result(
                decision=decision,
                verdict=TimeframeVerdict.SKIPPED,
                final_action=decision.action,
                confirmation_score=float(decision.score),
                position_factor=1.0,
                reasons=["İşlem kararı olmadığı için timeframe onayı uygulanmadı."],
                evaluations=[],
            )
            self.history.append(result)
            return result

        if not self.config.enabled:
            result = self._build_result(
                decision=decision,
                verdict=TimeframeVerdict.CONFIRMED,
                final_action=decision.action,
                confirmation_score=100.0,
                position_factor=1.0,
                reasons=["Çoklu zaman dilimi onayı devre dışı."],
                evaluations=[],
            )
            self.history.append(result)
            return result

        normalized = {
            self.normalize_timeframe(key): self._coerce_signal(key, value)
            for key, value in signals.items()
        }

        expected = (
            TimeframeTrend.BULLISH
            if decision.action == RuntimeAction.BUY
            else TimeframeTrend.BEARISH
        )

        evaluations: list[TimeframeEvaluation] = []
        hard_conflicts: list[str] = []
        weighted_sum = 0.0
        total_weight = 0.0

        for rule in self.config.rules:
            tf = self.normalize_timeframe(rule.timeframe)
            signal = normalized.get(tf)

            if signal is None:
                if rule.required:
                    hard_conflicts.append(f"Zorunlu {tf} timeframe verisi eksik.")
                evaluations.append(
                    TimeframeEvaluation(
                        timeframe=tf,
                        expected=expected,
                        actual=TimeframeTrend.UNKNOWN,
                        aligned=False,
                        required=rule.required,
                        weight=rule.weight,
                        contribution=0.0,
                        detail="Timeframe verisi bulunamadı.",
                    )
                )
                total_weight += rule.weight
                continue

            actual = signal.trend
            aligned = actual == expected
            unknown = actual == TimeframeTrend.UNKNOWN
            neutral = actual == TimeframeTrend.NEUTRAL

            if aligned:
                base_score = max(60.0, min(100.0, float(signal.score)))
                detail = f"{tf} trend uyumlu."
            elif unknown and self.config.allow_unknown_optional and not rule.required:
                base_score = 50.0
                detail = f"{tf} trend bilinmiyor, nötr kabul edildi."
            elif neutral:
                base_score = 40.0
                detail = f"{tf} trend nötr."
            else:
                base_score = 0.0
                detail = f"{tf} trend çelişkili: {actual.value}."

            if (
                rule.required
                and not aligned
                and self.config.reject_on_required_conflict
            ):
                hard_conflicts.append(f"Zorunlu {tf} timeframe trendi çelişkili.")

            if (
                tf == "1d"
                and actual not in {expected, TimeframeTrend.UNKNOWN, TimeframeTrend.NEUTRAL}
                and self.config.reject_on_daily_conflict
            ):
                hard_conflicts.append("Günlük trend ana işlem yönüyle çelişkili.")

            contribution = base_score * rule.weight
            weighted_sum += contribution
            total_weight += rule.weight

            evaluations.append(
                TimeframeEvaluation(
                    timeframe=tf,
                    expected=expected,
                    actual=actual,
                    aligned=aligned,
                    required=rule.required,
                    weight=rule.weight,
                    contribution=round(contribution, 4),
                    detail=detail,
                )
            )

        confirmation_score = (
            weighted_sum / total_weight if total_weight > 0 else 0.0
        )

        if hard_conflicts or confirmation_score < self.config.minimum_confirmation_score:
            reasons = list(dict.fromkeys(hard_conflicts))
            if confirmation_score < self.config.minimum_confirmation_score:
                reasons.append(
                    f"Timeframe onay puanı yetersiz: {confirmation_score:.1f}/100."
                )
            result = self._build_result(
                decision=decision,
                verdict=TimeframeVerdict.REJECTED,
                final_action=RuntimeAction.HOLD,
                confirmation_score=confirmation_score,
                position_factor=0.0,
                reasons=reasons,
                evaluations=evaluations,
            )
        elif confirmation_score < self.config.full_confirmation_score:
            result = self._build_result(
                decision=decision,
                verdict=TimeframeVerdict.PARTIAL,
                final_action=decision.action,
                confirmation_score=confirmation_score,
                position_factor=self.config.partial_position_factor,
                reasons=[
                    f"Timeframe onayı kısmi: {confirmation_score:.1f}/100."
                ],
                evaluations=evaluations,
            )
        else:
            result = self._build_result(
                decision=decision,
                verdict=TimeframeVerdict.CONFIRMED,
                final_action=decision.action,
                confirmation_score=confirmation_score,
                position_factor=1.0,
                reasons=[
                    f"Timeframe onayı güçlü: {confirmation_score:.1f}/100."
                ],
                evaluations=evaluations,
            )

        self.history.append(result)
        return result

    def apply(
        self,
        decision: StrategyDecision,
        signals: dict[str, TimeframeSignal | dict[str, Any]] | None = None,
    ) -> StrategyDecision:
        return self.evaluate(decision, signals).filtered_decision

    def summary(self, limit: int | None = None) -> dict[str, Any]:
        items = self.history[-limit:] if limit and limit > 0 else self.history
        counts = {verdict.value: 0 for verdict in TimeframeVerdict}
        for item in items:
            counts[item.verdict.value] += 1
        average = (
            sum(item.confirmation_score for item in items) / len(items)
            if items
            else 0.0
        )
        return {
            "total": len(items),
            "counts": counts,
            "average_confirmation_score": round(average, 4),
            "recent": [item.to_dict() for item in items[-20:]],
        }

    def clear_history(self) -> None:
        self.history.clear()

    def _build_result(
        self,
        *,
        decision: StrategyDecision,
        verdict: TimeframeVerdict,
        final_action: RuntimeAction,
        confirmation_score: float,
        position_factor: float,
        reasons: list[str],
        evaluations: list[TimeframeEvaluation],
    ) -> MultiTimeframeResult:
        quantity = decision.quantity
        if quantity is not None:
            quantity = float(quantity) * position_factor

        metadata = dict(decision.metadata)
        metadata.update(
            {
                "multi_timeframe_verdict": verdict.value,
                "multi_timeframe_score": round(confirmation_score, 4),
                "multi_timeframe_position_factor": position_factor,
                "multi_timeframe_reasons": list(reasons),
            }
        )

        filtered = StrategyDecision(
            symbol=decision.symbol,
            action=final_action,
            score=decision.score,
            reason=self._compose_reason(decision.reason, verdict, reasons),
            quantity=quantity,
            price=decision.price,
            metadata=metadata,
        )

        return MultiTimeframeResult(
            symbol=self.normalize_symbol(decision.symbol),
            original_action=decision.action,
            final_action=final_action,
            verdict=verdict,
            confirmation_score=round(confirmation_score, 4),
            position_factor=position_factor,
            reasons=list(reasons),
            evaluations=evaluations,
            filtered_decision=filtered,
        )

    @staticmethod
    def infer_trend(
        *,
        close: float | None = None,
        ema_fast: float | None = None,
        ema_slow: float | None = None,
        score: float | None = None,
    ) -> TimeframeTrend:
        if (
            close is None
            or ema_fast is None
            or ema_slow is None
        ):
            return TimeframeTrend.UNKNOWN

        if close > ema_fast > ema_slow:
            return TimeframeTrend.BULLISH
        if close < ema_fast < ema_slow:
            return TimeframeTrend.BEARISH

        if score is not None:
            if score >= 65:
                return TimeframeTrend.BULLISH
            if score <= 35:
                return TimeframeTrend.BEARISH

        return TimeframeTrend.NEUTRAL

    @classmethod
    def signal_from_indicators(
        cls,
        timeframe: str,
        indicators: dict[str, Any],
    ) -> TimeframeSignal:
        close = cls._to_float(indicators.get("close"))
        ema_fast = cls._to_float(
            indicators.get("ema_fast", indicators.get("ema20"))
        )
        ema_slow = cls._to_float(
            indicators.get("ema_slow", indicators.get("ema50"))
        )
        score = cls._to_float(indicators.get("score"), default=50.0)
        trend_raw = indicators.get("trend")

        if trend_raw is None:
            trend = cls.infer_trend(
                close=close,
                ema_fast=ema_fast,
                ema_slow=ema_slow,
                score=score,
            )
        else:
            trend = cls._parse_trend(trend_raw)

        return TimeframeSignal(
            timeframe=cls.normalize_timeframe(timeframe),
            trend=trend,
            score=score,
            close=close,
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            rsi=cls._to_float(indicators.get("rsi")),
            adx=cls._to_float(indicators.get("adx")),
            metadata=dict(indicators.get("metadata", {})),
        )

    @classmethod
    def _coerce_signal(
        cls,
        timeframe: str,
        value: TimeframeSignal | dict[str, Any],
    ) -> TimeframeSignal:
        if isinstance(value, TimeframeSignal):
            return value
        if isinstance(value, dict):
            return cls.signal_from_indicators(timeframe, value)
        raise TypeError("Timeframe sinyali dict veya TimeframeSignal olmalıdır.")

    @staticmethod
    def _parse_trend(value: Any) -> TimeframeTrend:
        text = str(value).upper()
        aliases = {
            "UP": TimeframeTrend.BULLISH,
            "LONG": TimeframeTrend.BULLISH,
            "BULL": TimeframeTrend.BULLISH,
            "BULLISH": TimeframeTrend.BULLISH,
            "DOWN": TimeframeTrend.BEARISH,
            "SHORT": TimeframeTrend.BEARISH,
            "BEAR": TimeframeTrend.BEARISH,
            "BEARISH": TimeframeTrend.BEARISH,
            "SIDEWAYS": TimeframeTrend.NEUTRAL,
            "FLAT": TimeframeTrend.NEUTRAL,
            "NEUTRAL": TimeframeTrend.NEUTRAL,
            "UNKNOWN": TimeframeTrend.UNKNOWN,
        }
        return aliases.get(text, TimeframeTrend.UNKNOWN)

    @staticmethod
    def normalize_timeframe(timeframe: str) -> str:
        text = str(timeframe).strip().lower()
        aliases = {
            "15min": "15m",
            "15minute": "15m",
            "60m": "1h",
            "1hour": "1h",
            "240m": "4h",
            "4hour": "4h",
            "day": "1d",
            "daily": "1d",
        }
        return aliases.get(text, text)

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        return symbol.replace("/", "").replace("-", "").upper()

    @staticmethod
    def _compose_reason(
        original_reason: str,
        verdict: TimeframeVerdict,
        reasons: list[str],
    ) -> str:
        detail = "; ".join(reasons)
        if detail:
            return f"{original_reason} | MTF: {verdict.value} - {detail}"
        return f"{original_reason} | MTF: {verdict.value}"

    @staticmethod
    def _to_float(value: Any, default: float | None = None) -> float | None:
        if value is None:
            return default
        return float(value)


class MultiTimeframeRuntimeBridge:
    def __init__(
        self,
        *,
        confirmation_engine: MultiTimeframeConfirmationEngine,
        next_stage: Any | None = None,
    ) -> None:
        self.confirmation_engine = confirmation_engine
        self.next_stage = next_stage

    def process(
        self,
        decision: StrategyDecision,
        timeframe_signals: dict[str, TimeframeSignal | dict[str, Any]] | None = None,
        market_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = self.confirmation_engine.evaluate(
            decision,
            timeframe_signals,
        )

        next_result = None
        if (
            self.next_stage is not None
            and result.filtered_decision.action
            in {RuntimeAction.BUY, RuntimeAction.SELL}
        ):
            if hasattr(self.next_stage, "process"):
                next_result = self.next_stage.process(
                    result.filtered_decision,
                    market_context or {},
                )
            elif hasattr(self.next_stage, "execute"):
                next_result = self.next_stage.execute(
                    result.filtered_decision,
                    market_context or {},
                )

        return {
            "multi_timeframe": result.to_dict(),
            "next_stage": next_result,
        }

    def dashboard(self) -> dict[str, Any]:
        return self.confirmation_engine.summary(limit=100)
