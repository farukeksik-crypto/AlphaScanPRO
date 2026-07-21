from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class RiskConfig:
    risk_per_trade_pct: float = 1.0
    max_daily_loss_pct: float = 3.0
    max_daily_trades: int = 8
    max_consecutive_losses: int = 3
    max_open_positions: int = 5
    max_total_risk_pct: float = 5.0
    min_stop_distance_pct: float = 0.25
    max_stop_distance_pct: float = 15.0
    equity_floor_pct: float = 80.0


@dataclass
class PositionSizeResult:
    allowed: bool
    quantity: float
    position_value: float
    risk_amount: float
    stop_distance: float
    stop_distance_pct: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RiskDecision:
    allowed: bool
    reason: str
    code: str
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RiskCore:
    def __init__(self, config: RiskConfig | None = None) -> None:
        self.config = config or RiskConfig()

    def calculate_position_size(
        self,
        *,
        equity: float,
        entry_price: float,
        stop_price: float,
        available_cash: float | None = None,
    ) -> PositionSizeResult:
        self._validate_positive(equity, "equity")
        self._validate_positive(entry_price, "entry_price")
        self._validate_positive(stop_price, "stop_price")

        stop_distance = abs(entry_price - stop_price)
        stop_distance_pct = stop_distance / entry_price * 100.0

        if stop_distance <= 0:
            return self._position_reject(
                "Stop mesafesi sıfır olamaz.",
                stop_distance,
                stop_distance_pct,
            )

        if stop_distance_pct < self.config.min_stop_distance_pct:
            return self._position_reject(
                "Stop mesafesi minimum sınırın altında.",
                stop_distance,
                stop_distance_pct,
            )

        if stop_distance_pct > self.config.max_stop_distance_pct:
            return self._position_reject(
                "Stop mesafesi maksimum sınırı aşıyor.",
                stop_distance,
                stop_distance_pct,
            )

        risk_amount = equity * self.config.risk_per_trade_pct / 100.0
        quantity = risk_amount / stop_distance
        position_value = quantity * entry_price

        if available_cash is not None:
            self._validate_positive(available_cash, "available_cash")
            if position_value > available_cash:
                quantity = available_cash / entry_price
                position_value = quantity * entry_price
                risk_amount = quantity * stop_distance

        if quantity <= 0 or position_value <= 0:
            return self._position_reject(
                "Pozisyon büyüklüğü hesaplanamadı.",
                stop_distance,
                stop_distance_pct,
            )

        return PositionSizeResult(
            allowed=True,
            quantity=round(quantity, 8),
            position_value=round(position_value, 8),
            risk_amount=round(risk_amount, 8),
            stop_distance=round(stop_distance, 8),
            stop_distance_pct=round(stop_distance_pct, 8),
            reason="Pozisyon büyüklüğü risk limitlerine göre hesaplandı.",
        )

    def check_daily_limits(
        self,
        *,
        starting_equity: float,
        current_equity: float,
        daily_trade_count: int,
        consecutive_losses: int,
    ) -> RiskDecision:
        self._validate_positive(starting_equity, "starting_equity")
        self._validate_positive(current_equity, "current_equity")

        daily_loss_pct = max(
            0.0,
            (starting_equity - current_equity) / starting_equity * 100.0,
        )

        if daily_loss_pct >= self.config.max_daily_loss_pct:
            return RiskDecision(
                allowed=False,
                reason="Günlük maksimum zarar limiti aşıldı.",
                code="DAILY_LOSS_LIMIT",
                details={"daily_loss_pct": round(daily_loss_pct, 8)},
            )

        if daily_trade_count >= self.config.max_daily_trades:
            return RiskDecision(
                allowed=False,
                reason="Günlük maksimum işlem sayısına ulaşıldı.",
                code="DAILY_TRADE_LIMIT",
                details={"daily_trade_count": int(daily_trade_count)},
            )

        if consecutive_losses >= self.config.max_consecutive_losses:
            return RiskDecision(
                allowed=False,
                reason="Ardışık zarar durdurucusu aktif.",
                code="CONSECUTIVE_LOSS_LIMIT",
                details={"consecutive_losses": int(consecutive_losses)},
            )

        return RiskDecision(
            allowed=True,
            reason="Günlük risk limitleri uygun.",
            code="OK",
            details={
                "daily_loss_pct": round(daily_loss_pct, 8),
                "daily_trade_count": int(daily_trade_count),
                "consecutive_losses": int(consecutive_losses),
            },
        )

    def check_equity_protection(
        self,
        *,
        initial_equity: float,
        current_equity: float,
    ) -> RiskDecision:
        self._validate_positive(initial_equity, "initial_equity")
        self._validate_positive(current_equity, "current_equity")

        equity_ratio_pct = current_equity / initial_equity * 100.0

        if equity_ratio_pct <= self.config.equity_floor_pct:
            return RiskDecision(
                allowed=False,
                reason="Equity koruma tabanı ihlal edildi.",
                code="EQUITY_FLOOR",
                details={"equity_ratio_pct": round(equity_ratio_pct, 8)},
            )

        return RiskDecision(
            allowed=True,
            reason="Equity koruma seviyesi uygun.",
            code="OK",
            details={"equity_ratio_pct": round(equity_ratio_pct, 8)},
        )

    def check_portfolio_capacity(
        self,
        *,
        open_positions: int,
        current_total_risk_pct: float,
        new_trade_risk_pct: float | None = None,
    ) -> RiskDecision:
        if open_positions >= self.config.max_open_positions:
            return RiskDecision(
                allowed=False,
                reason="Maksimum açık pozisyon sayısına ulaşıldı.",
                code="MAX_OPEN_POSITIONS",
                details={"open_positions": int(open_positions)},
            )

        proposed_risk = current_total_risk_pct + (
            self.config.risk_per_trade_pct
            if new_trade_risk_pct is None
            else float(new_trade_risk_pct)
        )

        if proposed_risk > self.config.max_total_risk_pct:
            return RiskDecision(
                allowed=False,
                reason="Toplam portföy risk limiti aşılacak.",
                code="MAX_TOTAL_RISK",
                details={
                    "current_total_risk_pct": round(
                        current_total_risk_pct,
                        8,
                    ),
                    "proposed_total_risk_pct": round(proposed_risk, 8),
                },
            )

        return RiskDecision(
            allowed=True,
            reason="Portföy kapasitesi yeni işlem için uygun.",
            code="OK",
            details={
                "open_positions": int(open_positions),
                "proposed_total_risk_pct": round(proposed_risk, 8),
            },
        )

    def evaluate_new_trade(
        self,
        *,
        initial_equity: float,
        starting_equity: float,
        current_equity: float,
        daily_trade_count: int,
        consecutive_losses: int,
        open_positions: int,
        current_total_risk_pct: float,
        entry_price: float,
        stop_price: float,
        available_cash: float | None = None,
    ) -> dict[str, Any]:
        equity_check = self.check_equity_protection(
            initial_equity=initial_equity,
            current_equity=current_equity,
        )
        if not equity_check.allowed:
            return {
                "allowed": False,
                "stage": "equity_protection",
                "decision": equity_check.to_dict(),
            }

        daily_check = self.check_daily_limits(
            starting_equity=starting_equity,
            current_equity=current_equity,
            daily_trade_count=daily_trade_count,
            consecutive_losses=consecutive_losses,
        )
        if not daily_check.allowed:
            return {
                "allowed": False,
                "stage": "daily_limits",
                "decision": daily_check.to_dict(),
            }

        portfolio_check = self.check_portfolio_capacity(
            open_positions=open_positions,
            current_total_risk_pct=current_total_risk_pct,
        )
        if not portfolio_check.allowed:
            return {
                "allowed": False,
                "stage": "portfolio_capacity",
                "decision": portfolio_check.to_dict(),
            }

        sizing = self.calculate_position_size(
            equity=current_equity,
            entry_price=entry_price,
            stop_price=stop_price,
            available_cash=available_cash,
        )
        if not sizing.allowed:
            return {
                "allowed": False,
                "stage": "position_sizing",
                "decision": sizing.to_dict(),
            }

        return {
            "allowed": True,
            "stage": "approved",
            "position": sizing.to_dict(),
            "checks": {
                "equity": equity_check.to_dict(),
                "daily": daily_check.to_dict(),
                "portfolio": portfolio_check.to_dict(),
            },
        }

    def risk_report(
        self,
        *,
        initial_equity: float,
        starting_equity: float,
        current_equity: float,
        daily_trade_count: int,
        consecutive_losses: int,
        open_positions: int,
        current_total_risk_pct: float,
    ) -> dict[str, Any]:
        return {
            "config": asdict(self.config),
            "equity": self.check_equity_protection(
                initial_equity=initial_equity,
                current_equity=current_equity,
            ).to_dict(),
            "daily": self.check_daily_limits(
                starting_equity=starting_equity,
                current_equity=current_equity,
                daily_trade_count=daily_trade_count,
                consecutive_losses=consecutive_losses,
            ).to_dict(),
            "portfolio": self.check_portfolio_capacity(
                open_positions=open_positions,
                current_total_risk_pct=current_total_risk_pct,
                new_trade_risk_pct=0.0,
            ).to_dict(),
        }

    @staticmethod
    def _validate_positive(value: float, name: str) -> None:
        if float(value) <= 0:
            raise ValueError(f"{name} 0'dan büyük olmalıdır.")

    @staticmethod
    def _position_reject(
        reason: str,
        stop_distance: float,
        stop_distance_pct: float,
    ) -> PositionSizeResult:
        return PositionSizeResult(
            allowed=False,
            quantity=0.0,
            position_value=0.0,
            risk_amount=0.0,
            stop_distance=round(stop_distance, 8),
            stop_distance_pct=round(stop_distance_pct, 8),
            reason=reason,
        )
