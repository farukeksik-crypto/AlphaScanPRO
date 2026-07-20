from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


MIN_SAMPLE_SIZE = 10
RELIABLE_SAMPLE_SIZE = 25


def _to_dataframe(history: Any) -> pd.DataFrame:
    """Robot geçmişini güvenli biçimde DataFrame'e dönüştürür."""
    if history is None:
        return pd.DataFrame()

    if isinstance(history, pd.DataFrame):
        return history.copy()

    try:
        return pd.DataFrame(history)
    except Exception:
        return pd.DataFrame()


def _find_column(
    frame: pd.DataFrame,
    candidates: list[str],
) -> str | None:
    """Farklı isimlerle gelebilen sütunlardan ilk eşleşeni bulur."""
    lowered = {
        str(column).strip().lower(): column
        for column in frame.columns
    }

    for candidate in candidates:
        found = lowered.get(candidate.strip().lower())
        if found is not None:
            return found

    return None


def _numeric_series(
    frame: pd.DataFrame,
    candidates: list[str],
    default: float = 0.0,
) -> pd.Series:
    column = _find_column(frame, candidates)

    if column is None:
        return pd.Series(default, index=frame.index, dtype="float64")

    return pd.to_numeric(frame[column], errors="coerce").fillna(default)


def _text_series(
    frame: pd.DataFrame,
    candidates: list[str],
    default: str = "Bilinmiyor",
) -> pd.Series:
    column = _find_column(frame, candidates)

    if column is None:
        return pd.Series(default, index=frame.index, dtype="object")

    result = frame[column].astype("string").fillna(default).str.strip()
    return result.replace("", default).astype(str)


def _closed_trades(history: Any) -> pd.DataFrame:
    """
    Yalnızca kapanmış işlemleri hazırlar.

    BUY / AL kayıtları kesinlikle öğrenme verisine alınmaz.
    Kabul edilen kapanış ifadeleri:
    SELL, SAT, CLOSE, CLOSED, EXIT.
    """
    frame = _to_dataframe(history)

    if frame.empty:
        return pd.DataFrame()

    frame.columns = [str(column).strip() for column in frame.columns]

    side_column = _find_column(
        frame,
        [
            "side",
            "işlem",
            "islem",
            "type",
            "trade_type",
            "action",
        ],
    )

    if side_column is None:
        return pd.DataFrame()

    side_text = (
        frame[side_column]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    closed_mask = side_text.isin(
        ["SELL", "SAT", "CLOSE", "CLOSED", "EXIT"]
    )

    sales = frame.loc[closed_mask].copy()

    if sales.empty:
        return pd.DataFrame()

    sales["side"] = "SELL"
    sales["symbol"] = _text_series(
        sales,
        ["symbol", "kod", "hisse", "ticker", "asset"],
    )
    sales["market"] = _text_series(
        sales,
        ["market", "piyasa"],
    )
    sales["universe"] = _text_series(
        sales,
        ["universe", "evren"],
    )
    sales["strategy_profile"] = _text_series(
        sales,
        [
            "strategy_profile",
            "strateji_profili",
            "strateji profili",
            "profile",
        ],
    )
    sales["reason"] = _text_series(
        sales,
        [
            "reason",
            "exit_reason",
            "çıkış nedeni",
            "cikis_nedeni",
            "neden",
        ],
    )
    sales["decision"] = _text_series(
        sales,
        ["decision", "karar"],
        default="",
    )
    sales["confidence_status"] = _text_series(
        sales,
        [
            "confidence_status",
            "güven durumu",
            "guven_durumu",
        ],
        default="",
    )

    sales["profit"] = _numeric_series(
        sales,
        [
            "profit",
            "pnl",
            "net_profit",
            "realized_pnl",
            "net k/z",
            "kâr/zarar",
            "kar_zarar",
            "kâr",
            "kar",
        ],
    )
    sales["commission"] = _numeric_series(
        sales,
        ["commission", "komisyon"],
    )
    sales["price"] = _numeric_series(
        sales,
        ["price", "fiyat"],
    )
    sales["quantity"] = _numeric_series(
        sales,
        ["quantity", "miktar", "adet"],
    )
    sales["technical_score"] = _numeric_series(
        sales,
        [
            "technical_score",
            "teknik_score",
            "teknik puan",
            "puan",
            "score",
            "skor",
        ],
        default=np.nan,
    )
    sales["confidence_score"] = _numeric_series(
        sales,
        [
            "confidence_score",
            "confidence",
            "güven",
            "guven",
            "güven puanı",
            "guven_puani",
        ],
        default=np.nan,
    )

    date_column = _find_column(
        sales,
        [
            "created_at",
            "closed_at",
            "exit_time",
            "date",
            "datetime",
            "tarih",
        ],
    )

    if date_column is not None:
        sales["created_at"] = pd.to_datetime(
            sales[date_column],
            errors="coerce",
        )
    else:
        sales["created_at"] = pd.NaT

    sales["weekday"] = sales["created_at"].dt.day_name()
    sales["hour"] = sales["created_at"].dt.hour
    sales["month"] = (
        sales["created_at"]
        .dt.to_period("M")
        .astype(str)
        .replace("NaT", "Bilinmiyor")
    )

    sales["weekday"] = sales["weekday"].fillna("Bilinmiyor")
    sales["hour"] = sales["hour"].fillna(-1).astype(int)

    id_column = _find_column(sales, ["id", "trade_id", "işlem id", "islem_id"])
    if id_column is not None:
        sales["id"] = sales[id_column]
    else:
        sales["id"] = range(1, len(sales) + 1)

    return sales.reset_index(drop=True)


def _profit_factor(series: pd.Series) -> float:
    values = pd.to_numeric(series, errors="coerce").fillna(0.0)

    positive = float(values[values > 0].sum())
    negative = float(abs(values[values < 0].sum()))

    if negative == 0:
        return float("inf") if positive > 0 else 0.0

    return positive / negative


def _performance_table(
    frame: pd.DataFrame,
    group_column: str,
) -> pd.DataFrame:
    if frame.empty or group_column not in frame.columns:
        return pd.DataFrame()

    working = frame.copy()
    working[group_column] = working[group_column].fillna("Bilinmiyor")

    grouped = (
        working.groupby(group_column, dropna=False)
        .agg(
            İşlem_Sayısı=("profit", "size"),
            Toplam_KZ=("profit", "sum"),
            Ortalama_KZ=("profit", "mean"),
            Medyan_KZ=("profit", "median"),
            Kazanan=("profit", lambda values: int((values > 0).sum())),
            Kaybeden=("profit", lambda values: int((values < 0).sum())),
            Komisyon=("commission", "sum"),
        )
        .reset_index()
    )

    grouped["Başarı_Oranı"] = np.where(
        grouped["İşlem_Sayısı"] > 0,
        grouped["Kazanan"] / grouped["İşlem_Sayısı"] * 100.0,
        0.0,
    )

    profit_factors: list[float] = []

    for _, row in grouped.iterrows():
        value = row[group_column]
        mask = working[group_column] == value
        profit_factors.append(
            _profit_factor(working.loc[mask, "profit"])
        )

    grouped["Kâr_Faktörü"] = profit_factors

    return grouped.sort_values(
        ["Toplam_KZ", "Başarı_Oranı"],
        ascending=[False, False],
    ).reset_index(drop=True)


def _band_table(
    frame: pd.DataFrame,
    source_column: str,
    output_column: str,
    bins: list[float],
    labels: list[str],
) -> pd.DataFrame:
    if frame.empty or source_column not in frame.columns:
        return pd.DataFrame()

    working = frame.dropna(subset=[source_column]).copy()

    if working.empty:
        return pd.DataFrame()

    working[output_column] = pd.cut(
        working[source_column],
        bins=bins,
        labels=labels,
        include_lowest=True,
    )

    return _performance_table(working, output_column)


def _best_reliable_row(
    frame: pd.DataFrame,
) -> dict[str, Any] | None:
    if frame is None or frame.empty:
        return None

    count_column = (
        "İşlem_Sayısı"
        if "İşlem_Sayısı" in frame.columns
        else "İşlem"
    )

    reliable = frame[
        frame[count_column] >= MIN_SAMPLE_SIZE
    ]

    if reliable.empty:
        return None

    reliable = reliable.sort_values(
        ["Toplam_KZ", "Başarı_Oranı"],
        ascending=[False, False],
    )

    return reliable.iloc[0].to_dict()


def _worst_reliable_row(
    frame: pd.DataFrame,
) -> dict[str, Any] | None:
    if frame is None or frame.empty:
        return None

    count_column = (
        "İşlem_Sayısı"
        if "İşlem_Sayısı" in frame.columns
        else "İşlem"
    )

    reliable = frame[
        frame[count_column] >= MIN_SAMPLE_SIZE
    ]

    if reliable.empty:
        return None

    reliable = reliable.sort_values(
        ["Toplam_KZ", "Başarı_Oranı"],
        ascending=[True, True],
    )

    return reliable.iloc[0].to_dict()


def _row_count(row: dict[str, Any]) -> int:
    return int(row.get("İşlem_Sayısı", row.get("İşlem", 0)))


def _sample_confidence_label(count: int) -> str:
    if count >= RELIABLE_SAMPLE_SIZE:
        return "yüksek"
    if count >= MIN_SAMPLE_SIZE:
        return "orta"
    return "düşük"


def _build_insights(
    sales: pd.DataFrame,
    tables: dict[str, pd.DataFrame],
) -> list[str]:
    total_count = len(sales)
    total_profit = float(sales["profit"].sum())
    winners = int((sales["profit"] > 0).sum())
    win_rate = winners / total_count * 100.0 if total_count else 0.0

    insights = [
        (
            f"Toplam {total_count} kapanmış işlemde net sonuç "
            f"{total_profit:+,.2f}; başarı oranı %{win_rate:.1f}."
        )
    ]

    if total_count < MIN_SAMPLE_SIZE:
        insights.append(
            "Kapanmış işlem sayısı düşük; sistem henüz güvenilir bir öğrenme yapamaz."
        )
        return insights

    definitions = [
        ("confidence_bands", "Güven Aralığı", "güven aralığı"),
        ("score_bands", "Teknik Puan Aralığı", "teknik puan aralığı"),
        ("by_market", "market", "piyasa"),
        ("by_universe", "universe", "evren"),
        ("by_profile", "strategy_profile", "strateji profili"),
        ("by_symbol", "symbol", "varlık"),
        ("by_exit_reason", "reason", "çıkış nedeni"),
    ]

    for table_name, label_column, readable_name in definitions:
        table = tables.get(table_name, pd.DataFrame())
        best = _best_reliable_row(table)

        if best is None:
            continue

        count = _row_count(best)
        sample_label = _sample_confidence_label(count)

        insights.append(
            f"En iyi {readable_name}: {best[label_column]} | "
            f"{count} işlem | başarı %{float(best['Başarı_Oranı']):.1f} | "
            f"toplam K/Z {float(best['Toplam_KZ']):+,.2f} | "
            f"örneklem güveni {sample_label}."
        )

    return insights


def _build_recommendations(
    sales: pd.DataFrame,
    tables: dict[str, pd.DataFrame],
) -> list[str]:
    recommendations: list[str] = []

    if len(sales) < MIN_SAMPLE_SIZE:
        return [
            "En az 10 kapanmış işlem olmadan robot ayarlarını değiştirme."
        ]

    best_confidence = _best_reliable_row(
        tables.get("confidence_bands", pd.DataFrame())
    )
    if best_confidence:
        recommendations.append(
            f"Minimum güven puanı için "
            f"{best_confidence['Güven Aralığı']} aralığını "
            "Backtest PRO'da ayrı test et."
        )

    best_score = _best_reliable_row(
        tables.get("score_bands", pd.DataFrame())
    )
    if best_score:
        recommendations.append(
            f"Minimum teknik puan için "
            f"{best_score['Teknik Puan Aralığı']} aralığını "
            "Strategy Lab'de doğrula."
        )

    best_profile = _best_reliable_row(
        tables.get("by_profile", pd.DataFrame())
    )
    if best_profile:
        recommendations.append(
            f"{best_profile['strategy_profile']} profili şu an "
            "en iyi sonucu üretiyor; ayrı tarih döneminde tekrar test et."
        )

    worst_market = _worst_reliable_row(
        tables.get("by_market", pd.DataFrame())
    )
    if worst_market and float(worst_market["Toplam_KZ"]) < 0:
        recommendations.append(
            f"{worst_market['market']} piyasasında yeni işlem açmadan "
            "önce daha yüksek güven filtresi kullanmayı test et."
        )

    worst_exit = _worst_reliable_row(
        tables.get("by_exit_reason", pd.DataFrame())
    )
    if worst_exit and float(worst_exit["Toplam_KZ"]) < 0:
        recommendations.append(
            f"{worst_exit['reason']} çıkış kuralı toplamda zarar "
            "üretiyor; stop ve çıkış puanını karşılaştırmalı test et."
        )

    recommendations.append(
        "Hiçbir öneriyi otomatik uygulama; önce Backtest PRO ve "
        "Strategy Lab ile doğrula."
    )

    return recommendations


def _build_learning_score(
    total_trades: int,
    tables: dict[str, pd.DataFrame],
) -> float:
    score = min(total_trades / RELIABLE_SAMPLE_SIZE, 1.0) * 50.0
    reliable_groups = 0

    for table in tables.values():
        if table is None or table.empty:
            continue

        count_column = (
            "İşlem_Sayısı"
            if "İşlem_Sayısı" in table.columns
            else "İşlem"
            if "İşlem" in table.columns
            else None
        )

        if count_column is None:
            continue

        if bool((table[count_column] >= MIN_SAMPLE_SIZE).any()):
            reliable_groups += 1

    score += min(reliable_groups / 5.0, 1.0) * 50.0
    return round(min(score, 100.0), 1)


def analyze_learning(history: Any) -> dict[str, Any]:
    """AI Öğrenme ekranının kullandığı ana analiz fonksiyonu."""
    sales = _closed_trades(history)

    if sales.empty:
        return {
            "learning_score": 0.0,
            "sample_status": "Veri yok",
            "closed_trades": 0,
            "insights": [
                "Henüz kapanmış robot işlemi bulunmuyor."
            ],
            "recommendations": [
                "AI Learning Engine için robotun kapanmış işlem "
                "verisi biriktirmesi gerekir."
            ],
            "tables": {},
            "sales": sales,
        }

    confidence_bands = _band_table(
        sales,
        "confidence_score",
        "Güven Aralığı",
        [-np.inf, 49.999, 64.999, 74.999, 84.999, np.inf],
        ["<50", "50-64", "65-74", "75-84", "85+"],
    )

    score_bands = _band_table(
        sales,
        "technical_score",
        "Teknik Puan Aralığı",
        [-np.inf, 69.999, 79.999, 89.999, np.inf],
        ["<70", "70-79", "80-89", "90+"],
    )

    tables = {
        "confidence_bands": confidence_bands,
        "score_bands": score_bands,
        "by_market": _performance_table(sales, "market"),
        "by_universe": _performance_table(sales, "universe"),
        "by_profile": _performance_table(sales, "strategy_profile"),
        "by_symbol": _performance_table(sales, "symbol"),
        "by_exit_reason": _performance_table(sales, "reason"),
        "by_weekday": _performance_table(sales, "weekday"),
        "by_hour": _performance_table(sales, "hour"),
        "by_month": _performance_table(sales, "month"),
    }

    total_trades = len(sales)

    if total_trades >= RELIABLE_SAMPLE_SIZE:
        sample_status = "Yeterli"
    elif total_trades >= MIN_SAMPLE_SIZE:
        sample_status = "Sınırlı"
    else:
        sample_status = "Çok yetersiz"

    return {
        "learning_score": _build_learning_score(
            total_trades,
            tables,
        ),
        "sample_status": sample_status,
        "closed_trades": total_trades,
        "insights": _build_insights(sales, tables),
        "recommendations": _build_recommendations(sales, tables),
        "tables": tables,
        "sales": sales,
    }