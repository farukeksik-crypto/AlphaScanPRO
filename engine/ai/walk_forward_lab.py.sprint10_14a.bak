from __future__ import annotations

from dataclasses import replace
from itertools import product
from math import isfinite
from typing import Any, Callable

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
) -> pd.DataFrame:
    combinations = list(product(entry_scores, exit_scores, holding_bars))

    if len(combinations) > max_combinations:
        raise ValueError(f"En fazla {max_combinations} kombinasyon kullanılabilir.")
    if not 0.50 <= train_ratio <= 0.85:
        raise ValueError("Eğitim oranı %50-%85 arasında olmalıdır.")

    frame = data.copy()
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    split = int(len(frame) * train_ratio)
    train_data = frame.iloc[:split].copy()
    test_data = frame.iloc[split:].copy()

    if len(train_data) < 220 or len(test_data) < 60:
        raise ValueError(
            "Walk-forward için eğitimde en az 220, doğrulamada 60 mum gerekir."
        )

    rows = []

    for test_no, (entry, exit_value, holding) in enumerate(combinations, 1):
        config = replace(
            base_config,
            minimum_entry_score=float(entry),
            exit_score=float(exit_value),
            max_holding_bars=int(holding),
        )
        train_result = run_backtest(train_data.copy(), config)
        test_result = run_backtest(test_data.copy(), config)

        error = train_result.get("error") or test_result.get("error")
        if error:
            rows.append({
                "Test": test_no,
                "Minimum Giriş Puanı": entry,
                "Çıkış Puanı": exit_value,
                "Maksimum Bekleme": holding,
                "Durum": "Hata",
                "Hata": str(error),
            })
            continue

        train = train_result.get("metrics", {})
        test = test_result.get("metrics", {})
        tr = _num(train.get("Toplam Getiri %"))
        te = _num(test.get("Toplam Getiri %"))
        pf = _num(test.get("Kâr Faktörü"))
        count = int(_num(test.get("Toplam İşlem")))

        rows.append({
            "Test": test_no,
            "Minimum Giriş Puanı": entry,
            "Çıkış Puanı": exit_value,
            "Maksimum Bekleme": holding,
            "Eğitim Getirisi %": tr,
            "Doğrulama Getirisi %": te,
            "Getiri Farkı": round(abs(tr - te), 2),
            "Doğrulama Kâr Faktörü": pf,
            "Doğrulama Başarı Oranı %": _num(test.get("Başarı Oranı %")),
            "Doğrulama Maksimum Düşüş %": _num(test.get("Maksimum Düşüş %")),
            "Doğrulama İşlem": count,
            "Doğrulama Sharpe": _num(test.get("Sharpe")),
            "Sağlamlık": _label(tr, te, pf, count),
            "Walk-Forward Puanı": _score(train, test),
            "Durum": "Tamamlandı",
            "Hata": "",
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
            ["_order", "Walk-Forward Puanı", "Doğrulama Kâr Faktörü",
             "Doğrulama Getirisi %", "Doğrulama Maksimum Düşüş %"],
            ascending=[False, False, False, False, True],
        ).drop(columns=["_order"]).reset_index(drop=True)
        completed.insert(0, "Sıra", range(1, len(completed) + 1))

    return pd.concat([completed, failed], ignore_index=True)


def best_walk_forward_profile(results: pd.DataFrame) -> dict[str, Any] | None:
    if results is None or results.empty:
        return None
    valid = results[
        (results["Durum"] == "Tamamlandı")
        & results["Sağlamlık"].isin(["Güçlü", "Orta"])
    ]
    if valid.empty:
        valid = results[results["Durum"] == "Tamamlandı"]
    return None if valid.empty else valid.iloc[0].to_dict()
