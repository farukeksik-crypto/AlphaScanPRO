from __future__ import annotations

from datetime import datetime

from config.settings import DIAGNOSTIC_SYMBOLS


def run_diagnostics(data_engine, cache_engine, database):
    rows = []

    for name, config in DIAGNOSTIC_SYMBOLS.items():
        try:
            if config["provider"] == "yahoo":
                frame = data_engine.get_yahoo(
                    symbol=config["symbol"],
                    period=config["period"],
                    interval=config["interval"],
                )
                interval = config["interval"]
            else:
                frame = data_engine.get_binance(
                    symbol=config["symbol"],
                    timeframe=config["timeframe"],
                    limit=config["limit"],
                )
                interval = config["timeframe"]

            rows.append(
                {
                    "Test": name,
                    "Sağlayıcı": config["provider"].upper(),
                    "Durum": "OK" if len(frame) else "VERİ YOK",
                    "Mum": len(frame),
                    "Son Mum": str(frame.index[-1]) if len(frame) else "—",
                    "Zaman Dilimi": interval,
                    "Hata": "",
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "Test": name,
                    "Sağlayıcı": config["provider"].upper(),
                    "Durum": "HATA",
                    "Mum": 0,
                    "Son Mum": "—",
                    "Zaman Dilimi": config.get("interval", config.get("timeframe", "?")),
                    "Hata": str(exc),
                }
            )

    rows.append(
        {
            "Test": "SQLite",
            "Sağlayıcı": "YEREL",
            "Durum": "OK" if database.health_check() else "HATA",
            "Mum": 0,
            "Son Mum": datetime.now().isoformat(timespec="seconds"),
            "Zaman Dilimi": "—",
            "Hata": "",
        }
    )

    rows.append(
        {
            "Test": "Cache",
            "Sağlayıcı": "YEREL",
            "Durum": "OK",
            "Mum": len(cache_engine.status()),
            "Son Mum": datetime.now().isoformat(timespec="seconds"),
            "Zaman Dilimi": "—",
            "Hata": "",
        }
    )

    return rows
