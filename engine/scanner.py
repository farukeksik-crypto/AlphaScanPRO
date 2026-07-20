from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import pandas as pd

from engine.models.decision import Decision
from engine.signal_engine import evaluate_decision


DECISION_ORDER: dict[str, int] = {
    "NET AL": 0,
    "AL ADAY": 1,
    "İZLE": 2,
    "IZLE": 2,
    "BEKLE": 3,
    "YETERSİZ VERİ": 4,
    "YETERSIZ VERI": 4,
}


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


def _safe_int(
    value: Any,
    default: int = 0,
) -> int:
    if value is None:
        return default

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


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


def _validate_frame(
    frame: pd.DataFrame | None,
    minimum_bars: int = 1,
) -> pd.DataFrame:
    if frame is None:
        raise ValueError(
            "Veri motoru boş sonuç döndürdü."
        )

    if not isinstance(frame, pd.DataFrame):
        raise TypeError(
            "Veri motoru pandas DataFrame döndürmedi."
        )

    if frame.empty:
        raise ValueError(
            "Fiyat verisi bulunamadı."
        )

    if len(frame) < minimum_bars:
        raise ValueError(
            f"Yetersiz mum verisi: {len(frame)} mum bulundu."
        )

    return frame


def _evaluate_frame(
    frame: pd.DataFrame,
) -> Decision:
    decision = evaluate_decision(frame)

    if not isinstance(decision, Decision):
        raise TypeError(
            "Signal Engine geçerli bir Decision sonucu döndürmedi."
        )

    return decision


def _common_signal_fields(
    decision: Decision,
    frame: pd.DataFrame,
) -> dict[str, Any]:
    return {
        "Karar": _normalize_decision(decision.action),
        "Kalite": decision.quality,
        "Puan": _safe_int(decision.score),

        # Sprint 2 - Güven Analizi
        "Güven": round(decision.confidence, 1),
        "Güven Seviyesi": decision.confidence_label,
        "Pozisyon %": round(
            decision.suggested_position_percent,
            1,
        ),

        "Fiyat": _safe_float(decision.price),
        "Stop": _safe_float(decision.stop),
        "Hedef 1": _safe_float(decision.target1),
        "Hedef 2": _safe_float(decision.target2),
        "R/K 1": _safe_float(decision.risk_reward1),
        "R/K 2": _safe_float(decision.risk_reward2),
        "RSI": decision.rsi,
        "ADX": decision.adx,
        "Neden": decision.reason,
        "Mum": len(frame),
    }

def _result_sort_key(
    row: dict[str, Any],
    name_field: str,
) -> tuple[int, int, str]:
    decision = _normalize_decision(
        row.get(
            "Karar",
            "YETERSİZ VERİ",
        )
    )

    score = _safe_int(
        row.get(
            "Puan",
            0,
        )
    )

    name = str(
        row.get(
            name_field,
            "",
        )
    )

    return (
        DECISION_ORDER.get(decision, 99),
        -score,
        name,
    )


def _resolve_yahoo_symbol(
    item: dict[str, Any],
) -> tuple[str, str]:
    """
    Hisse kodunu ve Yahoo sembolünü güvenli şekilde belirler.

    Öncelik sırası:
    1. item["sembol"]
    2. item["symbol"]
    3. item["kod"] + ".IS"
    """

    code = str(
        item.get(
            "kod",
            "",
        )
    ).strip().upper()

    configured_symbol = str(
        item.get(
            "sembol",
            item.get(
                "symbol",
                "",
            ),
        )
    ).strip().upper()

    if not code and not configured_symbol:
        raise ValueError(
            "Hisse kodu veya sembol bilgisi bulunamadı."
        )

    if configured_symbol:
        symbol = configured_symbol
    elif code.endswith(".IS"):
        symbol = code
    else:
        symbol = f"{code}.IS"

    if not code:
        code = symbol.removesuffix(".IS")

    clean_code = code.removesuffix(".IS")

    return clean_code, symbol


def scan_yahoo_items(
    data_engine: Any,
    items: list[dict[str, Any]],
    workers: int = 4,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """
    BIST hisselerini Yahoo Finance üzerinden paralel tarar.
    """

    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    safe_workers = max(
        1,
        min(
            int(workers),
            12,
        ),
    )

    def run(
        item: dict[str, Any],
    ) -> dict[str, Any]:
        code, symbol = _resolve_yahoo_symbol(
            item
        )

        frame = data_engine.get_yahoo(
            symbol,
            "2y",
            "1d",
        )

        frame = _validate_frame(frame)
        decision = _evaluate_frame(frame)

        return {
            "Kod": code,
            "Hisse": str(
                item.get(
                    "ad",
                    code,
                )
            ),
            **_common_signal_fields(
                decision,
                frame,
            ),
        }

    with ThreadPoolExecutor(
        max_workers=safe_workers
    ) as executor:
        future_map = {
            executor.submit(
                run,
                item,
            ): item
            for item in items
        }

        for future in as_completed(
            future_map
        ):
            item = future_map[future]

            try:
                results.append(
                    future.result()
                )

            except Exception as exc:
                failures.append(
                    {
                        "Kod": str(
                            item.get(
                                "kod",
                                "?",
                            )
                        ),
                        "Hisse": str(
                            item.get(
                                "ad",
                                "?",
                            )
                        ),
                        "Sembol": str(
                            item.get(
                                "sembol",
                                item.get(
                                    "symbol",
                                    "",
                                ),
                            )
                        ),
                        "Hata": str(exc),
                    }
                )

    results.sort(
        key=lambda row: _result_sort_key(
            row,
            "Kod",
        )
    )

    return results, failures


def scan_crypto(
    data_engine: Any,
    pairs: dict[str, str],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """
    Kripto paritelerini Binance üzerinden tarar.
    """

    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for name, symbol in pairs.items():
        try:
            clean_name = str(
                name
            ).strip()

            clean_symbol = str(
                symbol
            ).strip()

            if not clean_symbol:
                raise ValueError(
                    "Kripto parite sembolü bulunamadı."
                )

            frame = data_engine.get_binance(
                clean_symbol,
                "1h",
                1000,
            )

            frame = _validate_frame(frame)
            decision = _evaluate_frame(frame)

            rows.append(
                {
                    "Coin": clean_name,
                    **_common_signal_fields(
                        decision,
                        frame,
                    ),
                }
            )

        except Exception as exc:
            failures.append(
                {
                    "Coin": str(name),
                    "Sembol": str(symbol),
                    "Hata": str(exc),
                }
            )

    rows.sort(
        key=lambda row: _result_sort_key(
            row,
            "Coin",
        )
    )

    return rows, failures


def scan_commodities(
    data_engine: Any,
    symbols: dict[str, str],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """
    Emtia sembollerini Yahoo Finance üzerinden tarar.
    """

    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for name, symbol in symbols.items():
        try:
            clean_name = str(
                name
            ).strip()

            clean_symbol = str(
                symbol
            ).strip()

            if not clean_symbol:
                raise ValueError(
                    "Emtia sembolü bulunamadı."
                )

            frame = data_engine.get_yahoo(
                clean_symbol,
                "2y",
                "1d",
            )

            frame = _validate_frame(frame)
            decision = _evaluate_frame(frame)

            rows.append(
                {
                    "Emtia": clean_name,
                    **_common_signal_fields(
                        decision,
                        frame,
                    ),
                }
            )

        except Exception as exc:
            failures.append(
                {
                    "Emtia": str(name),
                    "Sembol": str(symbol),
                    "Hata": str(exc),
                }
            )

    rows.sort(
        key=lambda row: _result_sort_key(
            row,
            "Emtia",
        )
    )

    return rows, failures