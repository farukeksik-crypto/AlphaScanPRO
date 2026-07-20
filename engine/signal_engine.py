from __future__ import annotations

from typing import Any

import pandas as pd

from engine.indicators import adx, atr, ema, macd, rsi
from engine.models.decision import Decision
from engine.risk_engine import calculate_risk_levels
from engine.score_engine import calculate_score


MIN_BARS = 220


def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    if value is None:
        return default

    try:
        number = float(value)
    except (TypeError, ValueError):
        return default

    if pd.isna(number):
        return default

    return number


def _normalize_decision(value: Any) -> str:
    decision = str(
        value or "YETERSİZ VERİ"
    ).strip().upper()

    replacements = {
        "IZLE": "İZLE",
        "YETERSIZ VERI": "YETERSİZ VERİ",
        "YETERSİZ VERI": "YETERSİZ VERİ",
        "YETERSIZ VERİ": "YETERSİZ VERİ",
    }

    return replacements.get(decision, decision)


def _quality_from_score(score: float) -> str:
    """
    Puan motoru kalite alanı döndürmezse teknik puandan kalite üretir.
    """

    if score >= 85:
        return "A+"

    if score >= 75:
        return "A"

    if score >= 65:
        return "B"

    if score >= 50:
        return "C"

    return "D"


def _empty_result(
    reason: str,
    bar_count: int = 0,
) -> dict[str, Any]:
    """
    Geçersiz veya yetersiz veri durumlarında standart sonuç üretir.
    """

    return {
        "ok": False,
        "decision": "YETERSİZ VERİ",
        "quality": "D",
        "score": 0.0,
        "reason": reason,
        "price": 0.0,
        "stop": 0.0,
        "target1": 0.0,
        "target2": 0.0,
        "risk_reward1": 0.0,
        "risk_reward2": 0.0,
        "rsi": None,
        "adx": None,
        "bar_count": bar_count,
    }


def _evaluate_dict(frame: pd.DataFrame | None) -> dict[str, Any]:
    bar_count = len(frame) if frame is not None else 0

    if frame is None or not isinstance(frame, pd.DataFrame):
        return _empty_result(
            reason="Geçerli fiyat verisi bulunamadı.",
            bar_count=bar_count,
        )

    if frame.empty or bar_count < MIN_BARS:
        return _empty_result(
            reason=(
                f"{bar_count} mum bulundu. "
                f"En az {MIN_BARS} mum gerekli."
            ),
            bar_count=bar_count,
        )

    required_columns = {
        "High",
        "Low",
        "Close",
        "Volume",
    }

    missing_columns = required_columns.difference(frame.columns)

    if missing_columns:
        return _empty_result(
            reason=(
                "Eksik veri sütunları: "
                + ", ".join(sorted(missing_columns))
            ),
            bar_count=bar_count,
        )

    data = frame.copy()

    data["EMA20"] = ema(
        data["Close"],
        20,
    )

    data["EMA50"] = ema(
        data["Close"],
        50,
    )

    data["EMA200"] = ema(
        data["Close"],
        200,
    )

    data["RSI"] = rsi(
        data["Close"],
    )

    (
        data["MACD"],
        data["MACD_SIGNAL"],
        data["MACD_HIST"],
    ) = macd(
        data["Close"],
    )

    data["ATR"] = atr(
        data,
    )

    plus_di, minus_di, adx_value = adx(
        data,
    )

    data["PLUS_DI"] = plus_di
    data["MINUS_DI"] = minus_di
    data["ADX"] = adx_value

    data["VOLUME_MA"] = (
        data["Volume"]
        .rolling(
            window=20,
            min_periods=20,
        )
        .mean()
    )

    row = data.iloc[-1]

    score_result = calculate_score(
        row,
    )

    if not isinstance(score_result, dict):
        raise TypeError(
            "calculate_score geçerli bir sözlük döndürmedi."
        )

    score = _safe_float(
        score_result.get(
            "score",
            score_result.get(
                "puan",
                0.0,
            ),
        )
    )

    decision = _normalize_decision(
        score_result.get(
            "decision",
            score_result.get(
                "karar",
                "YETERSİZ VERİ",
            ),
        )
    )

    quality = str(
        score_result.get(
            "quality",
            _quality_from_score(score),
        )
    ).upper()

    reason_value = score_result.get(
        "reason",
        score_result.get(
            "neden",
            score_result.get(
                "reasons",
                "",
            ),
        ),
    )

    if isinstance(reason_value, list):
        reason = " | ".join(
            str(item)
            for item in reason_value
            if item
        )
    else:
        reason = str(
            reason_value or ""
        )

    price = _safe_float(
        row.get(
            "Close",
            0.0,
        )
    )

    atr_value = _safe_float(
        row.get(
            "ATR",
            0.0,
        )
    )

    risk_result = calculate_risk_levels(
        price,
        atr_value,
    )

    if not isinstance(risk_result, dict):
        risk_result = {}

    return {
        "ok": True,
        "decision": decision,
        "quality": quality,
        "score": round(score, 1),
        "price": round(price, 4),
        "stop": _safe_float(
            risk_result.get(
                "stop",
                0.0,
            )
        ),
        "target1": _safe_float(
            risk_result.get(
                "target1",
                0.0,
            )
        ),
        "target2": _safe_float(
            risk_result.get(
                "target2",
                0.0,
            )
        ),
        "risk_reward1": _safe_float(
            risk_result.get(
                "risk_reward1",
                0.0,
            )
        ),
        "risk_reward2": _safe_float(
            risk_result.get(
                "risk_reward2",
                0.0,
            )
        ),
        "rsi": _safe_float(
            row.get(
                "RSI",
                0.0,
            )
        ),
        "adx": _safe_float(
            row.get(
                "ADX",
                0.0,
            )
        ),
        "reason": reason,
        "bar_count": bar_count,
    }


def _calculate_confidence(
    result: dict[str, Any],
) -> float:
    """
    Teknik sonuçlardan 0-100 arasında destekleyici güven puanı üretir.

    Güven puanı alım kararını engellemez. Yalnızca sinyal gücünü ve
    önerilen pozisyon büyüklüğünü belirlemek için kullanılır.
    """

    if not bool(result.get("ok", False)):
        return 0.0

    score = _safe_float(
        result.get(
            "score",
            0.0,
        )
    )

    rsi_value = _safe_float(
        result.get(
            "rsi",
            0.0,
        )
    )

    adx_value = _safe_float(
        result.get(
            "adx",
            0.0,
        )
    )

    risk_reward1 = _safe_float(
        result.get(
            "risk_reward1",
            0.0,
        )
    )

    quality = str(
        result.get(
            "quality",
            "D",
        )
    ).upper()

    # Ana ağırlık teknik skordur.
    confidence = score * 0.60

    # ADX trend gücü desteği.
    if adx_value >= 25:
        confidence += 15.0
    elif adx_value >= 18:
        confidence += 10.0
    elif adx_value >= 12:
        confidence += 5.0

    # RSI uygunluk desteği.
    if 45 <= rsi_value <= 62:
        confidence += 10.0
    elif 40 <= rsi_value <= 68:
        confidence += 6.0
    elif rsi_value > 0:
        confidence += 2.0

    # Risk / ödül desteği.
    if risk_reward1 >= 2.0:
        confidence += 10.0
    elif risk_reward1 >= 1.5:
        confidence += 6.0
    elif risk_reward1 >= 1.0:
        confidence += 3.0

    quality_bonus = {
        "A+": 5.0,
        "A": 5.0,
        "B": 3.0,
        "C": 1.0,
        "D": 0.0,
    }

    confidence += quality_bonus.get(
        quality,
        0.0,
    )

    return round(
        max(
            0.0,
            min(
                confidence,
                100.0,
            ),
        ),
        2,
    )


def _position_multiplier(
    confidence: float,
) -> float:
    """
    Güven puanına göre pozisyon büyüklüğü katsayısı belirler.

    Güven puanı işlemi engellemez.
    """

    if confidence >= 80:
        return 1.00

    if confidence >= 65:
        return 0.75

    if confidence >= 50:
        return 0.50

    return 0.25


def evaluate_decision(
    frame: pd.DataFrame | None,
) -> Decision:
    """
    Fiyat verisini değerlendirir ve tip güvenli Decision nesnesi döndürür.
    """

    result = _evaluate_dict(
        frame,
    )

    confidence = _calculate_confidence(
        result,
    )

    position_multiplier = _position_multiplier(
        confidence,
    )

    return Decision(
        ok=bool(
            result.get(
                "ok",
                False,
            )
        ),
        action=_normalize_decision(
            result.get(
                "decision",
                "YETERSİZ VERİ",
            )
        ),
        quality=str(
            result.get(
                "quality",
                "D",
            )
        ),
        score=_safe_float(
            result.get(
                "score",
                0.0,
            )
        ),
        reason=str(
            result.get(
                "reason",
                "",
            )
            or ""
        ),
        price=_safe_float(
            result.get(
                "price",
                0.0,
            )
        ),
        stop=_safe_float(
            result.get(
                "stop",
                0.0,
            )
        ),
        target1=_safe_float(
            result.get(
                "target1",
                0.0,
            )
        ),
        target2=_safe_float(
            result.get(
                "target2",
                0.0,
            )
        ),
        risk_reward1=_safe_float(
            result.get(
                "risk_reward1",
                0.0,
            )
        ),
        risk_reward2=_safe_float(
            result.get(
                "risk_reward2",
                0.0,
            )
        ),
        rsi=(
            None
            if result.get("rsi") is None
            else _safe_float(
                result.get(
                    "rsi",
                    0.0,
                )
            )
        ),
        adx=(
            None
            if result.get("adx") is None
            else _safe_float(
                result.get(
                    "adx",
                    0.0,
                )
            )
        ),
        confidence=confidence,
        position_multiplier=position_multiplier,
    )


def evaluate(
    frame: pd.DataFrame | None,
) -> dict[str, Any]:
    """
    Geriye uyumluluk katmanı.

    Mevcut modüller sözlük beklediği için eski çıktı biçimini korur.
    Yeni kodlarda evaluate_decision kullanılması önerilir.
    """

    return evaluate_decision(
        frame,
    ).to_dict()