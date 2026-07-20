from __future__ import annotations

import platform
import sys
from datetime import datetime

import pandas as pd
import streamlit as st


OK_STATUSES = {"OK"}
WARNING_STATUSES = {"UYARI", "YETERSİZ MUM", "ESKİ VERİ"}
ERROR_STATUSES = {"HATA", "VERİ YOK"}


def _to_timestamp(value):
    try:
        ts = pd.Timestamp(value)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
        return ts
    except Exception:
        return pd.NaT


def _cache_view(cache_frame: pd.DataFrame) -> pd.DataFrame:
    if cache_frame.empty:
        return cache_frame

    view = cache_frame.copy()
    now = pd.Timestamp.now(tz="UTC")

    if "last_bar" in view.columns:
        last_ts = view["last_bar"].apply(_to_timestamp)
        age_hours = (now - last_ts).dt.total_seconds() / 3600
        view["cache_age"] = age_hours.apply(
            lambda h: "—" if pd.isna(h) else (f"{h:.1f} saat" if h < 48 else f"{h / 24:.1f} gün")
        )

        def freshness(row):
            age = age_hours.loc[row.name]
            if pd.isna(age):
                return "VERİ YOK"
            interval = str(row.get("interval", "")).lower()
            provider = str(row.get("provider", "")).lower()
            if interval.endswith("h"):
                return "GÜNCEL" if age <= 3 else "ESKİ"
            if interval == "1d":
                return "GÜNCEL" if age <= (96 if provider == "yahoo" else 48) else "ESKİ"
            return "GÜNCEL" if age <= 96 else "ESKİ"

        view["tazelik"] = view.apply(freshness, axis=1)

    if "rows" in view.columns:
        rows_numeric = pd.to_numeric(view["rows"], errors="coerce").fillna(0)
        view["mum_yeterliliği"] = rows_numeric.apply(
            lambda n: "HAZIR" if n >= 220 else f"YETERSİZ ({int(n)}/220)"
        )

    return view


def _style_status(value: str) -> str:
    value = str(value)
    if value in OK_STATUSES or value == "GÜNCEL" or value == "HAZIR":
        return "background-color:#1b5e20;color:white;font-weight:bold"
    if value in WARNING_STATUSES or value in {"ESKİ"} or value.startswith("YETERSİZ"):
        return "background-color:#f9a825;color:black;font-weight:bold"
    if value in ERROR_STATUSES:
        return "background-color:#b71c1c;color:white;font-weight:bold"
    return ""


def render_diagnostics(data_engine, cache_engine, database, run_diagnostics):
    st.title("🧪 Sistem Sağlığı ve Tanılama Merkezi")
    st.caption(
        "Veri kaynakları, veri tazeliği, mum yeterliliği, cache, SQLite ve veri kalitesi denetlenir."
    )

    action1, action2 = st.columns([1, 3])
    run_clicked = action1.button("Tanılama Testini Başlat", type="primary", use_container_width=True)
    action2.info("Bu test işlem kayıtlarını veya strateji ayarlarını değiştirmez.")

    if run_clicked:
        with st.spinner("Yahoo, Binance, veri kalitesi, cache ve SQLite test ediliyor..."):
            st.session_state["diagnostic_rows"] = run_diagnostics(
                data_engine,
                cache_engine,
                database,
            )
            st.session_state["diagnostic_last_run"] = datetime.now().isoformat(timespec="seconds")

    rows = st.session_state.get("diagnostic_rows", [])

    if not rows:
        st.info("Tanılama henüz çalıştırılmadı. Yukarıdaki düğmeye bas.")
    else:
        frame = pd.DataFrame(rows)
        status = frame.get("Durum", pd.Series(dtype=str)).astype(str)
        ok_count = int(status.isin(OK_STATUSES).sum())
        warning_count = int(status.isin(WARNING_STATUSES).sum())
        error_count = int(status.isin(ERROR_STATUSES).sum())
        total_count = len(frame)
        health_score = round(max(0.0, (ok_count + warning_count * 0.5) / max(1, total_count) * 100), 1)

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Sistem Sağlığı", f"{health_score:.1f}/100")
        c2.metric("Başarılı", ok_count)
        c3.metric("Uyarı", warning_count)
        c4.metric("Kritik", error_count)
        c5.metric("Son Test", st.session_state.get("diagnostic_last_run", "—").replace("T", " "))

        display_columns = [
            "Test", "Sağlayıcı", "Durum", "Mum", "Gerekli Mum", "Yeterlilik %",
            "Son Mum", "Veri Yaşı", "Zaman Dilimi", "Kalite", "Uyarı", "Hata",
        ]
        display_columns = [column for column in display_columns if column in frame.columns]
        table = frame[display_columns].copy()

        styler = table.style
        if "Durum" in table.columns:
            styler = styler.map(_style_status, subset=["Durum"])
        if "Yeterlilik %" in table.columns:
            styler = styler.format({"Yeterlilik %": "{:.1f}"})

        st.dataframe(styler, width="stretch", hide_index=True)

        warnings = frame[~status.isin(OK_STATUSES)]
        if warnings.empty:
            st.success(f"Tüm testler başarılı: {ok_count}/{total_count}")
        else:
            st.warning(f"{len(warnings)} test dikkat gerektiriyor.")
            for _, row in warnings.iterrows():
                message = row.get("Uyarı") or row.get("Hata") or "Kontrol gerekli."
                st.write(f"• **{row.get('Test', 'Bilinmeyen')} — {row.get('Durum', 'UYARI')}:** {message}")

    st.subheader("Yerel Cache Durumu")
    try:
        cache_frame = cache_engine.status()
    except Exception as exc:
        st.error(f"Cache durumu okunamadı: {exc}")
        cache_frame = pd.DataFrame()

    if cache_frame.empty:
        st.info("Henüz cache dosyası oluşmadı.")
    else:
        cache_display = _cache_view(cache_frame)
        cache_styler = cache_display.style
        for column in ["tazelik", "mum_yeterliliği"]:
            if column in cache_display.columns:
                cache_styler = cache_styler.map(_style_status, subset=[column])
        st.dataframe(cache_styler, width="stretch", hide_index=True)

        stale_count = int((cache_display.get("tazelik", pd.Series(dtype=str)) == "ESKİ").sum())
        insufficient_count = int(
            cache_display.get("mum_yeterliliği", pd.Series(dtype=str)).astype(str).str.startswith("YETERSİZ").sum()
        )
        cc1, cc2, cc3 = st.columns(3)
        cc1.metric("Cache Kaydı", len(cache_display))
        cc2.metric("Eski Veri", stale_count)
        cc3.metric("Yetersiz Mum", insufficient_count)

    with st.expander("Sistem Bilgileri"):
        info = pd.DataFrame(
            [
                {"Bileşen": "Python", "Değer": sys.version.split()[0]},
                {"Bileşen": "İşletim Sistemi", "Değer": platform.platform()},
                {"Bileşen": "Makine", "Değer": platform.machine()},
                {"Bileşen": "Streamlit", "Değer": st.__version__},
            ]
        )
        st.dataframe(info, width="stretch", hide_index=True)

    st.caption("Diagnostics PRO v1 — Güvenli sağlık kontrolü; otomatik veri silme veya strateji değiştirme yapmaz.")
