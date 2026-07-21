from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from engine.portfolio_engine import PortfolioEngine, PortfolioPosition
from engine.risk_core import RiskCore


@dataclass
class TradeCandidate:
    symbol: str
    market: str
    quantity: float
    entry_price: float
    current_price: float
    stop_price: float
    sector: str | None = None
    side: str = "LONG"
    signal_score: float = 0.0
    minimum_signal_score: float = 0.0

    def to_position(self) -> PortfolioPosition:
        return PortfolioPosition(
            symbol=self.symbol,
            market=self.market,
            quantity=self.quantity,
            entry_price=self.entry_price,
            current_price=self.current_price,
            stop_price=self.stop_price,
            sector=self.sector,
            side=self.side,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TradeGateDecision:
    allowed: bool
    code: str
    reason: str
    stage: str
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class UnifiedTradeGate:
    def __init__(
        self,
        *,
        risk_core: RiskCore,
        portfolio_engine: PortfolioEngine,
    ) -> None:
        self.risk_core = risk_core
        self.portfolio_engine = portfolio_engine

    def evaluate_trade(
        self,
        *,
        candidate: TradeCandidate | dict[str, Any],
        initial_equity: float,
        starting_equity: float,
        current_equity: float,
        daily_trade_count: int,
        consecutive_losses: int,
        current_total_risk_pct: float,
        available_cash: float,
        correlations: dict[str, float] | None = None,
    ) -> TradeGateDecision:
        item = (
            candidate
            if isinstance(candidate, TradeCandidate)
            else TradeCandidate(**candidate)
        )

        signal_decision = self._check_signal(item)
        if not signal_decision.allowed:
            return signal_decision

        risk_result = self.risk_core.evaluate_new_trade(
            initial_equity=initial_equity,
            starting_equity=starting_equity,
            current_equity=current_equity,
            daily_trade_count=daily_trade_count,
            consecutive_losses=consecutive_losses,
            open_positions=len(self.portfolio_engine.list_positions()),
            current_total_risk_pct=current_total_risk_pct,
            entry_price=item.entry_price,
            stop_price=item.stop_price,
            available_cash=available_cash,
        )

        if not risk_result["allowed"]:
            decision = risk_result["decision"]
            return TradeGateDecision(
                allowed=False,
                code=decision.get("code", "RISK_REJECTED"),
                reason=decision.get("reason", "Risk kontrolü işlemi reddetti."),
                stage=f"risk:{risk_result['stage']}",
                details={
                    "candidate": item.to_dict(),
                    "risk": risk_result,
                },
            )

        sized_quantity = float(risk_result["position"]["quantity"])
        effective_quantity = min(float(item.quantity), sized_quantity)
        if effective_quantity <= 0:
            return TradeGateDecision(
                allowed=False,
                code="INVALID_EFFECTIVE_QUANTITY",
                reason="Risk sonrası geçerli işlem miktarı oluşmadı.",
                stage="sizing",
                details={
                    "candidate_quantity": item.quantity,
                    "risk_quantity": sized_quantity,
                },
            )

        sized_candidate = TradeCandidate(
            symbol=item.symbol,
            market=item.market,
            quantity=effective_quantity,
            entry_price=item.entry_price,
            current_price=item.current_price,
            stop_price=item.stop_price,
            sector=item.sector,
            side=item.side,
            signal_score=item.signal_score,
            minimum_signal_score=item.minimum_signal_score,
        )

        portfolio_result = self.portfolio_engine.evaluate_candidate(
            equity=current_equity,
            candidate=sized_candidate.to_position(),
            correlations=correlations or {},
        )

        if not portfolio_result["allowed"]:
            decision = portfolio_result["decision"]
            return TradeGateDecision(
                allowed=False,
                code=decision.get("code", "PORTFOLIO_REJECTED"),
                reason=decision.get(
                    "reason",
                    "Portföy kontrolü işlemi reddetti.",
                ),
                stage=f"portfolio:{portfolio_result['stage']}",
                details={
                    "candidate": sized_candidate.to_dict(),
                    "risk": risk_result,
                    "portfolio": portfolio_result,
                },
            )

        return TradeGateDecision(
            allowed=True,
            code="APPROVED",
            reason="İşlem tüm sinyal, risk ve portföy kontrollerinden geçti.",
            stage="approved",
            details={
                "candidate": sized_candidate.to_dict(),
                "original_quantity": item.quantity,
                "approved_quantity": effective_quantity,
                "risk": risk_result,
                "portfolio": portfolio_result,
            },
        )

    def approve_and_register(
        self,
        *,
        candidate: TradeCandidate | dict[str, Any],
        initial_equity: float,
        starting_equity: float,
        current_equity: float,
        daily_trade_count: int,
        consecutive_losses: int,
        current_total_risk_pct: float,
        available_cash: float,
        correlations: dict[str, float] | None = None,
    ) -> TradeGateDecision:
        decision = self.evaluate_trade(
            candidate=candidate,
            initial_equity=initial_equity,
            starting_equity=starting_equity,
            current_equity=current_equity,
            daily_trade_count=daily_trade_count,
            consecutive_losses=consecutive_losses,
            current_total_risk_pct=current_total_risk_pct,
            available_cash=available_cash,
            correlations=correlations,
        )

        if decision.allowed:
            approved = decision.details["candidate"]
            self.portfolio_engine.add_position(
                PortfolioPosition(
                    symbol=approved["symbol"],
                    market=approved["market"],
                    quantity=approved["quantity"],
                    entry_price=approved["entry_price"],
                    current_price=approved["current_price"],
                    stop_price=approved["stop_price"],
                    sector=approved.get("sector"),
                    side=approved.get("side", "LONG"),
                )
            )

        return decision

    @staticmethod
    def _check_signal(candidate: TradeCandidate) -> TradeGateDecision:
        if candidate.signal_score < candidate.minimum_signal_score:
            return TradeGateDecision(
                allowed=False,
                code="SIGNAL_SCORE_TOO_LOW",
                reason="Sinyal puanı minimum giriş eşiğinin altında.",
                stage="signal",
                details={
                    "signal_score": candidate.signal_score,
                    "minimum_signal_score": candidate.minimum_signal_score,
                },
            )

        return TradeGateDecision(
            allowed=True,
            code="OK",
            reason="Sinyal puanı uygun.",
            stage="signal",
            details={
                "signal_score": candidate.signal_score,
                "minimum_signal_score": candidate.minimum_signal_score,
            },
        )

    def gate_report(
        self,
        *,
        equity: float,
        cash: float,
    ) -> dict[str, Any]:
        return {
            "risk_config": asdict(self.risk_core.config),
            "portfolio": self.portfolio_engine.portfolio_report(
                equity=equity,
                cash=cash,
            ),
        }
