from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from engine.live_robot_core import (
    LiveRobotCore,
    SignalEvent,
    TradeLifecycleStatus,
)
from engine.paper_execution import (
    OrderSide,
    OrderStatus,
    OrderType,
    PaperExecutionEngine,
)
from engine.trade_gate import TradeCandidate, UnifiedTradeGate


@dataclass
class OrchestratorConfig:
    default_order_type: str = "MARKET"
    auto_register_portfolio: bool = True
    reject_non_buy_signals: bool = True


@dataclass
class OrchestratorDecision:
    accepted: bool
    code: str
    reason: str
    stage: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RobotPaperOrchestrator:
    def __init__(
        self,
        *,
        robot: LiveRobotCore,
        trade_gate: UnifiedTradeGate,
        paper_engine: PaperExecutionEngine,
        config: OrchestratorConfig | None = None,
    ) -> None:
        self.robot = robot
        self.trade_gate = trade_gate
        self.paper_engine = paper_engine
        self.config = config or OrchestratorConfig()
        self.history: list[dict[str, Any]] = []

    def process_signal(
        self,
        *,
        signal: SignalEvent | dict[str, Any],
        market_price: float,
        stop_price: float,
        requested_quantity: float,
        initial_equity: float,
        starting_equity: float,
        current_equity: float,
        daily_trade_count: int,
        consecutive_losses: int,
        current_total_risk_pct: float,
        available_cash: float | None = None,
        sector: str | None = None,
        minimum_signal_score: float = 0.0,
        correlations: dict[str, float] | None = None,
        take_profit: float | None = None,
        available_liquidity: float | None = None,
    ) -> OrchestratorDecision:
        event = (
            signal
            if isinstance(signal, SignalEvent)
            else SignalEvent(**signal)
        )

        if self.config.reject_non_buy_signals and event.signal.upper() != "BUY":
            return self._record(
                OrchestratorDecision(
                    accepted=False,
                    code="UNSUPPORTED_SIGNAL",
                    reason="Bu entegrasyon akışı yalnızca BUY sinyallerini açar.",
                    stage="signal",
                    details={"signal": event.to_dict()},
                )
            )

        if market_price <= 0 or stop_price <= 0 or requested_quantity <= 0:
            return self._record(
                OrchestratorDecision(
                    accepted=False,
                    code="INVALID_INPUT",
                    reason="Fiyat, stop ve miktar 0'dan büyük olmalıdır.",
                    stage="validation",
                    details={
                        "market_price": market_price,
                        "stop_price": stop_price,
                        "requested_quantity": requested_quantity,
                    },
                )
            )

        cash = (
            self.paper_engine.cash
            if available_cash is None
            else float(available_cash)
        )

        candidate = TradeCandidate(
            symbol=event.symbol,
            market=event.market,
            quantity=float(requested_quantity),
            entry_price=float(market_price),
            current_price=float(market_price),
            stop_price=float(stop_price),
            sector=sector,
            side="LONG",
            signal_score=float(event.score),
            minimum_signal_score=float(minimum_signal_score),
        )

        gate_decision = self.trade_gate.evaluate_trade(
            candidate=candidate,
            initial_equity=initial_equity,
            starting_equity=starting_equity,
            current_equity=current_equity,
            daily_trade_count=daily_trade_count,
            consecutive_losses=consecutive_losses,
            current_total_risk_pct=current_total_risk_pct,
            available_cash=cash,
            correlations=correlations or {},
        )

        if not gate_decision.allowed:
            return self._record(
                OrchestratorDecision(
                    accepted=False,
                    code=gate_decision.code,
                    reason=gate_decision.reason,
                    stage=gate_decision.stage,
                    details={
                        "signal": event.to_dict(),
                        "gate": gate_decision.to_dict(),
                    },
                )
            )

        approved_quantity = float(
            gate_decision.details["approved_quantity"]
        )

        lifecycle = self.robot.create_trade(
            symbol=event.symbol,
            market=event.market,
            side="LONG",
            quantity=approved_quantity,
            entry_price=market_price,
            stop_price=stop_price,
            target_price=take_profit,
        )
        self.robot.transition_trade(
            lifecycle.trade_id,
            TradeLifecycleStatus.QUEUED,
            reason="Trade Gate onayı sonrası paper emir kuyruğa alındı.",
        )
        self.robot.transition_trade(
            lifecycle.trade_id,
            TradeLifecycleStatus.APPROVED,
            reason="Trade Gate işlemi onayladı.",
        )

        order_type = OrderType(self.config.default_order_type.upper())
        order = self.paper_engine.submit_order(
            symbol=event.symbol,
            side=OrderSide.BUY,
            order_type=order_type,
            quantity=approved_quantity,
            stop_loss=stop_price,
            take_profit=take_profit,
        )
        self.paper_engine.process_order(
            order.order_id,
            market_price=market_price,
            available_liquidity=available_liquidity,
        )

        if order.status not in {
            OrderStatus.FILLED,
            OrderStatus.PARTIALLY_FILLED,
        }:
            self.robot.transition_trade(
                lifecycle.trade_id,
                TradeLifecycleStatus.FAILED,
                reason=order.reject_reason or "Paper emir gerçekleşmedi.",
            )
            return self._record(
                OrchestratorDecision(
                    accepted=False,
                    code="PAPER_ORDER_FAILED",
                    reason=order.reject_reason or "Paper emir gerçekleşmedi.",
                    stage="execution",
                    details={
                        "signal": event.to_dict(),
                        "gate": gate_decision.to_dict(),
                        "order": order.to_dict(),
                        "trade": lifecycle.to_dict(),
                    },
                )
            )

        lifecycle.quantity = float(order.filled_quantity)
        lifecycle.entry_price = float(order.average_fill_price)
        self.robot.transition_trade(
            lifecycle.trade_id,
            TradeLifecycleStatus.OPEN,
            reason="Paper emir gerçekleşti.",
        )

        if self.config.auto_register_portfolio:
            approved = gate_decision.details["candidate"]
            approved["quantity"] = float(order.filled_quantity)
            approved["entry_price"] = float(order.average_fill_price)
            approved["current_price"] = float(order.average_fill_price)
            self.trade_gate.portfolio_engine.add_position(
                candidate.to_position().__class__(
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

        self.robot.publish_signal(event)

        return self._record(
            OrchestratorDecision(
                accepted=True,
                code="EXECUTED",
                reason="Sinyal onaylandı ve paper emir gerçekleştirildi.",
                stage="completed",
                details={
                    "signal": event.to_dict(),
                    "gate": gate_decision.to_dict(),
                    "order": order.to_dict(),
                    "trade": lifecycle.to_dict(),
                    "account": self.paper_engine.account_report(),
                },
            )
        )

    def process_price_update(
        self,
        *,
        symbol: str,
        market_price: float,
        available_liquidity: float | None = None,
    ) -> list[dict[str, Any]]:
        processed_orders = self.paper_engine.process_price_update(
            symbol=symbol,
            market_price=market_price,
            available_liquidity=available_liquidity,
        )
        events: list[dict[str, Any]] = []

        for order in processed_orders:
            if order.side != OrderSide.SELL:
                continue
            if order.status not in {
                OrderStatus.FILLED,
                OrderStatus.PARTIALLY_FILLED,
            }:
                continue

            open_trade = next(
                (
                    trade
                    for trade in self.robot.trades.values()
                    if trade.symbol == symbol
                    and trade.status == TradeLifecycleStatus.OPEN
                ),
                None,
            )
            if open_trade is None:
                continue

            self.robot.transition_trade(
                open_trade.trade_id,
                TradeLifecycleStatus.CLOSED,
                reason="Paper exit emri gerçekleşti.",
                exit_price=order.average_fill_price,
            )

            try:
                self.trade_gate.portfolio_engine.remove_position(symbol)
            except (KeyError, ValueError):
                pass

            events.append(
                {
                    "symbol": symbol,
                    "order": order.to_dict(),
                    "trade": open_trade.to_dict(),
                }
            )

        return events

    def combined_report(self) -> dict[str, Any]:
        account = self.paper_engine.account_report()
        return {
            "robot": self.robot.robot_report(),
            "paper_account": account,
            "portfolio": self.trade_gate.portfolio_engine.portfolio_report(
                equity=account["equity"],
                cash=account["cash"],
            ),
            "orchestrator_history": list(self.history),
        }

    def _record(
        self,
        decision: OrchestratorDecision,
    ) -> OrchestratorDecision:
        self.history.append(decision.to_dict())
        return decision
