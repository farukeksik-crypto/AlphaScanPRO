from __future__ import annotations

from math import isfinite
from typing import Any, Mapping

import numpy as np
import pandas as pd

from config.config_loader import (
    get_decision_levels,
    get_technical_score_settings,
    validate_independent_modules,
)


COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "close": (
        "Close",
        "close",
        "Fiyat",
        "fiyat",
    ),
    "ema20": (
        "EMA20",
        "ema20",
        "EMA_20",
        "ema_20",
    ),
    "ema50": (
        "EMA50",
        "ema50",
        "EMA_50",
        "ema_50",
    ),
    "ema200": (
        "EMA200",
        "ema200",
        "EMA_200",
        "ema_200",
    ),
    "rsi": (
        "RSI",
        "RSI14",
        "rsi",
        "rsi14",
        "RSI_14",
    ),
    "macd_hist": (
        "MACD_HIST",
        "MACD_Hist",
        "MACDh",
        "macd_hist",
        "MACD_histogram",
    ),
    "adx": (
        "ADX",
        "ADX14",
        "adx",
        "adx14",
        "ADX_14",
    ),
    "plus_di": (
        "PLUS_DI",
        "+DI",
        "DI_PLUS",
        "DMP",
        "DMP_14",
        "plus_di",
    ),
    "minus_di": (
        "MINUS_DI",
        "-DI",
        "DI_MINUS",
        "DMN",
        "DMN_14",
        "minus_di",
    ),
    "volume": (
        "Volume",
        "volume",
        "Hacim",
        "hacim",
    ),
    "volume_ma": (
        "VOLUME_MA",
        "Volume_MA",
        "VOL_MA",
        "volume_ma",
        "Hacim_MA",
        "hacim_ma",
    ),
}


def _to_float(value: Any) -> float | None:
    """
    Verilen değeri güvenli şekilde float türüne dönüştürür.

    NaN, sonsuz değer veya dönüştürülemeyen veri gelirse None döndürür.
    """

    if value is None:
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if not isfinite(number):
        return None

    return number


def _get_value(
    data: Mapping[str, Any] | pd.Series,
    field_name: str,
) -> float | None:
    """
    Bir göstergeyi farklı olası kolon isimlerinden bulur.
    """

    aliases = COLUMN_ALIASES.get(field_name, (field_name,))

    for column_name in aliases:
        if column_name in data:
            value = _to_float(data[column_name])

            if value is not None:
                return value

    return None


def _is_rule_enabled(rule: Mapping[str, Any]) -> bool:
    return bool(rule.get("enabled", True))


def _rule_points(rule: Mapping[str, Any]) -> int:
    try:
        return max(0, int(rule.get("points", 0)))
    except (TypeError, ValueError):
        return 0


def _rule_description(
    rule: Mapping[str, Any],
    default: str,
) -> str:
    description = str(rule.get("description", default)).strip()
    return description or default


def _decision_from_score(score: int) -> str:
    """
    YAML dosyasındaki eşiklere göre karar üretir.

    Eşikler büyükten küçüğe sıralanır. Böylece YAML içindeki sıra
    değiştirilse bile karar sistemi doğru çalışır.
    """

    decision_levels = get_decision_levels()

    normalized_levels: list[tuple[int, str]] = []

    for level in decision_levels.values():
        if not isinstance(level, Mapping):
            continue

        try:
            minimum_score = int(level.get("minimum_score", 0))
        except (TypeError, ValueError):
            minimum_score = 0

        label = str(level.get("label", "BEKLE")).strip() or "BEKLE"
        normalized_levels.append((minimum_score, label))

    normalized_levels.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    for minimum_score, label in normalized_levels:
        if score >= minimum_score:
            return label

    return "BEKLE"


def calculate_technical_score(
    data: Mapping[str, Any] | pd.Series,
) -> dict[str, Any]:
    """
    Tek bir mum/satır için teknik puan hesaplar.

    Finansal sağlık, katılım uygunluğu, arındırma oranı ve haber puanı
    bu hesaplamaya hiçbir şekilde dahil edilmez.
    """

    settings = get_technical_score_settings()

    maximum_score = settings.get("maximum_score", 100)

    try:
        maximum_score = max(1, int(maximum_score))
    except (TypeError, ValueError):
        maximum_score = 100

    score = 0
    reasons: list[str] = []
    missing_fields: list[str] = []

    close = _get_value(data, "close")
    ema20 = _get_value(data, "ema20")
    ema50 = _get_value(data, "ema50")
    ema200 = _get_value(data, "ema200")
    rsi = _get_value(data, "rsi")
    macd_hist = _get_value(data, "macd_hist")
    adx = _get_value(data, "adx")
    plus_di = _get_value(data, "plus_di")
    minus_di = _get_value(data, "minus_di")
    volume = _get_value(data, "volume")
    volume_ma = _get_value(data, "volume_ma")

    trend_settings = settings.get("trend", {})
    momentum_settings = settings.get("momentum", {})
    trend_strength_settings = settings.get("trend_strength", {})
    volume_settings = settings.get("volume", {})

    # ---------------------------------------------------------
    # 1. EMA50 > EMA200
    # ---------------------------------------------------------
    ema50_above_ema200 = trend_settings.get(
        "ema50_above_ema200",
        {},
    )

    if _is_rule_enabled(ema50_above_ema200):
        if ema50 is None or ema200 is None:
            missing_fields.append("EMA50/EMA200")
        elif ema50 > ema200:
            score += _rule_points(ema50_above_ema200)
            reasons.append(
                _rule_description(
                    ema50_above_ema200,
                    "EMA50 > EMA200",
                )
            )

    # ---------------------------------------------------------
    # 2. Fiyat > EMA50
    # ---------------------------------------------------------
    price_above_ema50 = trend_settings.get(
        "price_above_ema50",
        {},
    )

    if _is_rule_enabled(price_above_ema50):
        if close is None or ema50 is None:
            missing_fields.append("Fiyat/EMA50")
        elif close > ema50:
            score += _rule_points(price_above_ema50)
            reasons.append(
                _rule_description(
                    price_above_ema50,
                    "Fiyat EMA50 üstünde",
                )
            )

    # ---------------------------------------------------------
    # 3. EMA20 > EMA50
    # ---------------------------------------------------------
    ema20_above_ema50 = trend_settings.get(
        "ema20_above_ema50",
        {},
    )

    if _is_rule_enabled(ema20_above_ema50):
        if ema20 is None or ema50 is None:
            missing_fields.append("EMA20/EMA50")
        elif ema20 > ema50:
            score += _rule_points(ema20_above_ema50)
            reasons.append(
                _rule_description(
                    ema20_above_ema50,
                    "Kısa trend güçlü",
                )
            )

    # ---------------------------------------------------------
    # 4. RSI uygun aralıkta
    # ---------------------------------------------------------
    rsi_optimal = momentum_settings.get(
        "rsi_optimal",
        {},
    )

    if _is_rule_enabled(rsi_optimal):
        try:
            rsi_minimum = float(rsi_optimal.get("minimum", 42))
        except (TypeError, ValueError):
            rsi_minimum = 42.0

        try:
            rsi_maximum = float(rsi_optimal.get("maximum", 65))
        except (TypeError, ValueError):
            rsi_maximum = 65.0

        if rsi is None:
            missing_fields.append("RSI")
        elif rsi_minimum <= rsi <= rsi_maximum:
            score += _rule_points(rsi_optimal)
            reasons.append(
                _rule_description(
                    rsi_optimal,
                    "RSI uygun",
                )
            )

    # ---------------------------------------------------------
    # 5. MACD histogram pozitif
    # ---------------------------------------------------------
    macd_positive = momentum_settings.get(
        "macd_positive",
        {},
    )

    if _is_rule_enabled(macd_positive):
        if macd_hist is None:
            missing_fields.append("MACD")
        elif macd_hist > 0:
            score += _rule_points(macd_positive)
            reasons.append(
                _rule_description(
                    macd_positive,
                    "MACD pozitif",
                )
            )

    # ---------------------------------------------------------
    # 6. ADX ve yön onayı
    # ---------------------------------------------------------
    adx_confirmation = trend_strength_settings.get(
        "adx_confirmation",
        {},
    )

    if _is_rule_enabled(adx_confirmation):
        try:
            minimum_adx = float(
                adx_confirmation.get(
                    "minimum_adx",
                    18,
                )
            )
        except (TypeError, ValueError):
            minimum_adx = 18.0

        require_positive_di = bool(
            adx_confirmation.get(
                "require_positive_di",
                True,
            )
        )

        if adx is None:
            missing_fields.append("ADX")
        else:
            adx_condition = adx >= minimum_adx

            if require_positive_di:
                if plus_di is None or minus_di is None:
                    missing_fields.append("+DI/-DI")
                    direction_condition = False
                else:
                    direction_condition = plus_di > minus_di
            else:
                direction_condition = True

            if adx_condition and direction_condition:
                score += _rule_points(adx_confirmation)
                reasons.append(
                    _rule_description(
                        adx_confirmation,
                        "ADX yön onayı",
                    )
                )

    # ---------------------------------------------------------
    # 7. Hacim onayı
    # ---------------------------------------------------------
    volume_confirmation = volume_settings.get(
        "volume_confirmation",
        {},
    )

    volume_ratio: float | None = None

    if _is_rule_enabled(volume_confirmation):
        try:
            minimum_ratio = float(
                volume_confirmation.get(
                    "minimum_ratio",
                    0.85,
                )
            )
        except (TypeError, ValueError):
            minimum_ratio = 0.85

        if volume is None or volume_ma is None:
            missing_fields.append("Hacim/Hacim Ortalaması")
        elif volume_ma <= 0:
            missing_fields.append("Geçerli Hacim Ortalaması")
        else:
            volume_ratio = volume / volume_ma

            if volume_ratio >= minimum_ratio:
                score += _rule_points(volume_confirmation)
                reasons.append(
                    _rule_description(
                        volume_confirmation,
                        "Hacim yeterli",
                    )
                )

    score = int(np.clip(score, 0, maximum_score))
    decision = _decision_from_score(score)

    # Tekrarlanan eksik alanları temizle.
    missing_fields = list(dict.fromkeys(missing_fields))

    if reasons:
        reason_text = " | ".join(reasons)
    else:
        reason_text = "Teknik koşullar henüz yeterli değil"

    return {
        "score": score,
        "puan": score,
        "decision": decision,
        "karar": decision,
        "reasons": reasons,
        "neden": reason_text,
        "missing_fields": missing_fields,
        "eksik_veriler": missing_fields,
        "volume_ratio": volume_ratio,
        "hacim_orani": volume_ratio,
        "maximum_score": maximum_score,
        "independent_modules_valid": validate_independent_modules(),
    }


def calculate_score(
    data: Mapping[str, Any] | pd.Series,
) -> dict[str, Any]:
    """
    Eski modüllerle uyumluluk için kısa fonksiyon adı.
    """

    return calculate_technical_score(data)


def score_row(
    row: Mapping[str, Any] | pd.Series,
) -> pd.Series:
    """
    DataFrame.apply kullanımına uygun sonuç döndürür.
    """

    result = calculate_technical_score(row)

    return pd.Series(
        {
            "Puan": result["score"],
            "Karar": result["decision"],
            "Neden": result["neden"],
            "Hacim_Orani": result["volume_ratio"],
        }
    )


def score_latest(
    dataframe: pd.DataFrame,
) -> dict[str, Any]:
    """
    DataFrame içindeki son geçerli mumun teknik puanını hesaplar.
    """

    if dataframe is None or dataframe.empty:
        return {
            "score": 0,
            "puan": 0,
            "decision": "YETERSİZ VERİ",
            "karar": "YETERSİZ VERİ",
            "reasons": [],
            "neden": "Fiyat verisi bulunamadı",
            "missing_fields": ["Fiyat verisi"],
            "eksik_veriler": ["Fiyat verisi"],
            "volume_ratio": None,
            "hacim_orani": None,
            "maximum_score": 100,
            "independent_modules_valid": (
                validate_independent_modules()
            ),
        }

    valid_dataframe = dataframe.dropna(
        how="all",
    )

    if valid_dataframe.empty:
        return {
            "score": 0,
            "puan": 0,
            "decision": "YETERSİZ VERİ",
            "karar": "YETERSİZ VERİ",
            "reasons": [],
            "neden": "Geçerli mum verisi bulunamadı",
            "missing_fields": ["Geçerli mum"],
            "eksik_veriler": ["Geçerli mum"],
            "volume_ratio": None,
            "hacim_orani": None,
            "maximum_score": 100,
            "independent_modules_valid": (
                validate_independent_modules()
            ),
        }

    latest_row = valid_dataframe.iloc[-1]
    result = calculate_technical_score(latest_row)
    result["index"] = valid_dataframe.index[-1]

    return result


def apply_scores(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """
    DataFrame içindeki tüm satırlara teknik puan ve karar ekler.

    Orijinal DataFrame değiştirilmez; kopyası döndürülür.
    """

    if dataframe is None:
        return pd.DataFrame()

    result_dataframe = dataframe.copy()

    if result_dataframe.empty:
        result_dataframe["Puan"] = pd.Series(dtype="int64")
        result_dataframe["Karar"] = pd.Series(dtype="object")
        result_dataframe["Neden"] = pd.Series(dtype="object")
        result_dataframe["Hacim_Orani"] = pd.Series(dtype="float64")
        return result_dataframe

    scored_rows = result_dataframe.apply(
        score_row,
        axis=1,
    )

    for column_name in scored_rows.columns:
        result_dataframe[column_name] = scored_rows[column_name]

    return result_dataframe


def score_dataframe(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """
    Eski kodlarla uyumluluk için alternatif fonksiyon adı.
    """

    return apply_scores(dataframe)