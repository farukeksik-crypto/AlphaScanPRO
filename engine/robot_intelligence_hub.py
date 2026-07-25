from __future__ import annotations

from datetime import datetime
from typing import Any

from database.intelligence_repository import IntelligenceRepository
from engine.decision_trace import build_decision_trace
from engine.models.trade_snapshot import TradeSnapshot


class RobotIntelligenceHub:
    """DecisionTrace, Learning Queue ve TradeSnapshot için tek giriş noktası."""

    def __init__(self, database, logger=None) -> None:
        self.repository = IntelligenceRepository(database)
        self.logger = logger

    @staticmethod
    def _float(value: Any) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    def capture_scan(self, *, run_id: int, rows: list[dict[str, Any]], market: str, universe: str, robot, robot_enabled: bool) -> int:
        events = []
        for row in rows:
            symbol = str(row.get("Kod") or "").strip().upper()
            if not symbol:
                continue
            trace = build_decision_trace(row, robot, robot_enabled=robot_enabled)
            payload = trace.to_dict() if hasattr(trace, "to_dict") else {
                "accepted": trace.accepted, "reject_reasons": list(trace.reject_reasons)
            }
            event = {
                "run_id": run_id, "market": market, "universe": universe, "symbol": symbol,
                "decision": row.get("Karar", ""), "score": self._float(row.get("Puan")),
                "confidence": self._float(row.get("Güven")),
                "probability": self._float(row.get("Başarı Göstergesi %")),
                "risk_level": row.get("Risk", ""), "accepted": trace.accepted,
                "reject_reasons": list(trace.reject_reasons), "trace_payload": payload,
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
            events.append(event)
            self.repository.enqueue(
                event_type="DECISION_ACCEPTED" if trace.accepted else "DECISION_REJECTED",
                market=market, universe=universe, symbol=symbol, payload=event,
            )
        return self.repository.record_decision_events(events)

    def capture_actions(self, *, actions: list[dict[str, Any]], rows: list[dict[str, Any]], market: str, universe: str, account_id: str = "") -> int:
        by_symbol = {str(row.get("Kod") or "").upper(): row for row in rows}
        captured = 0
        for action in actions:
            if not action.get("ok"):
                continue
            symbol = str(action.get("symbol") or "").upper()
            if not symbol:
                continue
            row = by_symbol.get(symbol, {})
            event_type = "TRADE_CLOSED" if "profit" in action else "TRADE_OPENED"
            trade_id = str(action.get("trade_id") or f"{account_id}:{action.get('position_id','')}")
            payload = dict(action)
            payload["scanner_row"] = dict(row)
            self.repository.enqueue(event_type=event_type, market=market, universe=universe, symbol=symbol, trade_id=trade_id, payload=payload)
            if event_type == "TRADE_OPENED":
                snapshot = TradeSnapshot.open(
                    trade_id=trade_id, market=market, universe=universe, symbol=symbol,
                    decision=str(row.get("Karar") or action.get("decision") or ""),
                    score=self._float(row.get("Puan", action.get("score"))),
                    confidence=self._float(row.get("Güven", action.get("confidence"))),
                    probability=self._float(row.get("Başarı Göstergesi %")),
                    risk_level=str(row.get("Risk") or ""), entry_price=self._float(action.get("price")),
                    stop_loss=self._float(row.get("Stop")), take_profit=self._float(row.get("Hedef 1")),
                    take_profit2=self._float(row.get("Hedef 2")), quantity=self._float(action.get("quantity")),
                    atr=self._float(row.get("ATR")), strategy_name=str(action.get("strategy_profile") or "Background"),
                    entry_reason=str(row.get("Neden") or action.get("message") or ""), metadata={"action": action},
                )
                self.repository.save_snapshot(snapshot, position_id=action.get("position_id"), account_id=account_id)
            captured += 1
        return captured
