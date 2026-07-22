from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class TradePerformanceSummary:
    closed_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0
    win_rate_pct: float = 0.0
    net_profit: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    profit_factor: float | None = None
    average_profit: float = 0.0
    average_win: float = 0.0
    average_loss: float = 0.0
    payoff_ratio: float | None = None
    average_profit_pct: float = 0.0
    average_holding_minutes: float = 0.0
    maximum_drawdown: float = 0.0
    maximum_drawdown_pct: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    average_mfe_pct: float = 0.0
    average_mae_pct: float = 0.0
    average_quality_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def closed_trade_rows(history: pd.DataFrame | None) -> pd.DataFrame:
    """Robot geçmişinden yalnızca kapanış (SELL) kayıtlarını güvenli biçimde döndürür."""
    if history is None or history.empty or "side" not in history.columns:
        return pd.DataFrame()
    return history[history["side"].astype(str).str.upper().eq("SELL")].copy()


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def _safe_mean(series: pd.Series) -> float:
    clean = series.dropna()
    return float(clean.mean()) if not clean.empty else 0.0


def _drawdown(profits: pd.Series) -> tuple[float, float]:
    clean = profits.fillna(0.0).astype(float)
    if clean.empty:
        return 0.0, 0.0
    equity = clean.cumsum()
    running_peak = equity.cummax().clip(lower=0.0)
    drawdown = equity - running_peak
    max_drawdown = abs(float(drawdown.min()))
    denominator = running_peak.where(running_peak > 0)
    drawdown_pct = (drawdown / denominator * 100.0).replace([float("inf"), float("-inf")], pd.NA)
    max_drawdown_pct = abs(float(drawdown_pct.min())) if drawdown_pct.notna().any() else 0.0
    return max_drawdown, max_drawdown_pct


def summarize_trade_history(history: pd.DataFrame | None) -> TradePerformanceSummary:
    closed = closed_trade_rows(history)
    if closed.empty:
        return TradePerformanceSummary()

    if "created_at" in closed.columns:
        closed = closed.assign(
            _created_at=pd.to_datetime(closed["created_at"], errors="coerce")
        ).sort_values(["_created_at"], kind="stable")

    profits = _numeric(closed, "profit").fillna(0.0)
    profit_pct = _numeric(closed, "profit_pct")
    holding = _numeric(closed, "holding_minutes")
    mfe = _numeric(closed, "mfe_pct")
    mae = _numeric(closed, "mae_pct")
    quality = _numeric(closed, "trade_quality_score")

    wins = profits[profits > 0]
    losses = profits[profits < 0]
    breakeven = profits[profits == 0]
    gross_profit = float(wins.sum()) if not wins.empty else 0.0
    gross_loss = abs(float(losses.sum())) if not losses.empty else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (None if gross_profit == 0 else float("inf"))
    average_win = _safe_mean(wins)
    average_loss = abs(_safe_mean(losses))
    payoff_ratio = average_win / average_loss if average_loss > 0 else (None if average_win == 0 else float("inf"))
    max_drawdown, max_drawdown_pct = _drawdown(profits)

    return TradePerformanceSummary(
        closed_trades=int(len(closed)),
        winning_trades=int((profits > 0).sum()),
        losing_trades=int((profits < 0).sum()),
        breakeven_trades=int((profits == 0).sum()),
        win_rate_pct=float((profits > 0).mean() * 100.0),
        net_profit=float(profits.sum()),
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        profit_factor=profit_factor,
        average_profit=_safe_mean(profits),
        average_win=average_win,
        average_loss=average_loss,
        payoff_ratio=payoff_ratio,
        average_profit_pct=_safe_mean(profit_pct),
        average_holding_minutes=_safe_mean(holding),
        maximum_drawdown=max_drawdown,
        maximum_drawdown_pct=max_drawdown_pct,
        best_trade=float(profits.max()),
        worst_trade=float(profits.min()),
        average_mfe_pct=_safe_mean(mfe),
        average_mae_pct=_safe_mean(mae),
        average_quality_score=_safe_mean(quality),
    )


def performance_by(history: pd.DataFrame | None, column: str) -> pd.DataFrame:
    """Piyasa, sembol, çıkış nedeni veya strateji bazında performans tablosu üretir."""
    closed = closed_trade_rows(history)
    if closed.empty or column not in closed.columns:
        return pd.DataFrame()

    working = closed.copy()
    working[column] = working[column].fillna("Bilinmiyor").astype(str)
    working["profit"] = _numeric(working, "profit").fillna(0.0)
    working["profit_pct"] = _numeric(working, "profit_pct")
    working["holding_minutes"] = _numeric(working, "holding_minutes")

    rows: list[dict[str, Any]] = []
    for name, group in working.groupby(column, dropna=False):
        profits = group["profit"]
        losses = profits[profits < 0]
        wins = profits[profits > 0]
        gross_loss = abs(float(losses.sum())) if not losses.empty else 0.0
        gross_profit = float(wins.sum()) if not wins.empty else 0.0
        rows.append(
            {
                column: name,
                "İşlem": int(len(group)),
                "Kazanan": int((profits > 0).sum()),
                "Başarı %": float((profits > 0).mean() * 100.0),
                "Net K/Z": float(profits.sum()),
                "Ortalama K/Z": float(profits.mean()),
                "Ortalama K/Z %": _safe_mean(group["profit_pct"]),
                "Profit Factor": gross_profit / gross_loss if gross_loss > 0 else None,
                "Ortalama Süre (dk)": _safe_mean(group["holding_minutes"]),
            }
        )
    return pd.DataFrame(rows).sort_values(["Net K/Z", "Başarı %"], ascending=[False, False])


def equity_curve(history: pd.DataFrame | None) -> pd.DataFrame:
    closed = closed_trade_rows(history)
    if closed.empty:
        return pd.DataFrame(columns=["Tarih", "Kümülatif K/Z", "Drawdown"])
    working = closed.copy()
    working["Tarih"] = pd.to_datetime(working.get("created_at"), errors="coerce")
    working["K/Z"] = _numeric(working, "profit").fillna(0.0)
    working = working.sort_values("Tarih", kind="stable")
    working["Kümülatif K/Z"] = working["K/Z"].cumsum()
    peak = working["Kümülatif K/Z"].cummax().clip(lower=0.0)
    working["Drawdown"] = working["Kümülatif K/Z"] - peak
    return working[["Tarih", "Kümülatif K/Z", "Drawdown"]].reset_index(drop=True)
