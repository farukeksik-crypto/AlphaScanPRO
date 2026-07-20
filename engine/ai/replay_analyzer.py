from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


NUMERIC_COLUMNS = [
    "profit",
    "technical_score",
    "confidence_score",
    "commission",
    "price",
    "quantity",
]


def _safe_numeric(
    frame: pd.DataFrame,
    columns: list[str],
) -> pd.DataFrame:
    result = frame.copy()

    for column in columns:
        if column in result.columns:
            result[column] = pd.to_numeric(
                result[column],
                errors="coerce",
            )

    return result


def _sell_rows(history: pd.DataFrame) -> pd.DataFrame:
    if history is None or history.empty or "side" not in history.columns:
        return pd.DataFrame()

    frame = history[
        history["side"].astype(str).str.upper() == "SELL"
    ].copy()

    frame = _safe_numeric(frame, NUMERIC_COLUMNS)

    if "created_at" in frame.columns:
        frame["created_at"] = pd.to_datetime(
            frame["created_at"],
            errors="coerce",
        )
        frame = frame.sort_values("created_at")

    frame["profit"] = frame.get(
        "profit",
        pd.Series(0.0, index=frame.index),
    ).fillna(0.0)

    frame["commission"] = frame.get(
        "commission",
        pd.Series(0.0, index=frame.index),
    ).fillna(0.0)

    return frame


def _profit_factor(series: pd.Series) -> float:
    positive = float(series[series > 0].sum())
    negative = float(abs(series[series < 0].sum()))

    if negative == 0:
        return float("inf") if positive > 0 else 0.0

    return positive / negative


def _group_performance(
    frame: pd.DataFrame,
    group_columns: list[str],
) -> pd.DataFrame:
    valid_columns = [
        column for column in group_columns if column in frame.columns
    ]

    if frame.empty or not valid_columns:
        return pd.DataFrame()

    grouped = (
        frame.groupby(valid_columns, dropna=False)
        .agg(
            İşlem=("profit", "size"),
            Kazanan=("profit", lambda values: int((values > 0).sum())),
            Kaybeden=("profit", lambda values: int((values < 0).sum())),
            Toplam_KZ=("profit", "sum"),
            Ortalama_KZ=("profit", "mean"),
            Medyan_KZ=("profit", "median"),
            En_İyi=("profit", "max"),
            En_Kötü=("profit", "min"),
            Komisyon=("commission", "sum"),
        )
        .reset_index()
    )

    grouped["Başarı_Oranı"] = np.where(
        grouped["İşlem"] > 0,
        grouped["Kazanan"] / grouped["İşlem"] * 100,
        0.0,
    )

    factors: list[float] = []

    for _, row in grouped.iterrows():
        mask = pd.Series(True, index=frame.index)

        for column in valid_columns:
            value = row[column]
            mask &= (
                frame[column].isna()
                if pd.isna(value)
                else frame[column] == value
            )

        factors.append(_profit_factor(frame.loc[mask, "profit"]))

    grouped["Kâr_Faktörü"] = factors

    return grouped.sort_values(
        ["Toplam_KZ", "Başarı_Oranı"],
        ascending=[False, False],
    )


def _band_analysis(
    frame: pd.DataFrame,
    source_column: str,
    labels: list[str],
    bins: list[float],
    output_name: str,
) -> pd.DataFrame:
    if frame.empty or source_column not in frame.columns:
        return pd.DataFrame()

    working = frame.dropna(subset=[source_column]).copy()

    if working.empty:
        return pd.DataFrame()

    working[output_name] = pd.cut(
        working[source_column],
        bins=bins,
        labels=labels,
        include_lowest=True,
    )

    return _group_performance(working, [output_name])


def _equity_curve(sales: pd.DataFrame) -> pd.DataFrame:
    if sales.empty:
        return pd.DataFrame()

    curve = sales.copy()
    curve["İşlem"] = np.arange(1, len(curve) + 1)
    curve["Kümülatif K/Z"] = curve["profit"].cumsum()
    curve["Zirve"] = curve["Kümülatif K/Z"].cummax()
    curve["Drawdown"] = curve["Kümülatif K/Z"] - curve["Zirve"]

    columns = ["İşlem", "Kümülatif K/Z", "Zirve", "Drawdown"]

    if "created_at" in curve.columns:
        columns.insert(1, "created_at")

    return curve[columns]


def _period_performance(
    sales: pd.DataFrame,
    period: str,
    output_name: str,
) -> pd.DataFrame:
    if (
        sales.empty
        or "created_at" not in sales.columns
        or sales["created_at"].isna().all()
    ):
        return pd.DataFrame()

    working = sales.dropna(subset=["created_at"]).copy()
    working[output_name] = working["created_at"].dt.to_period(period).astype(str)

    return _group_performance(working, [output_name])


def _calibration_status(
    closed_trades: int,
) -> dict[str, Any]:
    if closed_trades >= 200:
        return {
            "level": "Güçlü",
            "progress": 100,
            "message": "Kalibrasyon için güçlü miktarda işlem verisi oluştu.",
        }

    if closed_trades >= 100:
        return {
            "level": "Orta",
            "progress": 70,
            "message": "Sonuçlar anlamlı hale geliyor; yine de yeni verilerle doğrulanmalı.",
        }

    if closed_trades >= 30:
        return {
            "level": "Başlangıç",
            "progress": 40,
            "message": "İlk örüntüler görülebilir fakat kesin karar için veri az.",
        }

    return {
        "level": "Yetersiz",
        "progress": min(25, closed_trades),
        "message": "Ayar değiştirmek için yeterli kapanmış işlem bulunmuyor.",
    }


def _build_warnings(
    summary: dict[str, Any],
    by_market: pd.DataFrame,
    by_profile: pd.DataFrame,
) -> list[str]:
    warnings: list[str] = []

    if summary["closed_trades"] < 30:
        warnings.append(
            "Kapanmış işlem sayısı 30'un altında; sonuçları kesin kabul etme."
        )

    if summary["profit_factor"] < 1.0:
        warnings.append(
            "Kâr faktörü 1'in altında; mevcut robot ayarları zarar üretiyor."
        )

    if summary["win_rate"] < 45:
        warnings.append(
            "Başarı oranı düşük; giriş filtreleri ve çıkış kuralları test edilmeli."
        )

    if summary["max_drawdown"] < -abs(summary["total_profit"]):
        warnings.append(
            "Drawdown toplam kazanca göre yüksek; pozisyon büyüklüğü azaltılmalı."
        )

    for table, column in (
        (by_market, "market"),
        (by_profile, "strategy_profile"),
    ):
        if table.empty or "Toplam_KZ" not in table.columns:
            continue

        for _, row in table[table["Toplam_KZ"] < 0].iterrows():
            value = row.get(column, "Bilinmeyen")
            warnings.append(f"{value} grubu toplamda zarar üretiyor.")

    return warnings


def _build_recommendations(
    summary: dict[str, Any],
    confidence_bands: pd.DataFrame,
    score_bands: pd.DataFrame,
    by_universe: pd.DataFrame,
) -> list[str]:
    recommendations: list[str] = []

    if summary["closed_trades"] < 30:
        recommendations.append(
            "En az 30 kapanmış işlem oluşana kadar mevcut ayarları sabit tut."
        )

    for table, label_column, prefix in (
        (confidence_bands, "Güven Aralığı", "güven"),
        (score_bands, "Teknik Puan Aralığı", "teknik puan"),
    ):
        if table.empty or "Toplam_KZ" not in table.columns:
            continue

        profitable = table[
            (table["Toplam_KZ"] > 0)
            & (table["İşlem"] >= 5)
        ]

        if not profitable.empty:
            best = profitable.iloc[0]
            recommendations.append(
                f"En iyi {prefix} aralığı şu anda "
                f"{best[label_column]}; ayrı backtest ile doğrula."
            )

    if not by_universe.empty and "Toplam_KZ" in by_universe.columns:
        profitable = by_universe[
            (by_universe["Toplam_KZ"] > 0)
            & (by_universe["İşlem"] >= 5)
        ]

        if not profitable.empty:
            best = profitable.iloc[0]
            recommendations.append(
                f"{best.get('universe', 'Bilinmeyen')} evreni en iyi sonucu "
                "üretiyor; aynı evreni farklı dönemlerde backtest et."
            )

    if summary["profit_factor"] < 1.5:
        recommendations.append(
            "Minimum güven eşiğini 65, 70 ve 75 için ayrı ayrı karşılaştır."
        )

    return recommendations


def analyze_robot_history(
    history: pd.DataFrame,
) -> dict[str, Any]:
    sales = _sell_rows(history)

    empty_summary = {
        "closed_trades": 0,
        "winners": 0,
        "losers": 0,
        "win_rate": 0.0,
        "total_profit": 0.0,
        "average_profit": 0.0,
        "profit_factor": 0.0,
        "total_commission": 0.0,
        "max_drawdown": 0.0,
        "best_trade": 0.0,
        "worst_trade": 0.0,
    }

    if sales.empty:
        return {
            "summary": empty_summary,
            "calibration": _calibration_status(0),
            "warnings": ["Henüz kapanmış robot işlemi bulunmuyor."],
            "recommendations": [
                "Replay analizi için robotun sanal işlemler kapatmasını bekle."
            ],
            "by_market": pd.DataFrame(),
            "by_universe": pd.DataFrame(),
            "by_profile": pd.DataFrame(),
            "by_symbol": pd.DataFrame(),
            "by_exit_reason": pd.DataFrame(),
            "confidence_bands": pd.DataFrame(),
            "score_bands": pd.DataFrame(),
            "monthly": pd.DataFrame(),
            "weekly": pd.DataFrame(),
            "equity_curve": pd.DataFrame(),
            "sales": sales,
        }

    winners = int((sales["profit"] > 0).sum())
    losers = int((sales["profit"] < 0).sum())
    closed_trades = int(len(sales))
    equity_curve = _equity_curve(sales)

    summary = {
        "closed_trades": closed_trades,
        "winners": winners,
        "losers": losers,
        "win_rate": winners / closed_trades * 100,
        "total_profit": float(sales["profit"].sum()),
        "average_profit": float(sales["profit"].mean()),
        "profit_factor": _profit_factor(sales["profit"]),
        "total_commission": float(sales["commission"].sum()),
        "max_drawdown": float(equity_curve["Drawdown"].min()),
        "best_trade": float(sales["profit"].max()),
        "worst_trade": float(sales["profit"].min()),
    }

    by_market = _group_performance(sales, ["market"])
    by_universe = _group_performance(sales, ["market", "universe"])
    by_profile = _group_performance(sales, ["strategy_profile"])
    by_symbol = _group_performance(sales, ["symbol"])
    by_exit_reason = _group_performance(sales, ["reason"])

    confidence_bands = _band_analysis(
        sales,
        "confidence_score",
        ["<50", "50-64", "65-74", "75-84", "85+"],
        [-np.inf, 49.999, 64.999, 74.999, 84.999, np.inf],
        "Güven Aralığı",
    )

    score_bands = _band_analysis(
        sales,
        "technical_score",
        ["<70", "70-79", "80-89", "90+"],
        [-np.inf, 69.999, 79.999, 89.999, np.inf],
        "Teknik Puan Aralığı",
    )

    return {
        "summary": summary,
        "calibration": _calibration_status(closed_trades),
        "warnings": _build_warnings(summary, by_market, by_profile),
        "recommendations": _build_recommendations(
            summary,
            confidence_bands,
            score_bands,
            by_universe,
        ),
        "by_market": by_market,
        "by_universe": by_universe,
        "by_profile": by_profile,
        "by_symbol": by_symbol,
        "by_exit_reason": by_exit_reason,
        "confidence_bands": confidence_bands,
        "score_bands": score_bands,
        "monthly": _period_performance(sales, "M", "Ay"),
        "weekly": _period_performance(sales, "W", "Hafta"),
        "equity_curve": equity_curve,
        "sales": sales,
    }
