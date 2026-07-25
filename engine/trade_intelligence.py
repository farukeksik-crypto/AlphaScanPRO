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


@dataclass(frozen=True)
class ClosedTradeAnalytics:
    """RobotEngine tarafından trade_history tablosuna yazılan kapanış metrikleri."""

    profit_pct: float
    holding_minutes: float
    mfe_pct: float
    mae_pct: float
    risk_pct: float
    reward_pct: float
    risk_reward: float
    entry_efficiency: float
    exit_efficiency: float
    trade_quality_score: float
    trade_grade: str

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
        start = _parse_datetime(entry_time)
        end = _parse_datetime(exit_time)
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


def _parse_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        result = datetime.fromisoformat(text)

    # Naive ve timezone-aware tarihlerin çıkarılmasında TypeError oluşmasını önle.
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, float(value)))


def _grade(score: float) -> str:
    if score >= 90:
        return "A+"
    if score >= 80:
        return "A"
    if score >= 70:
        return "B"
    if score >= 60:
        return "C"
    if score >= 50:
        return "D"
    return "F"


def _analyze_trade_record(trade: TradeRecord | dict[str, Any]) -> dict[str, Any]:
    """Eski API: TradeRecord/dict alır ve standart özet sözlüğü döndürür."""
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


def _analyze_robot_close(
    *,
    entry_price: float,
    exit_price: float,
    quantity: float,
    total_profit: float,
    opened_at: str | datetime,
    closed_at: str | datetime,
    highest_price: float | None = None,
    lowest_price: float | None = None,
    stop_price: float | None = None,
    target_price: float | None = None,
    technical_score: float = 0.0,
    confidence_score: float = 0.0,
) -> ClosedTradeAnalytics:
    """Yeni RobotEngine API'si için kapanış analizini üretir."""
    entry = float(entry_price)
    exit_value = float(exit_price)
    qty = float(quantity)
    profit = float(total_profit)

    if entry <= 0:
        raise ValueError("Giriş fiyatı sıfırdan büyük olmalı.")
    if exit_value <= 0:
        raise ValueError("Çıkış fiyatı sıfırdan büyük olmalı.")
    if qty <= 0:
        raise ValueError("Miktar sıfırdan büyük olmalı.")

    position_value = entry * qty
    profit_pct = (profit / position_value * 100.0) if position_value else 0.0

    opened = _parse_datetime(opened_at)
    closed = _parse_datetime(closed_at)
    holding_minutes = max(0.0, (closed - opened).total_seconds() / 60.0)

    high = _float_or_none(highest_price)
    low = _float_or_none(lowest_price)
    high = max(entry, exit_value, high if high is not None else entry)
    low = min(entry, exit_value, low if low is not None else entry)

    mfe_pct = max(0.0, ((high - entry) / entry) * 100.0)
    mae_pct = max(0.0, ((entry - low) / entry) * 100.0)

    stop = _float_or_none(stop_price)
    target = _float_or_none(target_price)
    risk_pct = (
        max(0.0, ((entry - stop) / entry) * 100.0)
        if stop is not None and stop > 0
        else 0.0
    )
    reward_pct = (
        max(0.0, ((target - entry) / entry) * 100.0)
        if target is not None and target > 0
        else 0.0
    )
    risk_reward = reward_pct / risk_pct if risk_pct > 0 else 0.0

    price_range = high - low
    entry_efficiency = (
        _clamp(((high - entry) / price_range) * 100.0)
        if price_range > 0
        else 50.0
    )
    exit_efficiency = (
        _clamp(((exit_value - entry) / (high - entry)) * 100.0)
        if high > entry
        else (100.0 if exit_value >= entry else 0.0)
    )

    technical_component = _clamp(technical_score)
    confidence_component = _clamp(confidence_score)
    outcome_component = _clamp(50.0 + profit_pct * 8.0)
    excursion_component = _clamp(50.0 + (mfe_pct - mae_pct) * 5.0)
    rr_component = _clamp(risk_reward * 25.0)

    quality_score = _clamp(
        outcome_component * 0.30
        + exit_efficiency * 0.20
        + entry_efficiency * 0.10
        + technical_component * 0.15
        + confidence_component * 0.15
        + excursion_component * 0.05
        + rr_component * 0.05
    )

    return ClosedTradeAnalytics(
        profit_pct=round(profit_pct, 6),
        holding_minutes=round(holding_minutes, 2),
        mfe_pct=round(mfe_pct, 6),
        mae_pct=round(mae_pct, 6),
        risk_pct=round(risk_pct, 6),
        reward_pct=round(reward_pct, 6),
        risk_reward=round(risk_reward, 6),
        entry_efficiency=round(entry_efficiency, 2),
        exit_efficiency=round(exit_efficiency, 2),
        trade_quality_score=round(quality_score, 2),
        trade_grade=_grade(quality_score),
    )


def analyze_closed_trade(
    trade: TradeRecord | dict[str, Any] | None = None,
    *,
    entry_price: float | None = None,
    exit_price: float | None = None,
    quantity: float | None = None,
    total_profit: float | None = None,
    opened_at: str | datetime | None = None,
    closed_at: str | datetime | None = None,
    highest_price: float | None = None,
    lowest_price: float | None = None,
    stop_price: float | None = None,
    target_price: float | None = None,
    technical_score: float = 0.0,
    confidence_score: float = 0.0,
) -> dict[str, Any] | ClosedTradeAnalytics:
    """
    Kapalı işlemi analiz eder.

    Geriye uyumluluk:
      - analyze_closed_trade(trade) -> dict
      - analyze_closed_trade(entry_price=..., ...) -> ClosedTradeAnalytics
    """
    if trade is not None:
        robot_arguments_supplied = any(
            value is not None
            for value in (
                entry_price,
                exit_price,
                quantity,
                total_profit,
                opened_at,
                closed_at,
            )
        )
        if robot_arguments_supplied:
            raise TypeError(
                "trade ile yeni RobotEngine parametreleri aynı çağrıda kullanılamaz."
            )
        return _analyze_trade_record(trade)

    required = {
        "entry_price": entry_price,
        "exit_price": exit_price,
        "quantity": quantity,
        "total_profit": total_profit,
        "opened_at": opened_at,
        "closed_at": closed_at,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        raise TypeError(
            "Eksik analyze_closed_trade parametreleri: " + ", ".join(missing)
        )

    return _analyze_robot_close(
        entry_price=float(entry_price),
        exit_price=float(exit_price),
        quantity=float(quantity),
        total_profit=float(total_profit),
        opened_at=opened_at,
        closed_at=closed_at,
        highest_price=highest_price,
        lowest_price=lowest_price,
        stop_price=stop_price,
        target_price=target_price,
        technical_score=float(technical_score or 0.0),
        confidence_score=float(confidence_score or 0.0),
    )
