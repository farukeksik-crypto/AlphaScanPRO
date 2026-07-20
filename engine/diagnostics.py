from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from config.settings import DIAGNOSTIC_SYMBOLS

try:
    from engine.signal_engine import MIN_BARS
except Exception:
    MIN_BARS = 220


def _utc_now() -> pd.Timestamp:
    return pd.Timestamp.now(tz="UTC")


def _to_utc(value: Any) -> pd.Timestamp | None:
    if value in (None, "", "—"):
        return None
    try:
        ts = pd.Timestamp(value)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        return ts
    except Exception:
        return None


def _freshness_limit(interval: str, provider: str) -> pd.Timedelta:
    interval = str(interval).lower().strip()
    provider = str(provider).lower().strip()

    if interval.endswith("m"):
        try:
            minutes = max(1, int(interval[:-1]))
        except ValueError:
            minutes = 15
        return pd.Timedelta(minutes=max(minutes * 3, 30))

    if interval.endswith("h"):
        try:
            hours = max(1, int(interval[:-1]))
        except ValueError:
            hours = 1
        return pd.Timedelta(hours=max(hours * 3, 3))

    if interval in {"1d", "d", "day", "daily"}:
        # Hafta sonu ve resmi tatil boşlukları için güvenli tolerans.
        return pd.Timedelta(days=4 if provider == "yahoo" else 2)

    if interval in {"1wk", "1w", "w"}:
        return pd.Timedelta(days=10)

    return pd.Timedelta(days=4)


def _age_text(last_bar: Any) -> tuple[str, float | None]:
    last_ts = _to_utc(last_bar)
    if last_ts is None:
        return "—", None

    age = max(pd.Timedelta(0), _utc_now() - last_ts)
    hours = age.total_seconds() / 3600

    if hours < 1:
        return f"{max(0, int(age.total_seconds() / 60))} dk", hours
    if hours < 48:
        return f"{hours:.1f} saat", hours
    return f"{hours / 24:.1f} gün", hours


def _quality_report(frame: pd.DataFrame) -> tuple[int, str]:
    if frame is None or frame.empty:
        return 0, "Veri yok"

    score = 100
    notes: list[str] = []

    if not frame.index.is_monotonic_increasing:
        score -= 20
        notes.append("tarih sırası bozuk")

    duplicate_count = int(frame.index.duplicated().sum())
    if duplicate_count:
        score -= min(25, duplicate_count * 2)
        notes.append(f"{duplicate_count} tekrarlı mum")

    price_columns = [c for c in ["Open", "High", "Low", "Close"] if c in frame.columns]
    if price_columns:
        null_count = int(frame[price_columns].isna().sum().sum())
        if null_count:
            score -= min(30, null_count)
            notes.append(f"{null_count} boş fiyat")

        numeric = frame[price_columns].apply(pd.to_numeric, errors="coerce")
        non_positive = int((numeric <= 0).sum().sum())
        if non_positive:
            score -= min(30, non_positive)
            notes.append(f"{non_positive} geçersiz fiyat")

        if {"High", "Low"}.issubset(numeric.columns):
            invalid_hl = int((numeric["High"] < numeric["Low"]).sum())
            if invalid_hl:
                score -= min(30, invalid_hl * 3)
                notes.append(f"{invalid_hl} high/low hatası")

    if "Volume" in frame.columns:
        volume = pd.to_numeric(frame["Volume"], errors="coerce")
        negative_volume = int((volume < 0).sum())
        if negative_volume:
            score -= min(20, negative_volume * 2)
            notes.append(f"{negative_volume} negatif hacim")

    score = max(0, min(100, score))
    return score, ", ".join(notes) if notes else "Temiz"


def _market_test_row(
    *,
    name: str,
    provider: str,
    interval: str,
    frame: pd.DataFrame,
) -> dict[str, Any]:
    row_count = int(len(frame))
    last_bar = frame.index[-1] if row_count else None
    age_text, _ = _age_text(last_bar)
    quality_score, quality_note = _quality_report(frame)
    required_bars = int(MIN_BARS)
    adequacy = min(100.0, (row_count / required_bars * 100)) if required_bars else 100.0

    if row_count == 0:
        status = "VERİ YOK"
        warning = "Sağlayıcı boş veri döndürdü."
    else:
        last_ts = _to_utc(last_bar)
        stale = last_ts is None or (_utc_now() - last_ts) > _freshness_limit(interval, provider)
        insufficient = row_count < required_bars

        if stale:
            status = "ESKİ VERİ"
            warning = "Son mum izin verilen tazelik sınırını aşıyor."
        elif insufficient:
            status = "YETERSİZ MUM"
            warning = f"Teknik analiz için en az {required_bars} mum gerekli."
        elif quality_score < 80:
            status = "UYARI"
            warning = quality_note
        else:
            status = "OK"
            warning = ""

    return {
        "Test": name,
        "Sağlayıcı": provider.upper(),
        "Durum": status,
        "Mum": row_count,
        "Gerekli Mum": required_bars,
        "Yeterlilik %": round(adequacy, 1),
        "Son Mum": str(last_bar) if last_bar is not None else "—",
        "Veri Yaşı": age_text,
        "Zaman Dilimi": interval,
        "Kalite": f"{quality_score}/100",
        "Kalite Notu": quality_note,
        "Uyarı": warning,
        "Hata": "",
    }


def _local_row(name: str, status: str, detail: str = "", count: int = 0) -> dict[str, Any]:
    return {
        "Test": name,
        "Sağlayıcı": "YEREL",
        "Durum": status,
        "Mum": count,
        "Gerekli Mum": 0,
        "Yeterlilik %": 100.0 if status == "OK" else 0.0,
        "Son Mum": datetime.now().isoformat(timespec="seconds"),
        "Veri Yaşı": "şimdi",
        "Zaman Dilimi": "—",
        "Kalite": "100/100" if status == "OK" else "0/100",
        "Kalite Notu": detail or ("Sağlıklı" if status == "OK" else "Kontrol gerekli"),
        "Uyarı": "" if status == "OK" else detail,
        "Hata": "" if status == "OK" else detail,
    }


def run_diagnostics(data_engine, cache_engine, database) -> list[dict[str, Any]]:
    """Veri sağlayıcıları, veri kalitesi, SQLite ve cache sağlığını test eder.

    Dönüş tipi eski arayüzle uyumlu kalması için satır listesi olarak korunur.
    """
    rows: list[dict[str, Any]] = []

    for name, config in DIAGNOSTIC_SYMBOLS.items():
        provider = str(config["provider"]).lower()
        interval = str(config.get("interval", config.get("timeframe", "?")))

        try:
            if provider == "yahoo":
                frame = data_engine.get_yahoo(
                    symbol=config["symbol"],
                    period=config["period"],
                    interval=config["interval"],
                )
            else:
                frame = data_engine.get_binance(
                    symbol=config["symbol"],
                    timeframe=config["timeframe"],
                    limit=config["limit"],
                )

            rows.append(
                _market_test_row(
                    name=name,
                    provider=provider,
                    interval=interval,
                    frame=frame,
                )
            )
        except Exception as exc:
            row = _local_row(name, "HATA", str(exc))
            row["Sağlayıcı"] = provider.upper()
            row["Zaman Dilimi"] = interval
            rows.append(row)

    try:
        db_ok = bool(database.health_check())
        rows.append(_local_row("SQLite", "OK" if db_ok else "HATA", "SQLite bağlantı/yazma kontrolü başarısız." if not db_ok else "Sağlıklı"))
    except Exception as exc:
        rows.append(_local_row("SQLite", "HATA", str(exc)))

    try:
        cache_status = cache_engine.status()
        cache_count = int(len(cache_status)) if cache_status is not None else 0
        rows.append(_local_row("Cache", "OK", f"{cache_count} cache kaydı", cache_count))
    except Exception as exc:
        rows.append(_local_row("Cache", "HATA", str(exc)))

    return rows
