from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any
import math

from engine.robot_runtime import RuntimeAction, StrategyDecision


class DecisionVerdict(str, Enum):
    APPROVED = "APPROVED"
    REDUCED = "REDUCED"
    REJECTED = "REJECTED"
    SKIPPED = "SKIPPED"


@dataclass
class DecisionFilterConfig:
    enabled: bool = True
    minimum_quality_score: float = 60.0
    reduced_quality_score: float = 72.0
    minimum_strategy_score: float = 55.0
    maximum_volatility_pct: float = 8.0
    maximum_spread_pct: float = 0.35
    minimum_volume_ratio: float = 0.70
    maximum_rsi_buy: float = 72.0
    minimum_rsi_sell: float = 28.0
    require_trend_alignment: bool = True
    require_positive_liquidity: bool = True
    reject_stale_market_data: bool = True
    stale_after_seconds: float = 90.0
    reduced_position_factor: float = 0.50
    maximum_position_factor: float = 1.00
    minimum_position_factor: float = 0.10

    def validate(self) -> None:
        if not 0 <= self.minimum_quality_score <= 100:
            raise ValueError("minimum_quality_score 0-100 arasında olmalıdır.")
        if not 0 <= self.reduced_quality_score <= 100:
            raise ValueError("reduced_quality_score 0-100 arasında olmalıdır.")
        if self.reduced_quality_score < self.minimum_quality_score:
            raise ValueError(
                "reduced_quality_score minimum_quality_score değerinden küçük olamaz."
            )
        if not 0 <= self.minimum_strategy_score <= 100:
            raise ValueError("minimum_strategy_score 0-100 arasında olmalıdır.")
        if self.maximum_volatility_pct <= 0:
            raise ValueError("maximum_volatility_pct pozitif olmalıdır.")
        if self.maximum_spread_pct < 0:
            raise ValueError("maximum_spread_pct negatif olamaz.")
        if self.minimum_volume_ratio < 0:
            raise ValueError("minimum_volume_ratio negatif olamaz.")
        if self.stale_after_seconds <= 0:
            raise ValueError("stale_after_seconds pozitif olmalıdır.")
        if not 0 < self.minimum_position_factor <= 1:
            raise ValueError("minimum_position_factor 0-1 arasında olmalıdır.")
        if not 0 < self.reduced_position_factor <= 1:
            raise ValueError("reduced_position_factor 0-1 arasında olmalıdır.")
        if not 0 < self.maximum_position_factor <= 1:
            raise ValueError("maximum_position_factor 0-1 arasında olmalıdır.")


@dataclass
class FilterFactor:
    name: str
    score: float
    weight: float
    passed: bool
    detail: str

    @property
    def contribution(self) -> float:
        return self.score * self.weight

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["contribution"] = self.contribution
        return data


@dataclass
class DecisionFilterResult:
    symbol: str
    original_action: RuntimeAction
    final_action: RuntimeAction
    verdict: DecisionVerdict
    quality_score: float
    position_factor: float
    reasons: list[str]
    warnings: list[str]
    factors: list[FilterFactor]
    original_decision: StrategyDecision
    filtered_decision: StrategyDecision

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "original_action": self.original_action.value,
            "final_action": self.final_action.value,
            "verdict": self.verdict.value,
            "quality_score": self.quality_score,
            "position_factor": self.position_factor,
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
            "factors": [item.to_dict() for item in self.factors],
            "original_decision": self._decision_to_dict(self.original_decision),
            "filtered_decision": self._decision_to_dict(self.filtered_decision),
        }

    @staticmethod
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


class IntelligentDecisionFilter:
    def __init__(self, config: DecisionFilterConfig | None = None) -> None:
        self.config = config or DecisionFilterConfig()
        self.config.validate()
        self.history: list[DecisionFilterResult] = []

    def evaluate(
        self,
        decision: StrategyDecision,
        market_context: dict[str, Any] | None = None,
    ) -> DecisionFilterResult:
        context = market_context or {}

        if decision.action not in {RuntimeAction.BUY, RuntimeAction.SELL}:
            result = self._skip(decision, "İşlem kararı olmadığı için filtre uygulanmadı.")
            self.history.append(result)
            return result

        if not self.config.enabled:
            result = self._approve_disabled(decision)
            self.history.append(result)
            return result

        factors = self._build_factors(decision, context)
        quality_score = self._weighted_score(factors)
        hard_reasons, warnings = self._hard_checks(decision, context)

        if hard_reasons or quality_score < self.config.minimum_quality_score:
            reasons = list(hard_reasons)
            if quality_score < self.config.minimum_quality_score:
                reasons.append(
                    f"Kalite puanı yetersiz: {quality_score:.1f}/100."
                )
            result = self._build_result(
                decision=decision,
                verdict=DecisionVerdict.REJECTED,
                final_action=RuntimeAction.HOLD,
                quality_score=quality_score,
                position_factor=0.0,
                reasons=reasons,
                warnings=warnings,
                factors=factors,
            )
        elif quality_score < self.config.reduced_quality_score:
            factor = self._clamp(
                self.config.reduced_position_factor,
                self.config.minimum_position_factor,
                self.config.maximum_position_factor,
            )
            result = self._build_result(
                decision=decision,
                verdict=DecisionVerdict.REDUCED,
                final_action=decision.action,
                quality_score=quality_score,
                position_factor=factor,
                reasons=[
                    f"Sinyal kabul edildi ancak pozisyon %{factor * 100:.0f} seviyesine düşürüldü."
                ],
                warnings=warnings,
                factors=factors,
            )
        else:
            result = self._build_result(
                decision=decision,
                verdict=DecisionVerdict.APPROVED,
                final_action=decision.action,
                quality_score=quality_score,
                position_factor=self.config.maximum_position_factor,
                reasons=[
                    f"Sinyal kalite filtresini geçti: {quality_score:.1f}/100."
                ],
                warnings=warnings,
                factors=factors,
            )

        self.history.append(result)
        return result

    def apply(
        self,
        decision: StrategyDecision,
        market_context: dict[str, Any] | None = None,
    ) -> StrategyDecision:
        return self.evaluate(decision, market_context).filtered_decision

    def batch_evaluate(
        self,
        decisions: list[StrategyDecision],
        contexts: dict[str, dict[str, Any]] | None = None,
    ) -> list[DecisionFilterResult]:
        contexts = contexts or {}
        return [
            self.evaluate(
                decision,
                contexts.get(self.normalize_symbol(decision.symbol), {}),
            )
            for decision in decisions
        ]

    def summary(self, limit: int | None = None) -> dict[str, Any]:
        items = self.history[-limit:] if limit and limit > 0 else self.history
        counts = {verdict.value: 0 for verdict in DecisionVerdict}
        for item in items:
            counts[item.verdict.value] += 1

        average_quality = (
            sum(item.quality_score for item in items) / len(items)
            if items
            else 0.0
        )
        return {
            "total": len(items),
            "counts": counts,
            "average_quality_score": round(average_quality, 4),
            "recent": [item.to_dict() for item in items[-20:]],
        }

    def clear_history(self) -> None:
        self.history.clear()

    def _build_factors(
        self,
        decision: StrategyDecision,
        context: dict[str, Any],
    ) -> list[FilterFactor]:
        return [
            self._strategy_score_factor(decision),
            self._trend_factor(decision, context),
            self._momentum_factor(decision, context),
            self._volume_factor(context),
            self._volatility_factor(context),
            self._spread_factor(context),
            self._freshness_factor(context),
            self._liquidity_factor(context),
        ]

    def _strategy_score_factor(self, decision: StrategyDecision) -> FilterFactor:
        score = self._clamp(float(decision.score), 0.0, 100.0)
        return FilterFactor(
            name="strategy_score",
            score=score,
            weight=0.25,
            passed=score >= self.config.minimum_strategy_score,
            detail=f"Strateji puanı: {score:.1f}",
        )

    def _trend_factor(
        self,
        decision: StrategyDecision,
        context: dict[str, Any],
    ) -> FilterFactor:
        trend = str(context.get("trend", "UNKNOWN")).upper()
        aligned = (
            trend in {"UP", "BULLISH", "LONG"}
            if decision.action == RuntimeAction.BUY
            else trend in {"DOWN", "BEARISH", "SHORT"}
        )
        unknown = trend in {"", "UNKNOWN", "NONE"}

        if unknown:
            score = 50.0
            detail = "Trend bilgisi yok."
        elif aligned:
            score = 100.0
            detail = f"Trend uyumlu: {trend}"
        else:
            score = 0.0
            detail = f"Trend uyumsuz: {trend}"

        return FilterFactor(
            name="trend_alignment",
            score=score,
            weight=0.20,
            passed=aligned or (unknown and not self.config.require_trend_alignment),
            detail=detail,
        )

    def _momentum_factor(
        self,
        decision: StrategyDecision,
        context: dict[str, Any],
    ) -> FilterFactor:
        rsi_value = context.get("rsi")
        if rsi_value is None:
            return FilterFactor(
                name="momentum",
                score=50.0,
                weight=0.15,
                passed=True,
                detail="RSI bilgisi yok.",
            )

        rsi = float(rsi_value)
        if not math.isfinite(rsi):
            return FilterFactor(
                name="momentum",
                score=0.0,
                weight=0.15,
                passed=False,
                detail="RSI geçersiz.",
            )

        if decision.action == RuntimeAction.BUY:
            passed = rsi <= self.config.maximum_rsi_buy
            score = 100.0 if 42 <= rsi <= 65 else 65.0 if passed else 0.0
        else:
            passed = rsi >= self.config.minimum_rsi_sell
            score = 100.0 if 35 <= rsi <= 58 else 65.0 if passed else 0.0

        return FilterFactor(
            name="momentum",
            score=score,
            weight=0.15,
            passed=passed,
            detail=f"RSI: {rsi:.2f}",
        )

    def _volume_factor(self, context: dict[str, Any]) -> FilterFactor:
        ratio = float(context.get("volume_ratio", 1.0))
        passed = ratio >= self.config.minimum_volume_ratio
        score = self._clamp(ratio * 100.0, 0.0, 100.0)
        return FilterFactor(
            name="volume",
            score=score,
            weight=0.12,
            passed=passed,
            detail=f"Hacim oranı: {ratio:.2f}",
        )

    def _volatility_factor(self, context: dict[str, Any]) -> FilterFactor:
        volatility = float(context.get("volatility_pct", 0.0))
        passed = volatility <= self.config.maximum_volatility_pct
        ratio = volatility / self.config.maximum_volatility_pct
        score = self._clamp(100.0 - ratio * 100.0, 0.0, 100.0)
        return FilterFactor(
            name="volatility",
            score=score,
            weight=0.10,
            passed=passed,
            detail=f"Volatilite: %{volatility:.2f}",
        )

    def _spread_factor(self, context: dict[str, Any]) -> FilterFactor:
        spread = float(context.get("spread_pct", 0.0))
        passed = spread <= self.config.maximum_spread_pct
        if self.config.maximum_spread_pct == 0:
            score = 100.0 if spread == 0 else 0.0
        else:
            score = self._clamp(
                100.0 - (spread / self.config.maximum_spread_pct) * 100.0,
                0.0,
                100.0,
            )
        return FilterFactor(
            name="spread",
            score=score,
            weight=0.08,
            passed=passed,
            detail=f"Spread: %{spread:.4f}",
        )

    def _freshness_factor(self, context: dict[str, Any]) -> FilterFactor:
        age = float(context.get("market_data_age_seconds", 0.0))
        passed = age <= self.config.stale_after_seconds
        score = self._clamp(
            100.0 - (age / self.config.stale_after_seconds) * 100.0,
            0.0,
            100.0,
        )
        return FilterFactor(
            name="freshness",
            score=score,
            weight=0.06,
            passed=passed,
            detail=f"Veri yaşı: {age:.1f} sn",
        )

    def _liquidity_factor(self, context: dict[str, Any]) -> FilterFactor:
        liquidity = float(context.get("liquidity_score", 100.0))
        score = self._clamp(liquidity, 0.0, 100.0)
        return FilterFactor(
            name="liquidity",
            score=score,
            weight=0.04,
            passed=score > 0,
            detail=f"Likidite puanı: {score:.1f}",
        )

    def _hard_checks(
        self,
        decision: StrategyDecision,
        context: dict[str, Any],
    ) -> tuple[list[str], list[str]]:
        reasons: list[str] = []
        warnings: list[str] = []

        if float(decision.score) < self.config.minimum_strategy_score:
            reasons.append("Strateji puanı minimum eşik altında.")

        trend = str(context.get("trend", "UNKNOWN")).upper()
        if self.config.require_trend_alignment:
            if decision.action == RuntimeAction.BUY and trend not in {
                "UP",
                "BULLISH",
                "LONG",
            }:
                reasons.append("Alış sinyali üst trend ile uyumlu değil.")
            if decision.action == RuntimeAction.SELL and trend not in {
                "DOWN",
                "BEARISH",
                "SHORT",
            }:
                reasons.append("Satış sinyali üst trend ile uyumlu değil.")

        volatility = float(context.get("volatility_pct", 0.0))
        if volatility > self.config.maximum_volatility_pct:
            reasons.append("Volatilite güvenli sınırın üzerinde.")

        spread = float(context.get("spread_pct", 0.0))
        if spread > self.config.maximum_spread_pct:
            reasons.append("Spread güvenli sınırın üzerinde.")

        volume_ratio = float(context.get("volume_ratio", 1.0))
        if volume_ratio < self.config.minimum_volume_ratio:
            reasons.append("Hacim oranı yetersiz.")

        rsi_value = context.get("rsi")
        if rsi_value is not None:
            rsi = float(rsi_value)
            if decision.action == RuntimeAction.BUY and rsi > self.config.maximum_rsi_buy:
                reasons.append("Alış için RSI aşırı yüksek.")
            if decision.action == RuntimeAction.SELL and rsi < self.config.minimum_rsi_sell:
                reasons.append("Satış için RSI aşırı düşük.")

        age = float(context.get("market_data_age_seconds", 0.0))
        if self.config.reject_stale_market_data and age > self.config.stale_after_seconds:
            reasons.append("Piyasa verisi güncel değil.")

        liquidity = float(context.get("liquidity_score", 100.0))
        if self.config.require_positive_liquidity and liquidity <= 0:
            reasons.append("Likidite bulunamadı.")

        if context.get("news_risk") is True:
            warnings.append("Haber riski işaretlendi.")
        if context.get("market_regime") in {"EXTREME", "PANIC"}:
            warnings.append("Olağan dışı piyasa rejimi.")

        return reasons, warnings

    def _build_result(
        self,
        *,
        decision: StrategyDecision,
        verdict: DecisionVerdict,
        final_action: RuntimeAction,
        quality_score: float,
        position_factor: float,
        reasons: list[str],
        warnings: list[str],
        factors: list[FilterFactor],
    ) -> DecisionFilterResult:
        quantity = decision.quantity
        if quantity is not None:
            quantity = float(quantity) * position_factor

        metadata = dict(decision.metadata)
        metadata.update(
            {
                "decision_filter_verdict": verdict.value,
                "decision_quality_score": round(quality_score, 4),
                "position_factor": position_factor,
                "filter_reasons": list(reasons),
                "filter_warnings": list(warnings),
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
        return DecisionFilterResult(
            symbol=self.normalize_symbol(decision.symbol),
            original_action=decision.action,
            final_action=final_action,
            verdict=verdict,
            quality_score=round(quality_score, 4),
            position_factor=position_factor,
            reasons=list(reasons),
            warnings=list(warnings),
            factors=factors,
            original_decision=decision,
            filtered_decision=filtered,
        )

    def _skip(self, decision: StrategyDecision, reason: str) -> DecisionFilterResult:
        return self._build_result(
            decision=decision,
            verdict=DecisionVerdict.SKIPPED,
            final_action=decision.action,
            quality_score=float(decision.score),
            position_factor=1.0,
            reasons=[reason],
            warnings=[],
            factors=[],
        )

    def _approve_disabled(
        self,
        decision: StrategyDecision,
    ) -> DecisionFilterResult:
        return self._build_result(
            decision=decision,
            verdict=DecisionVerdict.APPROVED,
            final_action=decision.action,
            quality_score=float(decision.score),
            position_factor=1.0,
            reasons=["Karar filtresi devre dışı."],
            warnings=[],
            factors=[],
        )

    @staticmethod
    def _weighted_score(factors: list[FilterFactor]) -> float:
        total_weight = sum(item.weight for item in factors)
        if total_weight <= 0:
            return 0.0
        return sum(item.contribution for item in factors) / total_weight

    @staticmethod
    def _compose_reason(
        original_reason: str,
        verdict: DecisionVerdict,
        reasons: list[str],
    ) -> str:
        suffix = "; ".join(reasons)
        if suffix:
            return f"{original_reason} | Filtre: {verdict.value} - {suffix}"
        return f"{original_reason} | Filtre: {verdict.value}"

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        return symbol.replace("/", "").replace("-", "").upper()

    @staticmethod
    def _clamp(value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, value))


class IntelligentDecisionRuntimeBridge:
    def __init__(
        self,
        *,
        decision_filter: IntelligentDecisionFilter,
        execution_engine: Any | None = None,
    ) -> None:
        self.decision_filter = decision_filter
        self.execution_engine = execution_engine

    def process(
        self,
        decision: StrategyDecision,
        market_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = self.decision_filter.evaluate(decision, market_context)
        execution_result = None

        if (
            self.execution_engine is not None
            and result.filtered_decision.action
            in {RuntimeAction.BUY, RuntimeAction.SELL}
        ):
            execution_result = self.execution_engine.execute(
                result.filtered_decision,
                market_context or {},
            )

        return {
            "filter": result.to_dict(),
            "execution": execution_result,
        }

    def dashboard(self) -> dict[str, Any]:
        return self.decision_filter.summary(limit=100)
