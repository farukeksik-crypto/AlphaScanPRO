import pandas as pd
import streamlit as st


def render_diagnostics(data_engine, cache_engine, database, run_diagnostics):
    st.title("🧪 AlphaScan PRO — Sistem Tanılama")
    st.caption(
        "Sprint 1 yalnız veri motoru, önbellek ve veritabanını test eder."
    )

    if st.button("Tanılama Testini Başlat", type="primary"):
        with st.spinner("Yahoo, Binance, cache ve SQLite test ediliyor..."):
            st.session_state["diagnostic_rows"] = run_diagnostics(
                data_engine,
                cache_engine,
                database,
            )

    rows = st.session_state.get("diagnostic_rows", [])
    if rows:
        frame = pd.DataFrame(rows)
        st.dataframe(frame, use_container_width=True, hide_index=True)

        ok_count = int((frame["Durum"] == "OK").sum())
        total_count = len(frame)
        if ok_count == total_count:
            st.success(f"Tüm testler başarılı: {ok_count}/{total_count}")
        else:
            st.warning(f"Başarılı test: {ok_count}/{total_count}")

    st.subheader("Yerel Cache Durumu")
    cache_frame = cache_engine.status()
    if cache_frame.empty:
        st.info("Henüz cache dosyası oluşmadı.")
    else:
        st.dataframe(cache_frame, use_container_width=True, hide_index=True)
