from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class PortfolioDecision(str, Enum):
    APPROVED = "APPROVED"
    REDUCED = "REDUCED"
    REJECTED = "REJECTED"


class PortfolioRejectReason(str, Enum):
    NONE = "NONE"
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"
    MAX_OPEN_POSITIONS = "MAX_OPEN_POSITIONS"
    SYMBOL_EXPOSURE_LIMIT = "SYMBOL_EXPOSURE_LIMIT"
    GROUP_EXPOSURE_LIMIT = "GROUP_EXPOSURE_LIMIT"
    TOTAL_EXPOSURE_LIMIT = "TOTAL_EXPOSURE_LIMIT"
    TOTAL_RISK_LIMIT = "TOTAL_RISK_LIMIT"
    INVALID_REQUEST = "INVALID_REQUEST"
    DUPLICATE_SYMBOL = "DUPLICATE_SYMBOL"


@dataclass
class PortfolioRiskConfig:
    initial_equity: float = 1_000_000.0
    max_open_positions: int = 5
    max_total_exposure_pct: float = 75.0
    max_symbol_exposure_pct: float = 25.0
    max_group_exposure_pct: float = 40.0
    max_total_risk_pct: float = 5.0
    max_risk_per_trade_pct: float = 1.0
    daily_loss_limit_pct: float = 3.0
    allow_position_reduction: bool = True
    block_duplicate_symbol: bool = True
    minimum_position_value: float = 100.0

    def validate(self) -> None:
        if self.initial_equity <= 0:
            raise ValueError("initial_equity pozitif olmalıdır.")
        if self.max_open_positions <= 0:
            raise ValueError("max_open_positions pozitif olmalıdır.")
        pct_fields = (
            self.max_total_exposure_pct,
            self.max_symbol_exposure_pct,
            self.max_group_exposure_pct,
            self.max_total_risk_pct,
            self.max_risk_per_trade_pct,
            self.daily_loss_limit_pct,
        )
        if any(value <= 0 or value > 100 for value in pct_fields):
            raise ValueError("Yüzde limitleri 0-100 arasında olmalıdır.")
        if self.minimum_position_value <= 0:
            raise ValueError("minimum_position_value pozitif olmalıdır.")


@dataclass
class PortfolioPosition:
    symbol: str
    quantity: float
    entry_price: float
    current_price: float
    stop_price: float
    group: str = "DEFAULT"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def market_value(self) -> float:
        return abs(self.quantity * self.current_price)

    @property
    def entry_value(self) -> float:
        return abs(self.quantity * self.entry_price)

    @property
    def risk_amount(self) -> float:
        return abs(self.entry_price - self.stop_price) * abs(self.quantity)

    @property
    def unrealized_pnl(self) -> float:
        direction = 1.0 if self.quantity >= 0 else -1.0
        return (self.current_price - self.entry_price) * abs(self.quantity) * direction

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.update(
            {
                "market_value": self.market_value,
                "entry_value": self.entry_value,
                "risk_amount": self.risk_amount,
                "unrealized_pnl": self.unrealized_pnl,
            }
        )
        return data


@dataclass
class PortfolioRequest:
    symbol: str
    side: str
    price: float
    quantity: float
    stop_price: float
    group: str = "DEFAULT"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def signed_quantity(self) -> float:
        side = self.side.upper()
        return abs(self.quantity) if side in {"BUY", "LONG"} else -abs(self.quantity)

    @property
    def position_value(self) -> float:
        return abs(self.quantity * self.price)

    @property
    def risk_amount(self) -> float:
        return abs(self.price - self.stop_price) * abs(self.quantity)


@dataclass
class PortfolioEvaluation:
    decision: PortfolioDecision
    reason: PortfolioRejectReason
    approved_quantity: float
    requested_quantity: float
    approved_position_value: float
    requested_position_value: float
    risk_amount: float
    message: str
    metrics: dict[str, float] = field(default_factory=dict)

    @property
    def approved(self) -> bool:
        return self.decision in {
            PortfolioDecision.APPROVED,
            PortfolioDecision.REDUCED,
        }

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["decision"] = self.decision.value
        data["reason"] = self.reason.value
        data["approved"] = self.approved
        return data


class PortfolioRiskManager:
    def __init__(self, config: PortfolioRiskConfig | None = None) -> None:
        self.config = config or PortfolioRiskConfig()
        self.config.validate()
        self.equity = float(self.config.initial_equity)
        self.day_start_equity = float(self.config.initial_equity)
        self.realized_pnl_today = 0.0
        self.positions: dict[str, PortfolioPosition] = {}
        self.history: list[PortfolioEvaluation] = []

    def evaluate(self, request: PortfolioRequest) -> PortfolioEvaluation:
        request = self._normalize_request(request)
        invalid = self._validate_request(request)
        if invalid is not None:
            return self._remember(invalid)

        if self.daily_loss_pct >= self.config.daily_loss_limit_pct:
            return self._remember(
                self._reject(
                    request,
                    PortfolioRejectReason.DAILY_LOSS_LIMIT,
                    "Günlük zarar limiti aşıldı; yeni işlem engellendi.",
                )
            )

        symbol = self.normalize_symbol(request.symbol)
        if self.config.block_duplicate_symbol and symbol in self.positions:
            return self._remember(
                self._reject(
                    request,
                    PortfolioRejectReason.DUPLICATE_SYMBOL,
                    "Aynı sembolde açık pozisyon mevcut.",
                )
            )

        if len(self.positions) >= self.config.max_open_positions:
            return self._remember(
                self._reject(
                    request,
                    PortfolioRejectReason.MAX_OPEN_POSITIONS,
                    "Maksimum açık pozisyon sayısına ulaşıldı.",
                )
            )

        requested_value = request.position_value
        requested_risk = request.risk_amount
        allowed_values = {
            "symbol": self._remaining_symbol_capacity(symbol),
            "group": self._remaining_group_capacity(request.group),
            "total": self._remaining_total_exposure_capacity(),
            "trade_risk": self.equity * self.config.max_risk_per_trade_pct / 100,
            "total_risk": self._remaining_total_risk_capacity(),
        }

        risk_per_value = (
            requested_risk / requested_value
            if requested_value > 0
            else float("inf")
        )
        risk_value_limits = [
            allowed_values["trade_risk"] / risk_per_value,
            allowed_values["total_risk"] / risk_per_value,
        ] if risk_per_value > 0 else [requested_value, requested_value]

        max_allowed_value = min(
            requested_value,
            allowed_values["symbol"],
            allowed_values["group"],
            allowed_values["total"],
            *risk_value_limits,
        )

        if max_allowed_value + 1e-9 >= requested_value:
            return self._remember(
                PortfolioEvaluation(
                    decision=PortfolioDecision.APPROVED,
                    reason=PortfolioRejectReason.NONE,
                    approved_quantity=request.quantity,
                    requested_quantity=request.quantity,
                    approved_position_value=requested_value,
                    requested_position_value=requested_value,
                    risk_amount=requested_risk,
                    message="İşlem portföy limitleri içinde onaylandı.",
                    metrics=self.metrics(),
                )
            )

        reason = self._limiting_reason(
            requested_value=requested_value,
            requested_risk=requested_risk,
            capacities=allowed_values,
            max_allowed_value=max_allowed_value,
        )

        if (
            not self.config.allow_position_reduction
            or max_allowed_value < self.config.minimum_position_value
        ):
            return self._remember(
                self._reject(
                    request,
                    reason,
                    "İşlem portföy limitleri nedeniyle reddedildi.",
                )
            )

        approved_quantity = request.quantity * max_allowed_value / requested_value
        approved_risk = requested_risk * max_allowed_value / requested_value

        return self._remember(
            PortfolioEvaluation(
                decision=PortfolioDecision.REDUCED,
                reason=reason,
                approved_quantity=approved_quantity,
                requested_quantity=request.quantity,
                approved_position_value=max_allowed_value,
                requested_position_value=requested_value,
                risk_amount=approved_risk,
                message="Pozisyon büyüklüğü portföy limitlerine göre azaltıldı.",
                metrics=self.metrics(),
            )
        )

    def register_position(
        self,
        request: PortfolioRequest,
        evaluation: PortfolioEvaluation | None = None,
    ) -> PortfolioPosition:
        evaluation = evaluation or self.evaluate(request)
        if not evaluation.approved:
            raise ValueError("Reddedilen işlem portföye kaydedilemez.")

        quantity = evaluation.approved_quantity
        signed_quantity = abs(quantity) if request.side.upper() in {"BUY", "LONG"} else -abs(quantity)
        position = PortfolioPosition(
            symbol=self.normalize_symbol(request.symbol),
            quantity=signed_quantity,
            entry_price=float(request.price),
            current_price=float(request.price),
            stop_price=float(request.stop_price),
            group=self.normalize_group(request.group),
            metadata=dict(request.metadata),
        )
        self.positions[position.symbol] = position
        return position

    def update_price(self, symbol: str, price: float) -> PortfolioPosition:
        normalized = self.normalize_symbol(symbol)
        if normalized not in self.positions:
            raise KeyError(f"Pozisyon bulunamadı: {normalized}")
        if price <= 0:
            raise ValueError("price pozitif olmalıdır.")
        self.positions[normalized].current_price = float(price)
        return self.positions[normalized]

    def close_position(self, symbol: str, exit_price: float) -> float:
        normalized = self.normalize_symbol(symbol)
        if normalized not in self.positions:
            raise KeyError(f"Pozisyon bulunamadı: {normalized}")
        if exit_price <= 0:
            raise ValueError("exit_price pozitif olmalıdır.")

        position = self.positions.pop(normalized)
        direction = 1.0 if position.quantity >= 0 else -1.0
        pnl = (
            exit_price - position.entry_price
        ) * abs(position.quantity) * direction
        self.realized_pnl_today += pnl
        self.equity += pnl
        return pnl

    def record_realized_pnl(self, pnl: float) -> None:
        self.realized_pnl_today += float(pnl)
        self.equity += float(pnl)

    def reset_day(self) -> None:
        self.day_start_equity = self.equity
        self.realized_pnl_today = 0.0

    @property
    def total_exposure(self) -> float:
        return sum(position.market_value for position in self.positions.values())

    @property
    def total_risk(self) -> float:
        return sum(position.risk_amount for position in self.positions.values())

    @property
    def unrealized_pnl(self) -> float:
        return sum(position.unrealized_pnl for position in self.positions.values())

    @property
    def daily_loss_pct(self) -> float:
        if self.day_start_equity <= 0:
            return 0.0
        loss = max(0.0, -self.realized_pnl_today)
        return loss / self.day_start_equity * 100

    def group_exposure(self, group: str) -> float:
        normalized = self.normalize_group(group)
        return sum(
            position.market_value
            for position in self.positions.values()
            if self.normalize_group(position.group) == normalized
        )

    def symbol_exposure(self, symbol: str) -> float:
        position = self.positions.get(self.normalize_symbol(symbol))
        return position.market_value if position else 0.0

    def metrics(self) -> dict[str, float]:
        return {
            "equity": self.equity,
            "day_start_equity": self.day_start_equity,
            "realized_pnl_today": self.realized_pnl_today,
            "unrealized_pnl": self.unrealized_pnl,
            "daily_loss_pct": self.daily_loss_pct,
            "total_exposure": self.total_exposure,
            "total_exposure_pct": self._pct(self.total_exposure),
            "total_risk": self.total_risk,
            "total_risk_pct": self._pct(self.total_risk),
            "open_position_count": float(len(self.positions)),
        }

    def dashboard(self) -> dict[str, Any]:
        return {
            "metrics": self.metrics(),
            "positions": [position.to_dict() for position in self.positions.values()],
            "recent_evaluations": [item.to_dict() for item in self.history[-100:]],
            "daily_loss_blocked": (
                self.daily_loss_pct >= self.config.daily_loss_limit_pct
            ),
        }

    def _normalize_request(self, request: PortfolioRequest) -> PortfolioRequest:
        return PortfolioRequest(
            symbol=self.normalize_symbol(request.symbol),
            side=request.side.upper(),
            price=float(request.price),
            quantity=abs(float(request.quantity)),
            stop_price=float(request.stop_price),
            group=self.normalize_group(request.group),
            metadata=dict(request.metadata),
        )

    def _validate_request(
        self,
        request: PortfolioRequest,
    ) -> PortfolioEvaluation | None:
        if request.side not in {"BUY", "LONG", "SELL", "SHORT"}:
            return self._reject(
                request,
                PortfolioRejectReason.INVALID_REQUEST,
                "Geçersiz işlem yönü.",
            )
        if request.price <= 0 or request.quantity <= 0 or request.stop_price <= 0:
            return self._reject(
                request,
                PortfolioRejectReason.INVALID_REQUEST,
                "Fiyat, miktar ve stop pozitif olmalıdır.",
            )
        if request.position_value < self.config.minimum_position_value:
            return self._reject(
                request,
                PortfolioRejectReason.INVALID_REQUEST,
                "Pozisyon değeri minimum sınırın altında.",
            )
        return None

    def _remaining_symbol_capacity(self, symbol: str) -> float:
        limit = self.equity * self.config.max_symbol_exposure_pct / 100
        return max(0.0, limit - self.symbol_exposure(symbol))

    def _remaining_group_capacity(self, group: str) -> float:
        limit = self.equity * self.config.max_group_exposure_pct / 100
        return max(0.0, limit - self.group_exposure(group))

    def _remaining_total_exposure_capacity(self) -> float:
        limit = self.equity * self.config.max_total_exposure_pct / 100
        return max(0.0, limit - self.total_exposure)

    def _remaining_total_risk_capacity(self) -> float:
        limit = self.equity * self.config.max_total_risk_pct / 100
        return max(0.0, limit - self.total_risk)

    def _limiting_reason(
        self,
        *,
        requested_value: float,
        requested_risk: float,
        capacities: dict[str, float],
        max_allowed_value: float,
    ) -> PortfolioRejectReason:
        risk_per_value = requested_risk / requested_value
        candidates = {
            PortfolioRejectReason.SYMBOL_EXPOSURE_LIMIT: capacities["symbol"],
            PortfolioRejectReason.GROUP_EXPOSURE_LIMIT: capacities["group"],
            PortfolioRejectReason.TOTAL_EXPOSURE_LIMIT: capacities["total"],
            PortfolioRejectReason.TOTAL_RISK_LIMIT: min(
                capacities["trade_risk"] / risk_per_value,
                capacities["total_risk"] / risk_per_value,
            ) if risk_per_value > 0 else requested_value,
        }
        return min(candidates, key=candidates.get)

    def _reject(
        self,
        request: PortfolioRequest,
        reason: PortfolioRejectReason,
        message: str,
    ) -> PortfolioEvaluation:
        return PortfolioEvaluation(
            decision=PortfolioDecision.REJECTED,
            reason=reason,
            approved_quantity=0.0,
            requested_quantity=request.quantity,
            approved_position_value=0.0,
            requested_position_value=request.position_value,
            risk_amount=0.0,
            message=message,
            metrics=self.metrics(),
        )

    def _remember(self, result: PortfolioEvaluation) -> PortfolioEvaluation:
        self.history.append(result)
        return result

    def _pct(self, value: float) -> float:
        return value / self.equity * 100 if self.equity > 0 else 0.0

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        return str(symbol).replace("/", "").replace("-", "").upper()

    @staticmethod
    def normalize_group(group: str) -> str:
        text = str(group or "DEFAULT").strip().upper()
        return text or "DEFAULT"


class PortfolioRuntimeBridge:
    def __init__(self, manager: PortfolioRiskManager) -> None:
        self.manager = manager

    def evaluate_execution(
        self,
        *,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        stop_price: float,
        group: str = "DEFAULT",
        metadata: dict[str, Any] | None = None,
    ) -> PortfolioEvaluation:
        return self.manager.evaluate(
            PortfolioRequest(
                symbol=symbol,
                side=side,
                price=price,
                quantity=quantity,
                stop_price=stop_price,
                group=group,
                metadata=dict(metadata or {}),
            )
        )

    def register_approved(
        self,
        request: PortfolioRequest,
        evaluation: PortfolioEvaluation,
    ) -> PortfolioPosition:
        return self.manager.register_position(request, evaluation)

    def dashboard(self) -> dict[str, Any]:
        return self.manager.dashboard()
