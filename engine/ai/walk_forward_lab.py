from __future__ import annotations

from dataclasses import replace
from itertools import product
from math import isfinite
from typing import Any, Callable

import numpy as np
import pandas as pd


def _num(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if isfinite(result) else default


def _score(train: dict, test: dict) -> float:
    tr = _num(train.get("Toplam Getiri %"))
    te = _num(test.get("Toplam Getiri %"))
    pf = min(_num(test.get("Kâr Faktörü")), 4.0)
    dd = _num(test.get("Maksimum Düşüş %"))
    wr = _num(test.get("Başarı Oranı %"))
    count = int(_num(test.get("Toplam İşlem")))

    value = (
        max(-30.0, min(30.0, te)) * 1.8
        + max(0.0, pf) * 16.0
        + max(0.0, min(wr, 80.0)) * 0.30
        + max(0.0, 25.0 - dd * 1.5)
        + min(count, 40) * 0.35
    )
    if count < 5:
        value -= 30.0
    elif count < 10:
        value -= 15.0
    if pf < 1.0:
        value -= 25.0
    if te < 0:
        value -= abs(te) * 2.0
    value -= min(abs(tr - te), 40.0) * 0.65
    if tr > 0 and te <= 0:
        value -= 20.0
    return round(value, 2)


def _label(train_return: float, test_return: float, pf: float, count: int) -> str:
    if count < 5:
        return "Yetersiz Veri"
    if test_return > 0 and pf >= 1.3:
        return "Güçlü" if abs(train_return - test_return) <= 10 else "Orta"
    if test_return > 0 and pf >= 1.0:
        return "Sınırlı"
    return "Zayıf"


def _build_folds(length: int, train_ratio: float, folds: int) -> list[tuple[int, int, int, int]]:
    if folds < 1:
        raise ValueError("Fold sayısı en az 1 olmalıdır.")
    initial_train = int(length * train_ratio)
    remaining = length - initial_train
    test_size = remaining // folds
    if initial_train < 220 or test_size < 60:
        raise ValueError(
            "Rolling walk-forward için ilk eğitimde en az 220, "
            "her doğrulama fold'unda en az 60 mum gerekir."
        )
    result: list[tuple[int, int, int, int]] = []
    for fold in range(folds):
        train_start = 0
        train_end = initial_train + fold * test_size
        test_start = train_end
        test_end = length if fold == folds - 1 else test_start + test_size
        result.append((train_start, train_end, test_start, test_end))
    return result


def _aggregate_fold_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [row for row in rows if row.get("Durum") == "Tamamlandı"]
    if not completed:
        return {"Durum": "Hata", "Hata": "Hiçbir fold tamamlanamadı."}

    train_returns = [_num(row["Eğitim Getirisi %"]) for row in completed]
    test_returns = [_num(row["Doğrulama Getirisi %"]) for row in completed]
    pfs = [_num(row["Doğrulama Kâr Faktörü"]) for row in completed]
    win_rates = [_num(row["Doğrulama Başarı Oranı %"]) for row in completed]
    drawdowns = [_num(row["Doğrulama Maksimum Düşüş %"]) for row in completed]
    sharpes = [_num(row["Doğrulama Sharpe"]) for row in completed]
    counts = [int(_num(row["Doğrulama İşlem"])) for row in completed]
    scores = [_num(row["Walk-Forward Puanı"]) for row in completed]

    avg_train = float(np.mean(train_returns))
    avg_test = float(np.mean(test_returns))
    avg_pf = float(np.mean(pfs))
    total_count = int(sum(counts))
    positive_fold_rate = sum(value > 0 for value in test_returns) / len(test_returns) * 100
    stability = max(0.0, 100.0 - float(np.std(test_returns, ddof=0)) * 4.0)
    degradation = float(np.mean([abs(a - b) for a, b in zip(train_returns, test_returns)]))

    label = _label(avg_train, avg_test, avg_pf, total_count)
    if positive_fold_rate < 50 or stability < 45:
        label = "Zayıf"
    elif label == "Güçlü" and positive_fold_rate < 75:
        label = "Orta"

    return {
        "Eğitim Getirisi %": round(avg_train, 2),
        "Doğrulama Getirisi %": round(avg_test, 2),
        "Getiri Farkı": round(degradation, 2),
        "Doğrulama Kâr Faktörü": round(avg_pf, 3),
        "Doğrulama Başarı Oranı %": round(float(np.mean(win_rates)), 2),
        "Doğrulama Maksimum Düşüş %": round(float(np.max(drawdowns)), 2),
        "Doğrulama İşlem": total_count,
        "Doğrulama Sharpe": round(float(np.mean(sharpes)), 3),
        "Pozitif Fold %": round(positive_fold_rate, 2),
        "Stabilite Puanı": round(stability, 2),
        "Fold Sayısı": len(completed),
        "Sağlamlık": label,
        "Walk-Forward Puanı": round(float(np.mean(scores)) + stability * 0.15, 2),
        "Durum": "Tamamlandı",
        "Hata": "",
    }


def run_walk_forward_lab(
    *,
    data: pd.DataFrame,
    base_config,
    run_backtest: Callable,
    entry_scores: list[int],
    exit_scores: list[int],
    holding_bars: list[int],
    train_ratio: float = 0.70,
    max_combinations: int = 200,
    folds: int = 1,
) -> pd.DataFrame:
    """Run single-split or expanding-window rolling walk-forward validation."""
    combinations = list(product(entry_scores, exit_scores, holding_bars))
    if len(combinations) > max_combinations:
        raise ValueError(f"En fazla {max_combinations} kombinasyon kullanılabilir.")
    if not 0.50 <= train_ratio <= 0.85:
        raise ValueError("Eğitim oranı %50-%85 arasında olmalıdır.")

    frame = data.copy()
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    fold_ranges = _build_folds(len(frame), train_ratio, folds)
    rows: list[dict[str, Any]] = []

    for test_no, (entry, exit_value, holding) in enumerate(combinations, 1):
        fold_rows: list[dict[str, Any]] = []
        config = replace(
            base_config,
            minimum_entry_score=float(entry),
            exit_score=float(exit_value),
            max_holding_bars=int(holding),
        )

        for fold_no, (train_start, train_end, test_start, test_end) in enumerate(fold_ranges, 1):
            train_data = frame.iloc[train_start:train_end].copy()
            test_data = frame.iloc[test_start:test_end].copy()
            train_result = run_backtest(train_data, config)
            test_result = run_backtest(test_data, config)
            error = train_result.get("error") or test_result.get("error")
            if error:
                fold_rows.append({"Durum": "Hata", "Hata": str(error), "Fold": fold_no})
                continue

            train = train_result.get("metrics", {})
            test = test_result.get("metrics", {})
            tr = _num(train.get("Toplam Getiri %"))
            te = _num(test.get("Toplam Getiri %"))
            pf = _num(test.get("Kâr Faktörü"))
            count = int(_num(test.get("Toplam İşlem")))
            fold_rows.append({
                "Fold": fold_no,
                "Eğitim Getirisi %": tr,
                "Doğrulama Getirisi %": te,
                "Doğrulama Kâr Faktörü": pf,
                "Doğrulama Başarı Oranı %": _num(test.get("Başarı Oranı %")),
                "Doğrulama Maksimum Düşüş %": _num(test.get("Maksimum Düşüş %")),
                "Doğrulama İşlem": count,
                "Doğrulama Sharpe": _num(test.get("Sharpe")),
                "Walk-Forward Puanı": _score(train, test),
                "Durum": "Tamamlandı",
                "Hata": "",
            })

        aggregate = _aggregate_fold_rows(fold_rows)
        rows.append({
            "Test": test_no,
            "Minimum Giriş Puanı": entry,
            "Çıkış Puanı": exit_value,
            "Maksimum Bekleme": holding,
            **aggregate,
        })

    result = pd.DataFrame(rows)
    if result.empty:
        return result
    completed = result[result["Durum"] == "Tamamlandı"].copy()
    failed = result[result["Durum"] != "Tamamlandı"].copy()
    if not completed.empty:
        order = {"Güçlü": 4, "Orta": 3, "Sınırlı": 2, "Zayıf": 1, "Yetersiz Veri": 0}
        completed["_order"] = completed["Sağlamlık"].map(order).fillna(0)
        completed = completed.sort_values(
            ["_order", "Walk-Forward Puanı", "Pozitif Fold %", "Doğrulama Kâr Faktörü", "Doğrulama Getirisi %"],
            ascending=[False, False, False, False, False],
        ).drop(columns=["_order"]).reset_index(drop=True)
        completed.insert(0, "Sıra", range(1, len(completed) + 1))
    return pd.concat([completed, failed], ignore_index=True)


def best_walk_forward_profile(results: pd.DataFrame) -> dict[str, Any] | None:
    if results is None or results.empty:
        return None
    valid = results[(results["Durum"] == "Tamamlandı") & results["Sağlamlık"].isin(["Güçlü", "Orta"])]
    if valid.empty:
        valid = results[results["Durum"] == "Tamamlandı"]
    return None if valid.empty else valid.iloc[0].to_dict()


def add_parameter_robustness(results: pd.DataFrame) -> pd.DataFrame:
    """Score each completed profile by the quality of its neighbouring profiles.

    Robust profiles should not be isolated spikes. The function measures the
    average walk-forward score around each parameter combination and adds an
    overfit-risk label without changing existing ranking columns.
    """
    if results is None or results.empty:
        return results.copy() if isinstance(results, pd.DataFrame) else pd.DataFrame()

    frame = results.copy()
    frame["Komşu Profil"] = 0
    frame["Komşu Ortalama Puan"] = np.nan
    frame["Parametre Sağlamlığı"] = np.nan
    frame["Aşırı Uyum Riski"] = "Bilinmiyor"

    valid_mask = frame["Durum"].eq("Tamamlandı")
    valid = frame.loc[valid_mask].copy()
    if valid.empty:
        return frame

    entry_values = sorted(valid["Minimum Giriş Puanı"].dropna().unique())
    exit_values = sorted(valid["Çıkış Puanı"].dropna().unique())
    holding_values = sorted(valid["Maksimum Bekleme"].dropna().unique())

    def adjacent(value, values):
        idx = values.index(value)
        return set(values[max(0, idx - 1): min(len(values), idx + 2)])

    for idx, row in valid.iterrows():
        mask = (
            valid["Minimum Giriş Puanı"].isin(adjacent(row["Minimum Giriş Puanı"], entry_values))
            & valid["Çıkış Puanı"].isin(adjacent(row["Çıkış Puanı"], exit_values))
            & valid["Maksimum Bekleme"].isin(adjacent(row["Maksimum Bekleme"], holding_values))
        )
        neighbours = valid.loc[mask & (valid.index != idx)]
        count = len(neighbours)
        own_score = _num(row.get("Walk-Forward Puanı"))
        avg_score = float(neighbours["Walk-Forward Puanı"].mean()) if count else own_score
        positive_ratio = (
            float((neighbours["Doğrulama Getirisi %"] > 0).mean() * 100) if count else
            (100.0 if _num(row.get("Doğrulama Getirisi %")) > 0 else 0.0)
        )
        score_gap = max(0.0, own_score - avg_score)
        robustness = max(0.0, min(100.0, 50.0 + avg_score * 0.45 + positive_ratio * 0.25 - score_gap * 0.9))

        if count < 2:
            risk = "Yetersiz Komşu"
        elif score_gap >= 30 or positive_ratio < 40:
            risk = "Yüksek"
        elif score_gap >= 15 or positive_ratio < 65:
            risk = "Orta"
        else:
            risk = "Düşük"

        frame.at[idx, "Komşu Profil"] = count
        frame.at[idx, "Komşu Ortalama Puan"] = round(avg_score, 2)
        frame.at[idx, "Parametre Sağlamlığı"] = round(robustness, 2)
        frame.at[idx, "Aşırı Uyum Riski"] = risk

    return frame


def best_robust_profile(results: pd.DataFrame) -> dict[str, Any] | None:
    enriched = add_parameter_robustness(results)
    if enriched.empty:
        return None
    valid = enriched[enriched["Durum"].eq("Tamamlandı")].copy()
    if valid.empty:
        return None
    risk_order = {"Düşük": 3, "Orta": 2, "Yüksek": 1, "Yetersiz Komşu": 0, "Bilinmiyor": 0}
    valid["_risk"] = valid["Aşırı Uyum Riski"].map(risk_order).fillna(0)
    valid = valid.sort_values(
        ["_risk", "Parametre Sağlamlığı", "Walk-Forward Puanı"],
        ascending=[False, False, False],
    )
    return valid.iloc[0].drop(labels=["_risk"]).to_dict()
