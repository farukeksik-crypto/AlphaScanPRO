from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd


BENCHMARK_SYMBOL = "XU100.IS"

INTERVAL_PERIODS = {
    "15m": "5d",
    "30m": "10d",
    "1h": "30d",
    "60m": "30d",
    "1d": "3mo",
}


def _percent_change(frame: pd.DataFrame) -> float:
    """
    Son iki mumun kapanış fiyatını karşılaştırarak yüzde değişimi hesaplar.
    """

    if frame is None or frame.empty or len(frame) < 2:
        raise ValueError("Yüzde değişim için en az 2 mum gerekli.")

    previous_close = float(frame["Close"].iloc[-2])
    latest_close = float(frame["Close"].iloc[-1])

    if previous_close <= 0:
        raise ValueError("Önceki kapanış fiyatı geçersiz.")

    return ((latest_close / previous_close) - 1) * 100


def _classify(
    benchmark_change: float,
    asset_change: float,
    relative_change: float,
) -> str:
    """
    BIST 100 ile hissenin yönünü karşılaştırır.
    """

    if benchmark_change < 0 and asset_change > 0:
        return "BIST düşerken yükseliyor"

    if benchmark_change > 0 and asset_change < 0:
        return "BIST yükselirken düşüyor"

    if benchmark_change < 0 and asset_change < 0:
        if relative_change > 0:
            return "BIST'ten daha az düşüyor"
        return "BIST'ten daha fazla düşüyor"

    if benchmark_change > 0 and asset_change > 0:
        if relative_change > 0:
            return "BIST'ten daha fazla yükseliyor"
        return "BIST'ten daha az yükseliyor"

    if asset_change > 0:
        return "Yükseliyor"

    if asset_change < 0:
        return "Düşüyor"

    return "Yatay"


def scan_relative_strength(
    data_engine,
    items: list[dict],
    interval: str = "1h",
    workers: int = 4,
    force_refresh: bool = False,
):
    """
    Arındırması sıfır hisseleri BIST 100 ile karşılaştırır.

    Sonuçlar göreceli farka göre güçlüden zayıfa sıralanır.
    """

    if interval not in INTERVAL_PERIODS:
        raise ValueError(
            f"Desteklenmeyen zaman dilimi: {interval}"
        )

    period = INTERVAL_PERIODS[interval]

    benchmark_frame = data_engine.get_yahoo(
        BENCHMARK_SYMBOL,
        period,
        interval,
        force_refresh=force_refresh,
    )

    if benchmark_frame.empty or len(benchmark_frame) < 2:
        raise ValueError(
            "BIST 100 verisi alınamadı veya yetersiz veri döndü."
        )

    benchmark_change = _percent_change(benchmark_frame)
    benchmark_price = float(benchmark_frame["Close"].iloc[-1])

    results = []
    failures = []

    def run(item: dict) -> dict:
        code = item["kod"]
        symbol = code if code.endswith(".IS") else f"{code}.IS"

        frame = data_engine.get_yahoo(
            symbol,
            period,
            interval,
            force_refresh=force_refresh,
        )

        if frame.empty or len(frame) < 2:
            raise ValueError("Yeterli fiyat verisi bulunamadı.")

        asset_change = _percent_change(frame)
        relative_change = asset_change - benchmark_change
        latest_price = float(frame["Close"].iloc[-1])

        return {
            "Kod": code,
            "Hisse": item.get("ad", code),
            "Zaman": interval,
            "Fiyat": round(latest_price, 4),
            "BIST 100": round(benchmark_change, 2),
            "Hisse %": round(asset_change, 2),
            "Göreceli Fark": round(relative_change, 2),
            "Durum": _classify(
                benchmark_change,
                asset_change,
                relative_change,
            ),
            "Mum": len(frame),
        }

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(run, item): item
            for item in items
        }

        for future in as_completed(future_map):
            item = future_map[future]

            try:
                results.append(future.result())
            except Exception as exc:
                failures.append(
                    {
                        "Kod": item.get("kod", "?"),
                        "Hisse": item.get("ad", "?"),
                        "Hata": str(exc),
                    }
                )

    results.sort(
        key=lambda row: row["Göreceli Fark"],
        reverse=True,
    )

    summary = {
        "benchmark_symbol": BENCHMARK_SYMBOL,
        "benchmark_price": round(benchmark_price, 2),
        "benchmark_change": round(benchmark_change, 2),
        "interval": interval,
        "total": len(results),
        "failures": len(failures),
        "bist_duserken_yukselen": sum(
            1
            for row in results
            if row["BIST 100"] < 0 and row["Hisse %"] > 0
        ),
        "bist_yukselirken_dusen": sum(
            1
            for row in results
            if row["BIST 100"] > 0 and row["Hisse %"] < 0
        ),
        "endeksten_guclu": sum(
            1
            for row in results
            if row["Göreceli Fark"] > 0
        ),
        "endeksten_zayif": sum(
            1
            for row in results
            if row["Göreceli Fark"] < 0
        ),
    }

    return results, failures, summary