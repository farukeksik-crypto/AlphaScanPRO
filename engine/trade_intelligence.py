from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass
class TradeRecord:
    trade_id: str
    symbol: str
    market: str
    side: str
    entry_time: str
    entry_price: float
    quantity: float
    entry_reason: str
    ai_score: float | None = None
    ai_decision: str | None = None
    ai_confidence: float | None = None
    technical_score: float | None = None
    market_regime: str | None = None
    correlation_score: float | None = None
    risk_score: float | None = None
    sector: str | None = None
    stop_price: float | None = None
    target_price: float | None = None
    exit_time: str | None = None
    exit_price: float | None = None
    exit_reason: str | None = None
    pnl: float | None = None
    pnl_pct: float | None = None
    duration_minutes: float | None = None
    status: str = "OPEN"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TradeIntelligenceLogger:
    def __init__(self, storage_path: str | Path) -> None:
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.storage_path.exists():
            self.storage_path.write_text("", encoding="utf-8")

    def open_trade(
        self,
        *,
        symbol: str,
        market: str,
        side: str,
        entry_price: float,
        quantity: float,
        entry_reason: str,
        ai_score: float | None = None,
        ai_decision: str | None = None,
        ai_confidence: float | None = None,
        technical_score: float | None = None,
        market_regime: str | None = None,
        correlation_score: float | None = None,
        risk_score: float | None = None,
        sector: str | None = None,
        stop_price: float | None = None,
        target_price: float | None = None,
        metadata: dict[str, Any] | None = None,
        entry_time: str | None = None,
    ) -> TradeRecord:
        record = TradeRecord(
            trade_id=uuid4().hex,
            symbol=str(symbol).upper(),
            market=str(market).upper(),
            side=str(side).upper(),
            entry_time=entry_time or self._now_iso(),
            entry_price=float(entry_price),
            quantity=float(quantity),
            entry_reason=str(entry_reason),
            ai_score=self._optional_float(ai_score),
            ai_decision=ai_decision,
            ai_confidence=self._optional_float(ai_confidence),
            technical_score=self._optional_float(technical_score),
            market_regime=market_regime,
            correlation_score=self._optional_float(correlation_score),
            risk_score=self._optional_float(risk_score),
            sector=sector,
            stop_price=self._optional_float(stop_price),
            target_price=self._optional_float(target_price),
            metadata=dict(metadata or {}),
        )
        self._append_event("OPEN", record.to_dict())
        return record

    def close_trade(
        self,
        trade: TradeRecord | dict[str, Any],
        *,
        exit_price: float,
        exit_reason: str,
        exit_time: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TradeRecord:
        if isinstance(trade, dict):
            record = TradeRecord(**trade)
        else:
            record = trade

        if record.status == "CLOSED":
            raise ValueError("İşlem zaten kapalı.")

        record.exit_time = exit_time or self._now_iso()
        record.exit_price = float(exit_price)
        record.exit_reason = str(exit_reason)
        record.pnl = round(
            self.calculate_pnl(
                side=record.side,
                entry_price=record.entry_price,
                exit_price=record.exit_price,
                quantity=record.quantity,
            ),
            8,
        )
        record.pnl_pct = round(
            self.calculate_pnl_pct(
                side=record.side,
                entry_price=record.entry_price,
                exit_price=record.exit_price,
            ),
            6,
        )
        record.duration_minutes = round(
            self.calculate_duration_minutes(
                record.entry_time,
                record.exit_time,
            ),
            2,
        )
        record.status = "CLOSED"
        if metadata:
            record.metadata.update(metadata)

        self._append_event("CLOSE", record.to_dict())
        return record

    def read_events(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        if not self.storage_path.exists():
            return events

        for line in self.storage_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            events.append(json.loads(line))
        return events

    def latest_trade_state(self, trade_id: str) -> dict[str, Any] | None:
        latest = None
        for event in self.read_events():
            payload = event.get("payload") or {}
            if payload.get("trade_id") == trade_id:
                latest = payload
        return latest

    def closed_trades(self) -> list[dict[str, Any]]:
        latest_by_id: dict[str, dict[str, Any]] = {}
        for event in self.read_events():
            payload = event.get("payload") or {}
            trade_id = payload.get("trade_id")
            if trade_id:
                latest_by_id[trade_id] = payload

        return [
            trade
            for trade in latest_by_id.values()
            if trade.get("status") == "CLOSED"
        ]

    @staticmethod
    def calculate_pnl(
        *,
        side: str,
        entry_price: float,
        exit_price: float,
        quantity: float,
    ) -> float:
        side_upper = str(side).upper()
        direction = -1.0 if side_upper in {"SELL", "SHORT"} else 1.0
        return (float(exit_price) - float(entry_price)) * float(quantity) * direction

    @staticmethod
    def calculate_pnl_pct(
        *,
        side: str,
        entry_price: float,
        exit_price: float,
    ) -> float:
        entry = float(entry_price)
        if entry == 0:
            raise ValueError("Giriş fiyatı sıfır olamaz.")

        side_upper = str(side).upper()
        direction = -1.0 if side_upper in {"SELL", "SHORT"} else 1.0
        return ((float(exit_price) - entry) / entry) * 100.0 * direction

    @staticmethod
    def calculate_duration_minutes(entry_time: str, exit_time: str) -> float:
        start = datetime.fromisoformat(entry_time.replace("Z", "+00:00"))
        end = datetime.fromisoformat(exit_time.replace("Z", "+00:00"))
        return max(0.0, (end - start).total_seconds() / 60.0)

    def _append_event(self, event_type: str, payload: dict[str, Any]) -> None:
        event = {
            "event_type": event_type,
            "logged_at": self._now_iso(),
            "payload": payload,
        }
        with self.storage_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        if value is None:
            return None
        return float(value)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

def analyze_closed_trade(
    trade: TradeRecord | dict[str, Any],
) -> dict[str, Any]:
    """Kapalı işlem kaydından standart analiz özeti üretir."""
    if isinstance(trade, TradeRecord):
        data = trade.to_dict()
    else:
        data = dict(trade)

    pnl = data.get("pnl")
    pnl_pct = data.get("pnl_pct")
    duration = data.get("duration_minutes")
    status = str(data.get("status") or "").upper()

    is_closed = status == "CLOSED"
    is_winner = bool(is_closed and pnl is not None and float(pnl) > 0)
    is_loser = bool(is_closed and pnl is not None and float(pnl) < 0)
    is_breakeven = bool(is_closed and pnl is not None and float(pnl) == 0)

    if not is_closed:
        outcome = "OPEN"
    elif is_winner:
        outcome = "WIN"
    elif is_loser:
        outcome = "LOSS"
    else:
        outcome = "BREAKEVEN"

    return {
        "trade_id": data.get("trade_id"),
        "symbol": data.get("symbol"),
        "market": data.get("market"),
        "side": data.get("side"),
        "status": status or "UNKNOWN",
        "outcome": outcome,
        "is_closed": is_closed,
        "is_winner": is_winner,
        "is_loser": is_loser,
        "is_breakeven": is_breakeven,
        "pnl": None if pnl is None else float(pnl),
        "pnl_pct": None if pnl_pct is None else float(pnl_pct),
        "duration_minutes": None if duration is None else float(duration),
        "entry_reason": data.get("entry_reason"),
        "exit_reason": data.get("exit_reason"),
        "ai_score": data.get("ai_score"),
        "ai_decision": data.get("ai_decision"),
        "technical_score": data.get("technical_score"),
        "market_regime": data.get("market_regime"),
        "correlation_score": data.get("correlation_score"),
        "risk_score": data.get("risk_score"),
    }

