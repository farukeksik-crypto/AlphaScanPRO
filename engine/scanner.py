from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from engine.signal_engine import evaluate


def scan_yahoo_items(data_engine, items: list[dict], workers: int = 4):
    results = []
    failures = []

    def run(item):
        code = item["kod"]
        symbol = code if code.endswith(".IS") else f"{code}.IS"
        frame = data_engine.get_yahoo(symbol, "2y", "1d")
        signal = evaluate(frame)
        return {
            "Kod": code,
            "Hisse": item.get("ad", code),
            "Karar": signal["decision"],
            "Puan": signal["score"],
            "Fiyat": signal.get("price", 0),
            "Stop": signal.get("stop", 0),
            "Hedef": signal.get("target", 0),
            "RSI": signal.get("rsi"),
            "ADX": signal.get("adx"),
            "Neden": signal.get("reason", ""),
            "Mum": len(frame),
        }

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {executor.submit(run, item): item for item in items}
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

    order = {"NET AL": 0, "AL ADAY": 1, "IZLE": 2, "BEKLE": 3, "YETERSIZ VERI": 4}
    results.sort(key=lambda row: (order.get(row["Karar"], 99), -row["Puan"]))
    return results, failures


def scan_crypto(data_engine, pairs: dict[str, str]):
    rows = []
    failures = []

    for name, symbol in pairs.items():
        try:
            frame = data_engine.get_binance(symbol, "1h", 1000)
            signal = evaluate(frame)
            rows.append(
                {
                    "Coin": name,
                    "Karar": signal["decision"],
                    "Puan": signal["score"],
                    "Fiyat": signal.get("price", 0),
                    "Stop": signal.get("stop", 0),
                    "Hedef": signal.get("target", 0),
                    "RSI": signal.get("rsi"),
                    "ADX": signal.get("adx"),
                    "Neden": signal.get("reason", ""),
                    "Mum": len(frame),
                }
            )
        except Exception as exc:
            failures.append({"Coin": name, "Hata": str(exc)})

    rows.sort(key=lambda row: -row["Puan"])
    return rows, failures


def scan_commodities(data_engine, symbols: dict[str, str]):
    rows = []
    failures = []

    for name, symbol in symbols.items():
        try:
            frame = data_engine.get_yahoo(symbol, "2y", "1d")
            signal = evaluate(frame)
            rows.append(
                {
                    "Emtia": name,
                    "Karar": signal["decision"],
                    "Puan": signal["score"],
                    "Fiyat": signal.get("price", 0),
                    "Stop": signal.get("stop", 0),
                    "Hedef": signal.get("target", 0),
                    "RSI": signal.get("rsi"),
                    "ADX": signal.get("adx"),
                    "Neden": signal.get("reason", ""),
                    "Mum": len(frame),
                }
            )
        except Exception as exc:
            failures.append({"Emtia": name, "Hata": str(exc)})

    rows.sort(key=lambda row: -row["Puan"])
    return rows, failures
