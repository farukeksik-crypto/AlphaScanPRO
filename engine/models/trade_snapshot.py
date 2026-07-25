from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class TradeSnapshot:
    """Bir işlemin girişten çıkışa kadar standart kaydı."""

    trade_id: str
    created_at: str
    updated_at: str

    market: str
    universe: str
    symbol: str

    decision: str
    score: float
    confidence: float
    probability: float
    risk_level: str

    strategy_name: str = "default"
    strategy_version: str = ""
    robot_version: str = ""

    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    take_profit2: float = 0.0
    atr: float = 0.0
    quantity: float = 0.0

    market_regime: str = ""
    entry_reason: str = ""

    status: str = "OPEN"
    exit_price: float | None = None
    exit_reason: str = ""
    exit_type: str = ""
    closed_at: str | None = None

    pnl: float | None = None
    pnl_percent: float | None = None
    holding_minutes: float | None = None

    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.trade_id.strip():
            raise ValueError("trade_id boş olamaz.")
        if not self.symbol.strip():
            raise ValueError("symbol boş olamaz.")
        if self.entry_price < 0:
            raise ValueError("entry_price negatif olamaz.")
        if self.quantity < 0:
            raise ValueError("quantity negatif olamaz.")
        if self.status not in {"OPEN", "PARTIAL", "CLOSED", "CANCELLED"}:
            raise ValueError(f"Geçersiz status: {self.status}")

        object.__setattr__(self, "market", self.market.strip().upper())
        object.__setattr__(self, "universe", self.universe.strip())
        object.__setattr__(self, "symbol", self.symbol.strip().upper())
        object.__setattr__(self, "decision", self.decision.strip().upper())
        object.__setattr__(self, "risk_level", self.risk_level.strip())
        object.__setattr__(self, "metadata", dict(self.metadata))

    @classmethod
    def open(
        cls,
        *,
        market: str,
        universe: str,
        symbol: str,
        decision: str,
        score: float,
        confidence: float,
        probability: float,
        risk_level: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        quantity: float,
        atr: float = 0.0,
        take_profit2: float = 0.0,
        strategy_name: str = "default",
        strategy_version: str = "",
        robot_version: str = "",
        market_regime: str = "",
        entry_reason: str = "",
        metadata: Mapping[str, Any] | None = None,
        trade_id: str | None = None,
        timestamp: str | None = None,
    ) -> "TradeSnapshot":
        now = timestamp or _utc_now_iso()
        return cls(
            trade_id=trade_id or uuid4().hex,
            created_at=now,
            updated_at=now,
            market=market,
            universe=universe,
            symbol=symbol,
            decision=decision,
            score=float(score),
            confidence=float(confidence),
            probability=float(probability),
            risk_level=risk_level,
            strategy_name=strategy_name,
            strategy_version=strategy_version,
            robot_version=robot_version,
            entry_price=float(entry_price),
            stop_loss=float(stop_loss),
            take_profit=float(take_profit),
            take_profit2=float(take_profit2),
            atr=float(atr),
            quantity=float(quantity),
            market_regime=market_regime,
            entry_reason=entry_reason,
            metadata=dict(metadata or {}),
        )

    def with_metadata(self, **values: Any) -> "TradeSnapshot":
        merged = dict(self.metadata)
        merged.update(values)
        return replace(self, metadata=merged, updated_at=_utc_now_iso())

    def mark_partial(
        self,
        *,
        remaining_quantity: float,
        exit_price: float,
        reason: str = "PARTIAL_EXIT",
        metadata: Mapping[str, Any] | None = None,
    ) -> "TradeSnapshot":
        if self.status == "CLOSED":
            raise ValueError("Kapanmış işlem kısmi çıkışa çevrilemez.")
        if remaining_quantity < 0:
            raise ValueError("remaining_quantity negatif olamaz.")

        merged = dict(self.metadata)
        merged.update(metadata or {})
        merged["partial_exit_price"] = float(exit_price)
        merged["partial_exit_reason"] = reason

        return replace(
            self,
            status="PARTIAL",
            quantity=float(remaining_quantity),
            updated_at=_utc_now_iso(),
            metadata=merged,
        )

    def close(
        self,
        *,
        exit_price: float,
        exit_reason: str,
        exit_type: str = "",
        closed_at: str | None = None,
        pnl: float | None = None,
        pnl_percent: float | None = None,
        holding_minutes: float | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "TradeSnapshot":
        if self.status == "CLOSED":
            raise ValueError("İşlem zaten kapalı.")

        closed_time = closed_at or _utc_now_iso()
        calculated_pnl = pnl
        if calculated_pnl is None and self.entry_price and self.quantity:
            calculated_pnl = (float(exit_price) - self.entry_price) * self.quantity

        calculated_pct = pnl_percent
        if calculated_pct is None and self.entry_price:
            calculated_pct = ((float(exit_price) / self.entry_price) - 1.0) * 100.0

        merged = dict(self.metadata)
        merged.update(metadata or {})

        return replace(
            self,
            status="CLOSED",
            exit_price=float(exit_price),
            exit_reason=exit_reason,
            exit_type=exit_type,
            closed_at=closed_time,
            updated_at=closed_time,
            pnl=None if calculated_pnl is None else float(calculated_pnl),
            pnl_percent=None if calculated_pct is None else float(calculated_pct),
            holding_minutes=None if holding_minutes is None else float(holding_minutes),
            metadata=merged,
        )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["metadata"] = dict(self.metadata)
        return result

    @classmethod
    def from_dict(cls, values: Mapping[str, Any]) -> "TradeSnapshot":
        payload = dict(values)
        payload["metadata"] = dict(payload.get("metadata") or {})
        return cls(**payload)
