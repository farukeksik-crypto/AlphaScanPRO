from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class StressScenario:
    name: str
    shock_pct: float

    def __post_init__(self) -> None:
        if self.shock_pct >= 0 or self.shock_pct < -100:
            raise ValueError("shock_pct -100 ile 0 arasında olmalıdır.")


@dataclass
class PortfolioRiskReport:
    equity: float
    total_exposure: float
    total_stop_risk: float
    exposure_pct: float
    stop_risk_pct: float
    largest_symbol_pct: float
    concentration_hhi: float
    effective_position_count: float
    risk_level: str
    recommended_risk_per_trade_pct: float
    symbol_exposure: list[dict[str, Any]] = field(default_factory=list)
    group_exposure: list[dict[str, Any]] = field(default_factory=list)
    stress_results: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _number(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if result == result else default


def _read(position: Any, key: str, default: Any = None) -> Any:
    if isinstance(position, Mapping):
        return position.get(key, default)
    return getattr(position, key, default)


def _normalize_position(position: Any) -> dict[str, Any]:
    symbol = str(_read(position, "symbol", "UNKNOWN") or "UNKNOWN").upper()
    group = str(
        _read(position, "group", None)
        or _read(position, "universe", None)
        or _read(position, "market", None)
        or "DEFAULT"
    ).upper()
    quantity = abs(_number(_read(position, "quantity", 0.0)))
    entry_price = _number(_read(position, "entry_price", 0.0))
    current_price = _number(
        _read(position, "current_price", None),
        _number(_read(position, "price", None), entry_price),
    )
    if current_price <= 0:
        current_price = entry_price
    stop_price = _number(_read(position, "stop_price", entry_price), entry_price)
    market_value = quantity * max(current_price, 0.0)
    stop_risk = quantity * abs(entry_price - stop_price)
    return {
        "symbol": symbol,
        "group": group,
        "quantity": quantity,
        "entry_price": entry_price,
        "current_price": current_price,
        "stop_price": stop_price,
        "market_value": market_value,
        "stop_risk": stop_risk,
    }


def _aggregate(rows: list[dict[str, Any]], key: str, equity: float) -> list[dict[str, Any]]:
    totals: dict[str, dict[str, float]] = {}
    for row in rows:
        bucket = totals.setdefault(str(row[key]), {"market_value": 0.0, "stop_risk": 0.0})
        bucket["market_value"] += row["market_value"]
        bucket["stop_risk"] += row["stop_risk"]
    result = []
    for name, values in totals.items():
        result.append(
            {
                key: name,
                "market_value": values["market_value"],
                "exposure_pct": values["market_value"] / equity * 100 if equity > 0 else 0.0,
                "stop_risk": values["stop_risk"],
                "stop_risk_pct": values["stop_risk"] / equity * 100 if equity > 0 else 0.0,
            }
        )
    return sorted(result, key=lambda item: item["market_value"], reverse=True)


def recommend_risk_per_trade(
    *,
    base_risk_pct: float,
    exposure_utilization_pct: float,
    stop_risk_utilization_pct: float,
    daily_loss_utilization_pct: float = 0.0,
    minimum_risk_pct: float = 0.10,
) -> float:
    """Portföy kullanımı arttıkça yeni işlem riskini kademeli azaltır."""
    base = max(_number(base_risk_pct), 0.0)
    minimum = max(min(_number(minimum_risk_pct), base), 0.0)
    pressure = max(
        _number(exposure_utilization_pct),
        _number(stop_risk_utilization_pct),
        _number(daily_loss_utilization_pct),
    )
    if pressure >= 100:
        factor = 0.0
    elif pressure >= 85:
        factor = 0.25
    elif pressure >= 70:
        factor = 0.50
    elif pressure >= 50:
        factor = 0.75
    else:
        factor = 1.0
    if factor == 0.0:
        return 0.0
    return round(max(base * factor, minimum), 4)


def build_portfolio_risk_report(
    positions: Iterable[Any],
    *,
    equity: float,
    max_total_exposure_pct: float = 75.0,
    max_total_risk_pct: float = 5.0,
    max_symbol_exposure_pct: float = 25.0,
    base_risk_per_trade_pct: float = 1.0,
    daily_loss_pct: float = 0.0,
    daily_loss_limit_pct: float = 3.0,
    scenarios: Iterable[StressScenario] | None = None,
) -> PortfolioRiskReport:
    equity = _number(equity)
    if equity <= 0:
        raise ValueError("equity pozitif olmalıdır.")
    rows = [_normalize_position(position) for position in positions]
    rows = [row for row in rows if row["market_value"] > 0]
    total_exposure = sum(row["market_value"] for row in rows)
    total_stop_risk = sum(row["stop_risk"] for row in rows)
    exposure_pct = total_exposure / equity * 100
    stop_risk_pct = total_stop_risk / equity * 100

    symbol_exposure = _aggregate(rows, "symbol", equity)
    group_exposure = _aggregate(rows, "group", equity)
    weights = [item["market_value"] / total_exposure for item in symbol_exposure] if total_exposure else []
    hhi = sum(weight * weight for weight in weights)
    effective_count = 1.0 / hhi if hhi > 0 else 0.0
    largest_symbol_pct = symbol_exposure[0]["exposure_pct"] if symbol_exposure else 0.0

    exposure_util = exposure_pct / max_total_exposure_pct * 100 if max_total_exposure_pct > 0 else 0.0
    risk_util = stop_risk_pct / max_total_risk_pct * 100 if max_total_risk_pct > 0 else 0.0
    daily_loss_util = daily_loss_pct / daily_loss_limit_pct * 100 if daily_loss_limit_pct > 0 else 0.0
    recommendation = recommend_risk_per_trade(
        base_risk_pct=base_risk_per_trade_pct,
        exposure_utilization_pct=exposure_util,
        stop_risk_utilization_pct=risk_util,
        daily_loss_utilization_pct=daily_loss_util,
    )

    warnings: list[str] = []
    if exposure_pct >= max_total_exposure_pct:
        warnings.append("Toplam portföy maruziyeti limite ulaştı veya limiti aştı.")
    elif exposure_util >= 85:
        warnings.append("Toplam maruziyet kapasitesinin en az %85'i kullanılıyor.")
    if stop_risk_pct >= max_total_risk_pct:
        warnings.append("Toplam stop riski limite ulaştı veya limiti aştı.")
    elif risk_util >= 85:
        warnings.append("Toplam stop riski kapasitesinin en az %85'i kullanılıyor.")
    if largest_symbol_pct > max_symbol_exposure_pct:
        warnings.append("En büyük sembol ağırlığı sembol limitini aşıyor.")
    if len(symbol_exposure) >= 2 and hhi > 0.35:
        warnings.append("Portföy birkaç sembolde yoğunlaşmış görünüyor.")
    if daily_loss_util >= 100:
        warnings.append("Günlük zarar limiti doldu; yeni işlem riski sıfırlanmalı.")

    pressure = max(exposure_util, risk_util, daily_loss_util)
    if pressure >= 100 or len(warnings) >= 3:
        risk_level = "KRİTİK"
    elif pressure >= 85 or hhi > 0.35:
        risk_level = "YÜKSEK"
    elif pressure >= 60:
        risk_level = "ORTA"
    else:
        risk_level = "DÜŞÜK"

    scenario_list = list(scenarios or (
        StressScenario("Hafif düşüş", -5.0),
        StressScenario("Sert düzeltme", -10.0),
        StressScenario("Şok senaryosu", -15.0),
    ))
    stress_results = []
    for scenario in scenario_list:
        loss = total_exposure * abs(scenario.shock_pct) / 100
        stressed_equity = max(equity - loss, 0.0)
        stress_results.append({
            "scenario": scenario.name,
            "shock_pct": scenario.shock_pct,
            "estimated_loss": loss,
            "loss_pct_equity": loss / equity * 100,
            "stressed_equity": stressed_equity,
        })

    return PortfolioRiskReport(
        equity=equity,
        total_exposure=total_exposure,
        total_stop_risk=total_stop_risk,
        exposure_pct=exposure_pct,
        stop_risk_pct=stop_risk_pct,
        largest_symbol_pct=largest_symbol_pct,
        concentration_hhi=hhi,
        effective_position_count=effective_count,
        risk_level=risk_level,
        recommended_risk_per_trade_pct=recommendation,
        symbol_exposure=symbol_exposure,
        group_exposure=group_exposure,
        stress_results=stress_results,
        warnings=warnings,
    )
