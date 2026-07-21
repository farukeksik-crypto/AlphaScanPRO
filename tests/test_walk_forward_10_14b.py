import pandas as pd

from engine.ai.walk_forward_lab import add_parameter_robustness, best_robust_profile


def sample_results():
    rows = []
    n = 0
    for entry in [60, 65, 70]:
        for exit_score in [35, 40, 45]:
            for holding in [20, 40]:
                n += 1
                score = 70 - abs(entry - 65) * 2 - abs(exit_score - 40) - abs(holding - 20) / 5
                rows.append({
                    "Sıra": n,
                    "Minimum Giriş Puanı": entry,
                    "Çıkış Puanı": exit_score,
                    "Maksimum Bekleme": holding,
                    "Doğrulama Getirisi %": 5.0 if score > 45 else -1.0,
                    "Walk-Forward Puanı": score,
                    "Durum": "Tamamlandı",
                })
    return pd.DataFrame(rows)


def test_adds_neighbour_robustness_columns():
    result = add_parameter_robustness(sample_results())
    assert {"Komşu Profil", "Komşu Ortalama Puan", "Parametre Sağlamlığı", "Aşırı Uyum Riski"}.issubset(result.columns)
    center = result[(result["Minimum Giriş Puanı"] == 65) & (result["Çıkış Puanı"] == 40) & (result["Maksimum Bekleme"] == 20)].iloc[0]
    assert center["Komşu Profil"] >= 7
    assert 0 <= center["Parametre Sağlamlığı"] <= 100


def test_best_robust_profile_prefers_low_risk_plateau():
    result = sample_results()
    isolated = result.iloc[0].copy()
    isolated["Minimum Giriş Puanı"] = 90
    isolated["Çıkış Puanı"] = 20
    isolated["Maksimum Bekleme"] = 80
    isolated["Walk-Forward Puanı"] = 150
    result = pd.concat([result, pd.DataFrame([isolated])], ignore_index=True)
    best = best_robust_profile(result)
    assert best is not None
    assert best["Aşırı Uyum Riski"] in {"Düşük", "Orta"}
    assert best["Minimum Giriş Puanı"] != 90


def test_empty_input_is_safe():
    empty = pd.DataFrame()
    assert add_parameter_robustness(empty).empty
    assert best_robust_profile(empty) is None
