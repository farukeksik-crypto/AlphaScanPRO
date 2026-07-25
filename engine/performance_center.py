from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime
from statistics import mean
from typing import Any, Iterable


def _number(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _metadata(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("metadata")
    if isinstance(raw, dict):
        return raw
    raw = row.get("metadata_json")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else {}
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


def _holding_band(value: Any) -> str:
    minutes = _number(value)
    if minutes < 60:
        return "<1 saat"
    if minutes < 360:
        return "1-6 saat"
    if minutes < 1440:
        return "6-24 saat"
    if minutes < 4320:
        return "1-3 gün"
    return "3+ gün"


def _safe_profit_factor(pnls: list[float]) -> float:
    gross_profit = sum(v for v in pnls if v > 0)
    gross_loss = abs(sum(v for v in pnls if v < 0))
    if gross_loss > 0:
        return gross_profit / gross_loss
    return math.inf if gross_profit > 0 else 0.0


@dataclass(slots=True)
class SegmentStats:
    segment: str
    trade_count: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    net_pnl: float
    average_pnl: float
    profit_factor: float
    average_holding_minutes: float
    average_mfe_pct: float
    average_mae_pct: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ComparisonStats:
    group: str
    trade_count: int
    average_entry_score: float
    average_exit_score: float
    average_confirmations: float
    average_holding_minutes: float
    average_mfe_pct: float
    average_mae_pct: float
    break_even_rate_pct: float
    trailing_rate_pct: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PerformanceRecommendation:
    severity: str
    title: str
    detail: str
    evidence: str
    action: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(slots=True)
class PerformanceCenterReport:
    trade_count: int
    date_from: str
    date_to: str
    score_bands: list[SegmentStats] = field(default_factory=list)
    holding_bands: list[SegmentStats] = field(default_factory=list)
    decision_stats: list[SegmentStats] = field(default_factory=list)
    risk_stats: list[SegmentStats] = field(default_factory=list)
    strategy_stats: list[SegmentStats] = field(default_factory=list)
    winner_loser_comparison: list[ComparisonStats] = field(default_factory=list)
    recommendations: list[PerformanceRecommendation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_count": self.trade_count,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "score_bands": [item.to_dict() for item in self.score_bands],
            "holding_bands": [item.to_dict() for item in self.holding_bands],
            "decision_stats": [item.to_dict() for item in self.decision_stats],
            "risk_stats": [item.to_dict() for item in self.risk_stats],
            "strategy_stats": [item.to_dict() for item in self.strategy_stats],
            "winner_loser_comparison": [item.to_dict() for item in self.winner_loser_comparison],
            "recommendations": [item.to_dict() for item in self.recommendations],
        }


def _enrich(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    meta = _metadata(item)
    item["net_pnl"] = _number(item.get("net_pnl"))
    item["entry_score"] = _number(item.get("entry_score"))
    item["exit_score"] = _number(item.get("exit_score"))
    item["confirmations"] = _number(item.get("confirmations"))
    item["holding_minutes"] = _number(item.get("holding_minutes"))
    item["mfe_pct"] = _number(item.get("mfe_pct"))
    item["mae_pct"] = _number(item.get("mae_pct"))
    item["break_even_active"] = bool(item.get("break_even_active"))
    item["trailing_active"] = bool(item.get("trailing_active"))
    item["decision"] = str(meta.get("decision") or item.get("decision") or "BİLİNMİYOR")
    item["risk"] = str(meta.get("risk") or meta.get("risk_level") or item.get("risk") or "BİLİNMİYOR")
    item["strategy"] = str(meta.get("strategy_profile") or item.get("strategy_profile") or "BİLİNMİYOR")
    item["score_band"] = _score_band(item["entry_score"])
    item["holding_band"] = _holding_band(item["holding_minutes"])
    return item


def _segment(rows: list[dict[str, Any]], field_name: str) -> list[SegmentStats]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[str(row.get(field_name) or "BİLİNMİYOR")].append(row)
    result: list[SegmentStats] = []
    for key, items in buckets.items():
        pnls = [item["net_pnl"] for item in items]
        wins = [v for v in pnls if v > 0]
        losses = [v for v in pnls if v < 0]
        result.append(SegmentStats(
            segment=key,
            trade_count=len(items),
            winning_trades=len(wins),
            losing_trades=len(losses),
            win_rate_pct=(len(wins) / len(items) * 100.0) if items else 0.0,
            net_pnl=sum(pnls),
            average_pnl=mean(pnls) if pnls else 0.0,
            profit_factor=_safe_profit_factor(pnls),
            average_holding_minutes=mean(item["holding_minutes"] for item in items),
            average_mfe_pct=mean(item["mfe_pct"] for item in items),
            average_mae_pct=mean(item["mae_pct"] for item in items),
        ))
    result.sort(key=lambda x: (x.net_pnl, x.trade_count), reverse=True)
    return result


def _comparison(rows: list[dict[str, Any]]) -> list[ComparisonStats]:
    groups = {
        "Kazanan": [row for row in rows if row["net_pnl"] > 0],
        "Kaybeden": [row for row in rows if row["net_pnl"] < 0],
        "Başa baş": [row for row in rows if row["net_pnl"] == 0],
    }
    result: list[ComparisonStats] = []
    for name, items in groups.items():
        if not items:
            continue
        count = len(items)
        result.append(ComparisonStats(
            group=name,
            trade_count=count,
            average_entry_score=mean(item["entry_score"] for item in items),
            average_exit_score=mean(item["exit_score"] for item in items),
            average_confirmations=mean(item["confirmations"] for item in items),
            average_holding_minutes=mean(item["holding_minutes"] for item in items),
            average_mfe_pct=mean(item["mfe_pct"] for item in items),
            average_mae_pct=mean(item["mae_pct"] for item in items),
            break_even_rate_pct=sum(1 for item in items if item["break_even_active"]) / count * 100.0,
            trailing_rate_pct=sum(1 for item in items if item["trailing_active"]) / count * 100.0,
        ))
    return result


def _recommendations(
    rows: list[dict[str, Any]],
    score_stats: list[SegmentStats],
    holding_stats: list[SegmentStats],
    risk_stats: list[SegmentStats],
    *,
    min_sample: int,
) -> list[PerformanceRecommendation]:
    if len(rows) < min_sample:
        return [PerformanceRecommendation(
            severity="BİLGİ",
            title="Veri birikimi sürüyor",
            detail=f"Güvenilir optimizasyon yorumu için en az {min_sample} kapalı işlem hedefleniyor.",
            evidence=f"Mevcut örneklem: {len(rows)} işlem.",
            action="Robotu mevcut eşiklerle çalıştırmaya devam et; henüz filtre değiştirme.",
        )]

    output: list[PerformanceRecommendation] = []
    eligible_scores = [x for x in score_stats if x.trade_count >= min_sample]
    profitable_scores = [x for x in eligible_scores if x.net_pnl > 0 and x.profit_factor >= 1.1]
    weak_scores = [x for x in eligible_scores if x.net_pnl < 0 and x.profit_factor < 0.9]
    if profitable_scores:
        best = max(profitable_scores, key=lambda x: (x.profit_factor, x.net_pnl))
        output.append(PerformanceRecommendation(
            severity="FIRSAT",
            title=f"{best.segment} puan bandı güçlü görünüyor",
            detail="Bu bant, mevcut örneklem içinde daha kaliteli sonuç üretiyor.",
            evidence=f"{best.trade_count} işlem, %{best.win_rate_pct:.1f} başarı, PF {best.profit_factor:.2f}, net PnL {best.net_pnl:.2f}.",
            action="Eşiği otomatik değiştirme; bu bandı izleme listesinde önceliklendir ve yeni veriyle yeniden doğrula.",
        ))
    if weak_scores:
        worst = min(weak_scores, key=lambda x: (x.profit_factor, x.net_pnl))
        output.append(PerformanceRecommendation(
            severity="UYARI",
            title=f"{worst.segment} puan bandı zayıf",
            detail="Bu puan aralığındaki işlemler zarar ve düşük profit factor üretiyor.",
            evidence=f"{worst.trade_count} işlem, %{worst.win_rate_pct:.1f} başarı, PF {worst.profit_factor:.2f}, net PnL {worst.net_pnl:.2f}.",
            action="Doğrudan kapatma yapma; ek güven/olasılık koşuluyla ayrı backtest ve gölge test uygula.",
        ))

    eligible_risks = [x for x in risk_stats if x.trade_count >= min_sample]
    weak_risks = [x for x in eligible_risks if x.net_pnl < 0 and x.profit_factor < 1.0]
    if weak_risks:
        worst = min(weak_risks, key=lambda x: x.net_pnl)
        output.append(PerformanceRecommendation(
            severity="RİSK",
            title=f"{worst.segment} risk sınıfı dikkat istiyor",
            detail="Bu risk sınıfı, örneklemde negatif katkı üretmiş.",
            evidence=f"{worst.trade_count} işlem, PF {worst.profit_factor:.2f}, net PnL {worst.net_pnl:.2f}.",
            action="Pozisyon boyutunu azaltma veya daha yüksek giriş eşiği senaryosunu laboratuvarda test et.",
        ))

    eligible_holding = [x for x in holding_stats if x.trade_count >= min_sample]
    weak_holding = [x for x in eligible_holding if x.net_pnl < 0]
    if weak_holding:
        worst = min(weak_holding, key=lambda x: x.net_pnl)
        output.append(PerformanceRecommendation(
            severity="ÇIKIŞ",
            title=f"{worst.segment} tutma süresi verimsiz",
            detail="Bu süre grubunda işlemler toplamda negatif sonuçlanmış.",
            evidence=f"{worst.trade_count} işlem, ortalama PnL {worst.average_pnl:.2f}, net PnL {worst.net_pnl:.2f}.",
            action="Time-exit ve trailing parametrelerini yalnızca bu süre grubu için simülasyonda karşılaştır.",
        ))

    winners = [row for row in rows if row["net_pnl"] > 0]
    losers = [row for row in rows if row["net_pnl"] < 0]
    if winners and losers:
        win_mae = mean(row["mae_pct"] for row in winners)
        loss_mae = mean(row["mae_pct"] for row in losers)
        if abs(loss_mae) > abs(win_mae) * 1.5 and len(losers) >= min_sample:
            output.append(PerformanceRecommendation(
                severity="STOP",
                title="Kaybeden işlemlerde ters hareket büyüyor",
                detail="Kaybeden grubun ortalama MAE değeri kazanan gruba göre belirgin biçimde daha olumsuz.",
                evidence=f"Kazanan MAE %{win_mae:.2f}; kaybeden MAE %{loss_mae:.2f}.",
                action="Daha sıkı stop önerisini geçmiş veride ve gölge robotta test et; canlı eşikleri otomatik değiştirme.",
            ))

    if not output:
        output.append(PerformanceRecommendation(
            severity="DENGELİ",
            title="Belirgin tekil sorun saptanmadı",
            detail="Mevcut segmentlerde güçlü ve tekrarlanabilir bir optimizasyon sinyali oluşmadı.",
            evidence=f"{len(rows)} işlem analiz edildi.",
            action="Veri toplamaya devam et ve en az bir tam piyasa döngüsü sonrası tekrar değerlendir.",
        ))
    return output


def build_performance_center_report(
    rows: Iterable[dict[str, Any]],
    *,
    min_sample: int = 10,
) -> PerformanceCenterReport:
    if min_sample < 2:
        raise ValueError("min_sample en az 2 olmalıdır")
    enriched = [_enrich(dict(row)) for row in rows]
    dates = sorted(str(row.get("closed_at") or "") for row in enriched if row.get("closed_at"))
    score_stats = _segment(enriched, "score_band")
    holding_stats = _segment(enriched, "holding_band")
    risk_stats = _segment(enriched, "risk")
    return PerformanceCenterReport(
        trade_count=len(enriched),
        date_from=dates[0] if dates else "",
        date_to=dates[-1] if dates else "",
        score_bands=score_stats,
        holding_bands=holding_stats,
        decision_stats=_segment(enriched, "decision"),
        risk_stats=risk_stats,
        strategy_stats=_segment(enriched, "strategy"),
        winner_loser_comparison=_comparison(enriched),
        recommendations=_recommendations(
            enriched, score_stats, holding_stats, risk_stats, min_sample=min_sample
        ),
    )
