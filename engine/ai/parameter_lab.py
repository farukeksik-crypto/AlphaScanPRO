from __future__ import annotations

from dataclasses import asdict, replace
from itertools import product
from typing import Any, Callable

import pandas as pd


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _strategy_score(metrics: dict[str, Any]) -> float:
    """
    Yalnızca en yüksek getiriyi değil, risk-getiri dengesini puanlar.
    """
    total_return = _safe_float(metrics.get("Toplam Getiri %"))
    profit_factor = _safe_float(metrics.get("Kâr Faktörü"))
    max_drawdown = _safe_float(metrics.get("Maksimum Düşüş %"))
    win_rate = _safe_float(metrics.get("Başarı Oranı %"))
    total_trades = int(_safe_float(metrics.get("Toplam İşlem")))

    return_score = max(min(total_return, 50.0), -50.0) * 1.2
    profit_factor_score = max(min(profit_factor, 3.0), 0.0) * 18.0
    drawdown_score = max(0.0, 30.0 - max_drawdown * 1.5)
    win_rate_score = max(min(win_rate, 80.0), 0.0) * 0.35
    sample_score = min(total_trades, 50) * 0.30

    penalty = 0.0

    if total_trades < 10:
        penalty += 20.0
    elif total_trades < 20:
        penalty += 8.0

    if profit_factor < 1.0:
        penalty += 20.0

    if total_return < 0:
        penalty += abs(total_return) * 1.5

    score = (
        return_score
        + profit_factor_score
        + drawdown_score
        + win_rate_score
        + sample_score
        - penalty
    )

    return round(score, 2)


def run_parameter_lab(
    *,
    data: pd.DataFrame,
    base_config,
    run_backtest: Callable,
    entry_scores: list[int],
    exit_scores: list[int],
    holding_bars: list[int],
    max_combinations: int = 200,
) -> pd.DataFrame:
    combinations = list(
        product(
            entry_scores,
            exit_scores,
            holding_bars,
        )
    )

    if len(combinations) > max_combinations:
        raise ValueError(
            f"Seçilen {len(combinations)} kombinasyon sınırı aşıyor. "
            f"En fazla {max_combinations} kombinasyon kullanılabilir."
        )

    rows: list[dict[str, Any]] = []

    for index, (
        minimum_entry_score,
        exit_score,
        max_holding_bars,
    ) in enumerate(combinations, start=1):
        config = replace(
            base_config,
            minimum_entry_score=float(minimum_entry_score),
            exit_score=float(exit_score),
            max_holding_bars=int(max_holding_bars),
        )

        result = run_backtest(
            data.copy(),
            config,
        )

        if result.get("error"):
            rows.append(
                {
                    "Test": index,
                    "Minimum Giriş Puanı": minimum_entry_score,
                    "Çıkış Puanı": exit_score,
                    "Maksimum Bekleme": max_holding_bars,
                    "Durum": "Hata",
                    "Hata": result["error"],
                }
            )
            continue

        metrics = result.get("metrics", {})

        rows.append(
            {
                "Test": index,
                "Minimum Giriş Puanı": minimum_entry_score,
                "Çıkış Puanı": exit_score,
                "Maksimum Bekleme": max_holding_bars,
                "Toplam Getiri %": _safe_float(
                    metrics.get("Toplam Getiri %")
                ),
                "Başarı Oranı %": _safe_float(
                    metrics.get("Başarı Oranı %")
                ),
                "Kâr Faktörü": _safe_float(
                    metrics.get("Kâr Faktörü")
                ),
                "Maksimum Düşüş %": _safe_float(
                    metrics.get("Maksimum Düşüş %")
                ),
                "Toplam İşlem": int(
                    _safe_float(
                        metrics.get("Toplam İşlem")
                    )
                ),
                "Son Bakiye": _safe_float(
                    metrics.get("Son Bakiye")
                ),
                "Sharpe": _safe_float(
                    metrics.get("Sharpe")
                ),
                "Strateji Puanı": _strategy_score(metrics),
                "Durum": "Tamamlandı",
            }
        )

    frame = pd.DataFrame(rows)

    if frame.empty:
        return frame

    completed = frame[
        frame["Durum"] == "Tamamlandı"
    ].copy()

    failed = frame[
        frame["Durum"] != "Tamamlandı"
    ].copy()

    if not completed.empty:
        completed = completed.sort_values(
            [
                "Strateji Puanı",
                "Kâr Faktörü",
                "Toplam Getiri %",
                "Maksimum Düşüş %",
            ],
            ascending=[False, False, False, True],
        ).reset_index(drop=True)

        completed.insert(
            0,
            "Sıra",
            range(1, len(completed) + 1),
        )

    return pd.concat(
        [completed, failed],
        ignore_index=True,
    )


def best_profile(results: pd.DataFrame) -> dict[str, Any] | None:
    if results is None or results.empty:
        return None

    valid = results[
        results["Durum"] == "Tamamlandı"
    ]

    if valid.empty:
        return None

    return valid.iloc[0].to_dict()