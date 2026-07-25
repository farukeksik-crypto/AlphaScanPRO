from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from statistics import mean
from typing import Any, Callable

from engine.trade_journal_pro import ensure_trade_journal_pro


def _number(value: Any) -> float:
    try:
        result = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return result if math.isfinite(result) else 0.0


def _metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
    return {}


def _score_band(value: Any) -> str:
    score = _number(value)
    if score < 70:
        return "<70"
    if score < 80:
        return "70-79"
    if score < 85:
        return "80-84"
    if score < 90:
        return "85-89"
    return "90+"


@dataclass(slots=True)
class LearningSegment:
    dimension: str
    segment: str
    sample_size: int
    wins: int
    losses: int
    win_rate_pct: float
    net_pnl: float
    average_pnl: float
    profit_factor: float
    stable: bool
    first_half_pnl: float
    second_half_pnl: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LearningRecommendation:
    priority: str
    title: str
    evidence: str
    proposed_action: str
    automatic_change: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RobotLearningReport:
    generated_at: str
    lookback_days: int
    trade_count: int
    minimum_sample: int
    data_ready: bool
    segments: list[LearningSegment] = field(default_factory=list)
    recommendations: list[LearningRecommendation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "lookback_days": self.lookback_days,
            "trade_count": self.trade_count,
            "minimum_sample": self.minimum_sample,
            "data_ready": self.data_ready,
            "segments": [item.to_dict() for item in self.segments],
            "recommendations": [item.to_dict() for item in self.recommendations],
        }


def _profit_factor(pnls: list[float]) -> float:
    gross_profit = sum(value for value in pnls if value > 0)
    gross_loss = abs(sum(value for value in pnls if value < 0))
    if gross_loss:
        return gross_profit / gross_loss
    return math.inf if gross_profit > 0 else 0.0


def _segment(
    rows: list[dict[str, Any]],
    dimension: str,
    resolver: Callable[[dict[str, Any]], str],
) -> list[LearningSegment]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        buckets.setdefault(resolver(row) or "BİLİNMİYOR", []).append(row)

    output: list[LearningSegment] = []
    for name, items in buckets.items():
        ordered = sorted(items, key=lambda item: str(item.get("closed_at") or ""))
        pnls = [_number(item.get("net_pnl")) for item in ordered]
        midpoint = max(1, len(pnls) // 2)
        first_pnl = sum(pnls[:midpoint])
        second_pnl = sum(pnls[midpoint:])
        stable = len(pnls) >= 4 and first_pnl * second_pnl > 0
        wins = sum(value > 0 for value in pnls)
        losses = sum(value < 0 for value in pnls)
        output.append(LearningSegment(
            dimension=dimension,
            segment=name,
            sample_size=len(items),
            wins=wins,
            losses=losses,
            win_rate_pct=wins / len(items) * 100.0 if items else 0.0,
            net_pnl=sum(pnls),
            average_pnl=mean(pnls) if pnls else 0.0,
            profit_factor=_profit_factor(pnls),
            stable=stable,
            first_half_pnl=first_pnl,
            second_half_pnl=second_pnl,
        ))
    output.sort(key=lambda item: (item.net_pnl, item.sample_size), reverse=True)
    return output


def _prepare_rows(raw_rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in raw_rows:
        item = dict(raw)
        meta = _metadata(item.get("metadata_json"))
        item["decision"] = str(meta.get("decision") or "BİLİNMİYOR")
        item["risk"] = str(meta.get("risk") or meta.get("risk_level") or "BİLİNMİYOR")
        item["strategy"] = str(meta.get("strategy_profile") or "BİLİNMİYOR")
        item["score_band"] = _score_band(item.get("entry_score"))
        rows.append(item)
    return rows


def build_robot_learning_report(
    connection: sqlite3.Connection,
    *,
    lookback_days: int = 90,
    minimum_sample: int = 20,
) -> RobotLearningReport:
    if lookback_days <= 0:
        raise ValueError("lookback_days pozitif olmalıdır.")
    if minimum_sample < 5:
        raise ValueError("minimum_sample en az 5 olmalıdır.")

    connection.row_factory = sqlite3.Row
    ensure_trade_journal_pro(connection)
    cutoff = (datetime.now() - timedelta(days=lookback_days)).isoformat(timespec="seconds")
    raw_rows = connection.execute(
        "SELECT * FROM trade_journal_pro WHERE closed_at >= ? ORDER BY closed_at",
        (cutoff,),
    ).fetchall()
    rows = _prepare_rows(raw_rows)

    segments: list[LearningSegment] = []
    segments.extend(_segment(rows, "Puan Bandı", lambda row: str(row["score_band"])))
    segments.extend(_segment(rows, "Risk", lambda row: str(row["risk"])))
    segments.extend(_segment(rows, "Karar", lambda row: str(row["decision"])))
    segments.extend(_segment(rows, "Strateji", lambda row: str(row["strategy"])))
    segments.extend(_segment(rows, "Çıkış", lambda row: str(row.get("exit_action") or row.get("event_type") or "BİLİNMİYOR")))

    recommendations: list[LearningRecommendation] = []
    if len(rows) < minimum_sample:
        recommendations.append(LearningRecommendation(
            priority="BİLGİ",
            title="Öğrenme için veri birikiyor",
            evidence=f"{len(rows)} kapalı işlem var; güvenilir yorum eşiği {minimum_sample}.",
            proposed_action="Robotu mevcut kurallarla sanal işlemde çalıştırmaya devam et.",
        ))
    else:
        eligible = [item for item in segments if item.sample_size >= minimum_sample and item.stable]
        strong = [item for item in eligible if item.net_pnl > 0 and item.profit_factor >= 1.20]
        weak = [item for item in eligible if item.net_pnl < 0 and item.profit_factor < 0.90]
        if strong:
            best = max(strong, key=lambda item: (item.profit_factor, item.net_pnl))
            recommendations.append(LearningRecommendation(
                priority="FIRSAT",
                title=f"{best.dimension}: {best.segment} istikrarlı güçlü",
                evidence=(f"{best.sample_size} işlem, %{best.win_rate_pct:.1f} başarı, "
                          f"PF {best.profit_factor:.2f}, net PnL {best.net_pnl:.2f}; iki yarı da pozitif."),
                proposed_action="Ayrı gölge profilde önceliklendir; ana robot eşiğini otomatik değiştirme.",
            ))
        if weak:
            worst = min(weak, key=lambda item: (item.profit_factor, item.net_pnl))
            recommendations.append(LearningRecommendation(
                priority="UYARI",
                title=f"{worst.dimension}: {worst.segment} istikrarlı zayıf",
                evidence=(f"{worst.sample_size} işlem, %{worst.win_rate_pct:.1f} başarı, "
                          f"PF {worst.profit_factor:.2f}, net PnL {worst.net_pnl:.2f}; iki yarı da negatif."),
                proposed_action="Bu segmenti yalnızca backtest ve gölge robotta daha sıkı koşullarla karşılaştır.",
            ))
        if not recommendations:
            recommendations.append(LearningRecommendation(
                priority="BİLGİ",
                title="Kararlı üstün segment henüz oluşmadı",
                evidence="Yeterli toplam veri var ancak örneklem ve dönem tutarlılığı birlikte sağlanmadı.",
                proposed_action="Filtreleri değiştirmeden veri toplamaya devam et ve raporu yeniden değerlendir.",
            ))

    return RobotLearningReport(
        generated_at=datetime.now().isoformat(timespec="seconds"),
        lookback_days=lookback_days,
        trade_count=len(rows),
        minimum_sample=minimum_sample,
        data_ready=len(rows) >= minimum_sample,
        segments=segments,
        recommendations=recommendations,
    )
