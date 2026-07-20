from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class AnalyzerThresholds:
    minimum_trades: int = 20
    good_profit_factor: float = 1.50
    good_win_rate: float = 55.0
    max_acceptable_drawdown: float = 15.0
    max_commission_share: float = 20.0
    max_top3_profit_share: float = 70.0


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
        if np.isnan(numeric) or np.isinf(numeric):
            return default
        return numeric
    except (TypeError, ValueError):
        return default


def _standardize_exit_reason(value: Any) -> str:
    text = str(value or "").strip().upper()

    if "SİNYAL ZAYIFLADI" in text or "SINYAL ZAYIFLADI" in text:
        return "SİNYAL ZAYIFLADI"
    if "HEDEF 2" in text:
        return "HEDEF 2"
    if "HEDEF 1" in text:
        return "HEDEF 1"
    if "HEDEF" in text:
        return "HEDEF"
    if "STOP" in text:
        return "STOP"
    if "MAKSİMUM BEKLEME" in text or "MAKSIMUM BEKLEME" in text:
        return "MAKSİMUM BEKLEME"
    if "GÜN SONU" in text or "GUN SONU" in text:
        return "GÜN SONU"
    if "TEST SONU" in text:
        return "TEST SONU"
    if "MANUEL" in text:
        return "MANUEL SATIŞ"
    if not text:
        return "BİLİNMİYOR"

    return text


def _normalize_trades(trades: pd.DataFrame) -> pd.DataFrame:
    """
    AL ve SAT kayıtlarını eşleştirir.

    SAT satırına:
    - Giriş Skoru
    - Çıkış Skoru
    - Standart Çıkış Nedeni
    alanlarını ekler.
    """
    if trades is None or trades.empty:
        return pd.DataFrame()

    required = {"İşlem"}
    if not required.issubset(trades.columns):
        return pd.DataFrame()

    frame = trades.copy().reset_index(drop=True)

    if "Tarih" in frame.columns:
        frame["Tarih"] = pd.to_datetime(
            frame["Tarih"],
            errors="coerce",
        )

    numeric_columns = [
        "Skor",
        "Net K/Z",
        "K/Z %",
        "Komisyon",
        "Fiyat",
        "Miktar",
        "Tutulan Mum",
    ]

    for column in numeric_columns:
        if column in frame.columns:
            frame[column] = pd.to_numeric(
                frame[column],
                errors="coerce",
            )

    open_entry: dict[str, Any] | None = None
    normalized_sales: list[dict[str, Any]] = []

    for _, row in frame.iterrows():
        side = str(row.get("İşlem", "")).strip().upper()

        if side == "AL":
            open_entry = row.to_dict()
            continue

        if side != "SAT":
            continue

        sale = row.to_dict()

        entry_score = (
            _safe_float(open_entry.get("Skor"))
            if open_entry is not None
            else np.nan
        )
        exit_score = _safe_float(row.get("Skor"), np.nan)

        sale["Giriş Skoru"] = entry_score
        sale["Çıkış Skoru"] = exit_score
        sale["Standart Çıkış Nedeni"] = _standardize_exit_reason(
            row.get("Neden")
        )

        if open_entry is not None:
            sale["Giriş Tarihi"] = open_entry.get("Tarih")
            sale["Giriş Fiyatı"] = open_entry.get("Fiyat")
            sale["Giriş Kararı"] = open_entry.get("Karar", "")
            sale["Giriş Nedeni"] = open_entry.get("Neden", "")

        normalized_sales.append(sale)
        open_entry = None

    if not normalized_sales:
        return pd.DataFrame()

    return pd.DataFrame(normalized_sales)


def _profit_concentration(sales: pd.DataFrame) -> dict[str, float]:
    if sales.empty or "Net K/Z" not in sales.columns:
        return {
            "top_1_share_pct": 0.0,
            "top_3_share_pct": 0.0,
        }

    positive = sales.loc[
        sales["Net K/Z"] > 0,
        "Net K/Z",
    ].sort_values(ascending=False)

    total_profit = float(positive.sum())

    if total_profit <= 0:
        return {
            "top_1_share_pct": 0.0,
            "top_3_share_pct": 0.0,
        }

    return {
        "top_1_share_pct": float(
            positive.head(1).sum() / total_profit * 100
        ),
        "top_3_share_pct": float(
            positive.head(3).sum() / total_profit * 100
        ),
    }


def _group_analysis(
    sales: pd.DataFrame,
    group_column: str,
) -> pd.DataFrame:
    if sales.empty or group_column not in sales.columns:
        return pd.DataFrame()

    grouped = (
        sales.groupby(
            group_column,
            dropna=False,
        )
        .agg(
            İşlem=("Net K/Z", "size"),
            Kazanan=("Net K/Z", lambda s: int((s > 0).sum())),
            Kaybeden=("Net K/Z", lambda s: int((s < 0).sum())),
            Toplam_KZ=("Net K/Z", "sum"),
            Ortalama_KZ=("Net K/Z", "mean"),
            Medyan_KZ=("Net K/Z", "median"),
        )
        .reset_index()
    )

    grouped["Başarı_Oranı"] = np.where(
        grouped["İşlem"] > 0,
        grouped["Kazanan"] / grouped["İşlem"] * 100,
        0.0,
    )

    return grouped.sort_values(
        ["Toplam_KZ", "Başarı_Oranı"],
        ascending=[False, False],
    )


def _entry_score_analysis(sales: pd.DataFrame) -> pd.DataFrame:
    if sales.empty or "Giriş Skoru" not in sales.columns:
        return pd.DataFrame()

    working = sales.dropna(subset=["Giriş Skoru"]).copy()

    if working.empty:
        return pd.DataFrame()

    working["Giriş Skoru Aralığı"] = pd.cut(
        working["Giriş Skoru"],
        bins=[-np.inf, 69.999, 79.999, 89.999, np.inf],
        labels=["<70", "70-79", "80-89", "90+"],
    )

    return _group_analysis(
        working,
        "Giriş Skoru Aralığı",
    )


def _exit_score_analysis(sales: pd.DataFrame) -> pd.DataFrame:
    if sales.empty or "Çıkış Skoru" not in sales.columns:
        return pd.DataFrame()

    working = sales.dropna(subset=["Çıkış Skoru"]).copy()

    if working.empty:
        return pd.DataFrame()

    working["Çıkış Skoru Aralığı"] = pd.cut(
        working["Çıkış Skoru"],
        bins=[-np.inf, 29.999, 39.999, 49.999, np.inf],
        labels=["<30", "30-39", "40-49", "50+"],
    )

    return _group_analysis(
        working,
        "Çıkış Skoru Aralığı",
    )


def _exit_reason_analysis(sales: pd.DataFrame) -> pd.DataFrame:
    return _group_analysis(
        sales,
        "Standart Çıkış Nedeni",
    )


def analyze_backtest(
    result: dict[str, Any],
    thresholds: AnalyzerThresholds | None = None,
) -> dict[str, Any]:
    thresholds = thresholds or AnalyzerThresholds()

    metrics = result.get("metrics", {}) if result else {}
    trades = result.get("trades", pd.DataFrame()) if result else pd.DataFrame()
    sales = _normalize_trades(trades)

    total_trades = int(
        _safe_float(
            metrics.get("Toplam İşlem", len(sales))
        )
    )
    win_rate = _safe_float(
        metrics.get("Başarı Oranı %")
    )
    profit_factor = _safe_float(
        metrics.get("Kâr Faktörü")
    )
    max_drawdown = _safe_float(
        metrics.get("Maksimum Düşüş %")
    )
    total_return = _safe_float(
        metrics.get("Toplam Getiri %")
    )
    buy_hold = _safe_float(
        metrics.get("Al-Tut Getirisi %")
    )
    commission = _safe_float(
        metrics.get("Toplam Komisyon")
    )
    final_balance = _safe_float(
        metrics.get("Son Bakiye")
    )
    initial_balance = _safe_float(
        metrics.get("Başlangıç Bakiye")
    )

    net_profit = final_balance - initial_balance

    gross_profit = (
        float(
            sales.loc[
                sales["Net K/Z"] > 0,
                "Net K/Z",
            ].sum()
        )
        if not sales.empty and "Net K/Z" in sales.columns
        else 0.0
    )

    commission_share = (
        commission / gross_profit * 100
        if gross_profit > 0
        else 0.0
    )

    concentration = _profit_concentration(sales)

    score = 0.0
    warnings: list[str] = []
    strengths: list[str] = []
    recommendations: list[str] = []

    if total_trades >= 50:
        score += 20
        strengths.append(
            "İşlem sayısı güçlü; örneklem anlamlı."
        )
    elif total_trades >= thresholds.minimum_trades:
        score += 14
        strengths.append(
            "İşlem sayısı temel değerlendirme için yeterli."
        )
    elif total_trades >= 10:
        score += 7
        warnings.append(
            "İşlem sayısı düşük; sonuçlar sınırlı güvenilirlikte."
        )
    else:
        warnings.append(
            "İşlem sayısı çok düşük; sonuçlara güvenilmemeli."
        )

    if total_return > buy_hold and total_return > 0:
        score += 10
        strengths.append(
            "Strateji al-tut getirisini geçmiş."
        )
    elif total_return > 0:
        score += 5
        warnings.append(
            "Strateji pozitif olsa da al-tut getirisinin gerisinde."
        )

    if profit_factor >= 2.0:
        score += 15
        strengths.append("Kâr faktörü çok güçlü.")
    elif profit_factor >= thresholds.good_profit_factor:
        score += 11
        strengths.append(
            "Kâr faktörü kabul edilebilir seviyede."
        )
    elif profit_factor >= 1.0:
        score += 5
        warnings.append(
            "Kâr faktörü zayıf; küçük bozulmalar sistemi zarara çevirebilir."
        )
    else:
        warnings.append(
            "Kâr faktörü 1'in altında; strateji zarar üretiyor."
        )

    if max_drawdown <= 5:
        score += 20
        strengths.append("Maksimum düşüş düşük.")
    elif max_drawdown <= 10:
        score += 15
    elif max_drawdown <= thresholds.max_acceptable_drawdown:
        score += 9
        warnings.append(
            "Maksimum düşüş orta seviyede."
        )
    else:
        warnings.append(
            "Maksimum düşüş yüksek; pozisyon büyüklüğü azaltılmalı."
        )

    if win_rate >= 65:
        score += 10
        strengths.append("Başarı oranı güçlü.")
    elif win_rate >= thresholds.good_win_rate:
        score += 7
    elif win_rate >= 45:
        score += 4
    else:
        warnings.append(
            "Başarı oranı düşük; giriş filtresi güçlendirilmeli."
        )

    if concentration["top_3_share_pct"] <= 50:
        score += 10
        strengths.append(
            "Kâr birkaç işleme aşırı bağlı değil."
        )
    elif concentration["top_3_share_pct"] <= thresholds.max_top3_profit_share:
        score += 5
        warnings.append(
            "Toplam kârın önemli bölümü az sayıda işlemden geliyor."
        )
    else:
        warnings.append(
            "Toplam kâr birkaç büyük işleme aşırı bağımlı."
        )

    if commission_share <= 5:
        score += 15
    elif commission_share <= 10:
        score += 11
    elif commission_share <= thresholds.max_commission_share:
        score += 6
        warnings.append("Komisyon etkisi belirgin.")
    else:
        warnings.append(
            "Komisyon brüt kârın büyük bölümünü tüketiyor."
        )

    score = round(
        min(max(score, 0), 100),
        1,
    )

    if total_trades < thresholds.minimum_trades:
        recommendations.append(
            "Daha uzun tarih aralığında veya daha geniş hisse evreninde tekrar test et."
        )

    if profit_factor < thresholds.good_profit_factor:
        recommendations.append(
            "Minimum giriş puanını 5 puan artırarak ayrı bir karşılaştırmalı backtest çalıştır."
        )

    if win_rate < thresholds.good_win_rate:
        recommendations.append(
            "ADX filtresini 18-25 aralığında test ederek zayıf trend işlemlerini ele."
        )

    if max_drawdown > thresholds.max_acceptable_drawdown:
        recommendations.append(
            "Pozisyon büyüklüğünü azalt veya işlem başına risk limitini düşür."
        )

    if commission_share > thresholds.max_commission_share:
        recommendations.append(
            "Daha az işlem üreten, daha yüksek puanlı giriş filtresini test et."
        )

    if concentration["top_3_share_pct"] > thresholds.max_top3_profit_share:
        recommendations.append(
            "En iyi üç işlemi çıkararak sonucu tekrar hesapla; stratejinin dayanıklılığını kontrol et."
        )

    exit_analysis = _exit_reason_analysis(sales)

    if not exit_analysis.empty:
        negative_exits = exit_analysis[
            exit_analysis["Ortalama_KZ"] < 0
        ]

        for _, row in negative_exits.iterrows():
            recommendations.append(
                f"{row['Standart Çıkış Nedeni']} çıkışları ortalamada zarar üretiyor; bu kuralı ayrı test et."
            )

    return {
        "health_score": score,
        "warnings": warnings,
        "strengths": strengths,
        "recommendations": recommendations,
        "summary": {
            "net_profit": net_profit,
            "commission_share_pct": commission_share,
            "top_1_profit_share_pct": concentration["top_1_share_pct"],
            "top_3_profit_share_pct": concentration["top_3_share_pct"],
        },
        "normalized_sales": sales,
        "exit_reason_analysis": exit_analysis,
        "entry_score_analysis": _entry_score_analysis(sales),
        "exit_score_analysis": _exit_score_analysis(sales),
        # Eski arayüzün kırılmaması için:
        "score_band_analysis": _entry_score_analysis(sales),
    }