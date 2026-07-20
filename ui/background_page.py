from __future__ import annotations

from pathlib import Path
import sqlite3

import pandas as pd
import streamlit as st

from config.background_settings import (
    BACKGROUND_CONFIG_FILE,
    BACKGROUND_LOG_DIR,
    load_background_settings,
)
from database.background_migrations import ensure_background_schema


def _read_runs(database, limit: int = 100) -> pd.DataFrame:
    query = """
        SELECT
            id,
            market AS Piyasa,
            universe AS Evren,
            started_at AS Başlangıç,
            finished_at AS Bitiş,
            status AS Durum,
            scanned_count AS Tarama,
            failure_count AS Hata,
            action_count AS Robot_Aksiyonu,
            error_message AS Hata_Mesajı
        FROM background_runs
        ORDER BY id DESC
        LIMIT ?
    """
    with database.connect() as connection:
        return pd.read_sql_query(query, connection, params=(int(limit),))


def _read_latest_results(database, market: str, limit: int = 100) -> pd.DataFrame:
    query = """
        SELECT
            created_at AS Zaman,
            market AS Piyasa,
            universe AS Evren,
            symbol AS Kod,
            name AS Ad,
            decision AS Karar,
            score AS Puan,
            price AS Fiyat,
            confidence AS Güven,
            confidence_label AS Güven_Durumu,
            risk_level AS Risk,
            probability AS Başarı_Göstergesi,
            reason AS Neden
        FROM background_scan_results
        WHERE market = ?
        ORDER BY id DESC
        LIMIT ?
    """
    with database.connect() as connection:
        return pd.read_sql_query(
            query,
            connection,
            params=(market, int(limit)),
        )


def _tail_log(path: Path, line_count: int = 120) -> str:
    if not path.exists():
        return "Henüz arka plan logu oluşmadı."

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-line_count:])


def render_background_status(database) -> None:
    st.title("⚙️ Arka Plan Platformu")

    ensure_background_schema(database)
    settings = load_background_settings()

    st.info(
        "Bu panel arka plan worker durumunu gösterir. "
        "Worker, Streamlit kapalıyken ayrı bir Python işlemi olarak çalışır."
    )

    c1, c2, c3 = st.columns(3)
    c1.metric(
        "BIST",
        "Aktif" if settings.bist.enabled else "Kapalı",
        f"{settings.bist.interval_minutes} dk",
    )
    c2.metric(
        "Kripto",
        "Aktif" if settings.crypto.enabled else "Kapalı",
        f"{settings.crypto.interval_minutes} dk",
    )
    c3.metric(
        "Emtia",
        "Aktif" if settings.commodity.enabled else "Kapalı",
        f"{settings.commodity.interval_minutes} dk",
    )

    st.caption(
        f"Ayar dosyası: {BACKGROUND_CONFIG_FILE} | "
        f"BIST çalışma aralığı: {settings.bist_market_start}–{settings.bist_market_end}"
    )

    try:
        runs = _read_runs(database)
    except (sqlite3.Error, pd.errors.DatabaseError) as exc:
        st.error(f"Arka plan çalışma geçmişi okunamadı: {exc}")
        runs = pd.DataFrame()

    st.subheader("Son Çalışmalar")
    if runs.empty:
        st.warning(
            "Henüz arka plan taraması kaydedilmedi. "
            "background_worker.py çalıştırıldığında kayıtlar burada görünür."
        )
    else:
        last = runs.iloc[0]
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Son Piyasa", str(last["Piyasa"]))
        k2.metric("Son Durum", str(last["Durum"]))
        k3.metric("Taranan", int(last["Tarama"] or 0))
        k4.metric("Robot Aksiyonu", int(last["Robot_Aksiyonu"] or 0))
        st.dataframe(runs, width="stretch", hide_index=True, height=360)

    st.subheader("Son Tarama Sonuçları")
    market = st.radio(
        "Piyasa",
        ["BIST", "KRIPTO", "EMTIA"],
        horizontal=True,
        key="background_market",
    )
    results = _read_latest_results(database, market)
    if results.empty:
        st.info(f"{market} için kayıtlı arka plan sonucu yok.")
    else:
        st.dataframe(results, width="stretch", hide_index=True, height=440)

    st.subheader("Worker Logu")
    log_path = BACKGROUND_LOG_DIR / "background_worker.log"
    st.code(_tail_log(log_path), language="text")

    with st.expander("Başlatma ve durdurma komutları"):
        st.code(
            r"""cd C:\Users\Faruk\AlphaScanPRO_Sprint2
py -3.13 background_worker.py

# Durdurmak için worker penceresinde:
Ctrl + C

# Windows başlangıcına kurmak için:
powershell -ExecutionPolicy Bypass -File .\scripts\install_background_task.ps1

# Otomatik görevi kaldırmak için:
powershell -ExecutionPolicy Bypass -File .\scripts\remove_background_task.ps1
""",
            language="powershell",
        )
