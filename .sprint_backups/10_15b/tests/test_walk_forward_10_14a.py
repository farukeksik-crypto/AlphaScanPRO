from dataclasses import dataclass

import pandas as pd

from engine.ai.walk_forward_lab import best_walk_forward_profile, run_walk_forward_lab


@dataclass
class Config:
    minimum_entry_score: float = 62
    exit_score: float = 42
    max_holding_bars: int = 40


def fake_backtest(frame, config):
    size = len(frame)
    entry_bonus = (70 - abs(config.minimum_entry_score - 65)) / 70
    ret = round((size / 1000) * entry_bonus * 10 - config.max_holding_bars / 200, 2)
    return {"error": "", "metrics": {
        "Toplam Getiri %": ret,
        "Kâr Faktörü": 1.4,
        "Maksimum Düşüş %": 4.0,
        "Başarı Oranı %": 58.0,
        "Toplam İşlem": 8,
        "Sharpe": 1.1,
    }}


def data(rows=700):
    index = pd.date_range("2024-01-01", periods=rows, freq="h")
    return pd.DataFrame({"Close": range(rows)}, index=index)


def test_rolling_walk_forward_returns_fold_metrics():
    result = run_walk_forward_lab(
        data=data(), base_config=Config(), run_backtest=fake_backtest,
        entry_scores=[60, 65], exit_scores=[40], holding_bars=[20],
        train_ratio=0.60, folds=3,
    )
    assert len(result) == 2
    assert set(["Pozitif Fold %", "Stabilite Puanı", "Fold Sayısı"]).issubset(result.columns)
    assert result.iloc[0]["Fold Sayısı"] == 3


def test_single_fold_backward_compatible():
    result = run_walk_forward_lab(
        data=data(500), base_config=Config(), run_backtest=fake_backtest,
        entry_scores=[62], exit_scores=[42], holding_bars=[40],
        train_ratio=0.70, folds=1,
    )
    assert result.iloc[0]["Durum"] == "Tamamlandı"
    assert best_walk_forward_profile(result) is not None


def test_rejects_too_small_fold():
    try:
        run_walk_forward_lab(
            data=data(300), base_config=Config(), run_backtest=fake_backtest,
            entry_scores=[62], exit_scores=[42], holding_bars=[40],
            train_ratio=0.70, folds=2,
        )
    except ValueError as exc:
        assert "en az 60" in str(exc)
    else:
        raise AssertionError("ValueError bekleniyordu")
