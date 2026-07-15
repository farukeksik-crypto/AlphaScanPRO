from __future__ import annotations

import pandas as pd
import streamlit as st

from engine.relative_strength_engine import scan_relative_strength


def _style_status(value: str) -> str:
    styles = {
        "BIST düşerken yükseliyor": "background-color:#00e676;color:black",
        "BIST yükselirken düşüyor": "background-color:#f44336;color:white",
        "BIST'ten daha az düşüyor": "background-color:#8bc34a;color:black",
        "BIST'ten daha fazla düşüyor": "background-color:#d32f2f;color:white",
        "BIST'ten daha fazla yükseliyor": "background-color:#00bcd4;color:black",
        "BIST'ten daha az yükseliyor": "background-color:#ffb300;color:black",
        "Yükseliyor": "background-color:#4caf50;color:white",
        "Düşüyor": "background-color:#e53935;color:white",
        "Yatay": "background-color:#757575;color:white",
    }
    return styles.get(value, "")


def render_relative_strength(data_engine, watchlists):
    st.title("⚖️ Arındırma 0 Göreceli Güç")

    items = watchlists.get("arindirma_0", [])

    if not items:
        st.warning("Arındırma 0 listesi boş.")
        return

    col1, col2, col3 = st.columns(3)

    with col1:
        interval_label = st.selectbox(
            "Zaman dilimi",
            options=["15 Dakika", "1 Saat", "1 Gün"],
            index=1,
        )

    interval_map = {
        "15 Dakika": "15m",
        "1 Saat": "1h",
        "1 Gün": "1d",
    }

    interval = interval_map[interval_label]

    with col2:
        workers = st.slider(
            "Paralel işçi",
            min_value=1,
            max_value=8,
            value=4,
        )

    with col3:
        force_refresh = st.checkbox(
            "Veriyi yenile",
            value=False,
        )

    if st.button(
        "Göreceli Güç Taramasını Başlat",
        type="primary",
    ):
        try:
            with st.spinner(
                f"{len(items)} hisse BIST 100 ile karşılaştırılıyor..."
            ):
                results, failures, summary = scan_relative_strength(
                    data_engine=data_engine,
                    items=items,
                    interval=interval,
                    workers=workers,
                    force_refresh=force_refresh,
                )

            st.session_state["relative_results"] = results
            st.session_state["relative_failures"] = failures
            st.session_state["relative_summary"] = summary

        except Exception as exc:
            st.error(f"Tarama başlatılamadı: {exc}")

    results = st.session_state.get("relative_results", [])
    failures = st.session_state.get("relative_failures", [])
    summary = st.session_state.get("relative_summary", {})

    if summary:
        st.subheader("Piyasa Özeti")

        metric1, metric2, metric3, metric4 = st.columns(4)

        metric1.metric(
            "BIST 100",
            f'{summary.get("benchmark_price", 0):,.2f}',
            f'%{summary.get("benchmark_change", 0):+.2f}',
        )

        metric2.metric(
            "Endeksten güçlü",
            summary.get("endeksten_guclu", 0),
        )

        metric3.metric(
            "Endeksten zayıf",
            summary.get("endeksten_zayif", 0),
        )

        if summary.get("benchmark_change", 0) < 0:
            metric4.metric(
                "BIST düşerken yükselen",
                summary.get("bist_duserken_yukselen", 0),
            )
        else:
            metric4.metric(
                "BIST yükselirken düşen",
                summary.get("bist_yukselirken_dusen", 0),
            )

    if not results:
        st.info("Henüz göreceli güç taraması yapılmadı.")
        return

    frame = pd.DataFrame(results)

    filter_option = st.radio(
        "Gösterilecek grup",
        options=[
            "Tümü",
            "BIST düşerken yükselenler",
            "BIST yükselirken düşenler",
            "Endeksten güçlüler",
            "Endeksten zayıflar",
        ],
        horizontal=True,
    )

    filtered = frame.copy()

    if filter_option == "BIST düşerken yükselenler":
        filtered = filtered[
            (filtered["BIST 100"] < 0)
            & (filtered["Hisse %"] > 0)
        ]

    elif filter_option == "BIST yükselirken düşenler":
        filtered = filtered[
            (filtered["BIST 100"] > 0)
            & (filtered["Hisse %"] < 0)
        ]

    elif filter_option == "Endeksten güçlüler":
        filtered = filtered[
            filtered["Göreceli Fark"] > 0
        ]

    elif filter_option == "Endeksten zayıflar":
        filtered = filtered[
            filtered["Göreceli Fark"] < 0
        ]

    st.subheader(f"Sonuçlar: {len(filtered)} hisse")

    if filtered.empty:
        st.info("Seçilen filtreye uygun hisse bulunamadı.")
    else:
        st.dataframe(
            filtered.style.map(
                _style_status,
                subset=["Durum"],
            ),
            width="stretch",
            hide_index=True,
        )

    if failures:
        st.warning(f"{len(failures)} hisse taranamadı.")

        st.dataframe(
            pd.DataFrame(failures),
            width="stretch",
            hide_index=True,
        )