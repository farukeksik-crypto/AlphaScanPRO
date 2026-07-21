from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


@dataclass
class EquityPoint:
    index: int
    timestamp: str
    pnl: float
    equity: float
    peak_equity: float
    drawdown_value: float
    drawdown_pct: float
    drawdown_duration: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DrawdownSummary:
    initial_equity: float
    final_equity: float
    net_pnl: float
    total_points: int
    max_equity: float
    min_equity: float
    current_drawdown_value: float
    current_drawdown_pct: float
    max_drawdown_value: float
    max_drawdown_pct: float
    max_drawdown_duration: int
    longest_recovery_duration: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EquityDrawdownEngine:
    def build_equity_curve(
        self,
        trades: Iterable[dict[str, Any]],
        *,
        initial_equity: float = 100000.0,
        timestamp_field: str = "exit_time",
    ) -> list[EquityPoint]:
        closed = [
            dict(trade)
            for trade in trades
            if str(trade.get("status") or "").upper() == "CLOSED"
            and trade.get("pnl") is not None
        ]

        closed.sort(key=lambda item: str(item.get(timestamp_field) or ""))

        equity = float(initial_equity)
        peak = equity
        active_drawdown_duration = 0
        points: list[EquityPoint] = []

        for index, trade in enumerate(closed, start=1):
            pnl = float(trade.get("pnl") or 0.0)
            equity += pnl

            if equity >= peak:
                peak = equity
                active_drawdown_duration = 0
            else:
                active_drawdown_duration += 1

            drawdown_value = peak - equity
            drawdown_pct = (
                (drawdown_value / peak) * 100.0
                if peak != 0
                else 0.0
            )

            timestamp = str(
                trade.get(timestamp_field)
                or trade.get("entry_time")
                or f"TRADE-{index}"
            )

            points.append(
                EquityPoint(
                    index=index,
                    timestamp=timestamp,
                    pnl=round(pnl, 8),
                    equity=round(equity, 8),
                    peak_equity=round(peak, 8),
                    drawdown_value=round(drawdown_value, 8),
                    drawdown_pct=round(drawdown_pct, 8),
                    drawdown_duration=active_drawdown_duration,
                )
            )

        return points

    def summarize(
        self,
        equity_curve: Iterable[EquityPoint | dict[str, Any]],
        *,
        initial_equity: float = 100000.0,
    ) -> DrawdownSummary:
        points = [
            point.to_dict() if isinstance(point, EquityPoint) else dict(point)
            for point in equity_curve
        ]

        if not points:
            initial = float(initial_equity)
            return DrawdownSummary(
                initial_equity=initial,
                final_equity=initial,
                net_pnl=0.0,
                total_points=0,
                max_equity=initial,
                min_equity=initial,
                current_drawdown_value=0.0,
                current_drawdown_pct=0.0,
                max_drawdown_value=0.0,
                max_drawdown_pct=0.0,
                max_drawdown_duration=0,
                longest_recovery_duration=0,
            )

        equities = [float(point["equity"]) for point in points]
        drawdowns = [float(point["drawdown_value"]) for point in points]
        drawdown_pcts = [float(point["drawdown_pct"]) for point in points]
        durations = [int(point["drawdown_duration"]) for point in points]

        final_equity = equities[-1]
        last = points[-1]

        longest_recovery = self._longest_recovery_duration(points)

        return DrawdownSummary(
            initial_equity=round(float(initial_equity), 8),
            final_equity=round(final_equity, 8),
            net_pnl=round(final_equity - float(initial_equity), 8),
            total_points=len(points),
            max_equity=round(max(equities), 8),
            min_equity=round(min(equities), 8),
            current_drawdown_value=round(
                float(last["drawdown_value"]),
                8,
            ),
            current_drawdown_pct=round(
                float(last["drawdown_pct"]),
                8,
            ),
            max_drawdown_value=round(max(drawdowns), 8),
            max_drawdown_pct=round(max(drawdown_pcts), 8),
            max_drawdown_duration=max(durations),
            longest_recovery_duration=longest_recovery,
        )

    def daily_snapshots(
        self,
        equity_curve: Iterable[EquityPoint | dict[str, Any]],
    ) -> list[dict[str, Any]]:
        latest_by_day: dict[str, dict[str, Any]] = {}

        for point in equity_curve:
            data = point.to_dict() if isinstance(point, EquityPoint) else dict(point)
            day = self._extract_day(str(data.get("timestamp") or ""))
            latest_by_day[day] = data

        return [
            {
                "date": day,
                "equity": float(data["equity"]),
                "peak_equity": float(data["peak_equity"]),
                "drawdown_value": float(data["drawdown_value"]),
                "drawdown_pct": float(data["drawdown_pct"]),
            }
            for day, data in sorted(latest_by_day.items())
        ]

    def full_report(
        self,
        trades: Iterable[dict[str, Any]],
        *,
        initial_equity: float = 100000.0,
    ) -> dict[str, Any]:
        curve = self.build_equity_curve(
            trades,
            initial_equity=initial_equity,
        )
        summary = self.summarize(
            curve,
            initial_equity=initial_equity,
        )
        return {
            "summary": summary.to_dict(),
            "equity_curve": [point.to_dict() for point in curve],
            "daily_snapshots": self.daily_snapshots(curve),
        }

    def export_json(
        self,
        report: dict[str, Any],
        path: str | Path,
    ) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return target

    @staticmethod
    def _extract_day(timestamp: str) -> str:
        value = timestamp.strip()
        if not value:
            return "UNKNOWN"

        try:
            return datetime.fromisoformat(
                value.replace("Z", "+00:00")
            ).date().isoformat()
        except ValueError:
            return value[:10] if len(value) >= 10 else value

    @staticmethod
    def _longest_recovery_duration(
        points: list[dict[str, Any]],
    ) -> int:
        longest = 0
        current = 0

        for point in points:
            if float(point.get("drawdown_value") or 0.0) > 0:
                current += 1
                longest = max(longest, current)
            else:
                current = 0

        return longest
