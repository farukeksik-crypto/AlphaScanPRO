import pandas as pd
import streamlit as st

from engine.scanner import scan_commodities, scan_crypto, scan_yahoo_items


def _style_decision(value):
    colors = {
        "NET AL": "background-color:#00e676;color:black",
        "AL ADAY": "background-color:#00bcd4;color:black",
        "IZLE": "background-color:#ffb300;color:black",
        "BEKLE": "background-color:#757575;color:white",
        "YETERSIZ VERI": "background-color:#f44336;color:white",
    }
    return colors.get(value, "")


def render_bist(data_engine, watchlists):
    st.title("📈 Arındırma 0 Tarama")
    items = watchlists.get("arindirma_0", [])

    if not items:
        st.warning("Arındırma 0 listesi boş.")
        return

    workers = st.slider("Paralel işçi", 1, 8, 4)

    if st.button("Arındırma 0 Taramasını Başlat", type="primary"):
        with st.spinner(f"{len(items)} hisse taranıyor..."):
            results, failures = scan_yahoo_items(data_engine, items, workers)
        st.session_state["s2_bist_results"] = results
        st.session_state["s2_bist_failures"] = failures

    results = st.session_state.get("s2_bist_results", [])
    failures = st.session_state.get("s2_bist_failures", [])

    if results:
        frame = pd.DataFrame(results)
        st.dataframe(
            frame.style.map(_style_decision, subset=["Karar"]),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Henüz tarama yapılmadı.")

    if failures:
        st.warning(f"{len(failures)} hisse taranamadı.")
        st.dataframe(pd.DataFrame(failures), use_container_width=True, hide_index=True)


def render_crypto(data_engine):
    st.title("₿ Kripto Tarama")

    pairs = {
        "BTC": "BTC/USDT",
        "ETH": "ETH/USDT",
        "SOL": "SOL/USDT",
        "BNB": "BNB/USDT",
        "LINK": "LINK/USDT",
        "XRP": "XRP/USDT",
        "ADA": "ADA/USDT",
        "AVAX": "AVAX/USDT",
        "DOGE": "DOGE/USDT",
        "DOT": "DOT/USDT",
    }

    if st.button("Kripto Taramasını Başlat", type="primary"):
        with st.spinner(f"{len(pairs)} coin taranıyor..."):
            rows, failures = scan_crypto(data_engine, pairs)
        st.session_state["s2_crypto_results"] = rows
        st.session_state["s2_crypto_failures"] = failures

    rows = st.session_state.get("s2_crypto_results", [])
    failures = st.session_state.get("s2_crypto_failures", [])

    if rows:
        frame = pd.DataFrame(rows)
        st.dataframe(
            frame.style.map(_style_decision, subset=["Karar"]),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Henüz kripto taraması yapılmadı.")

    if failures:
        st.warning(f"{len(failures)} coin taranamadı.")
        st.dataframe(pd.DataFrame(failures), use_container_width=True, hide_index=True)


def render_commodity(data_engine):
    st.title("🥇 Emtia Tarama")

    symbols = {
        "Altın": "GC=F",
        "Gümüş": "SI=F",
        "WTI Petrol": "CL=F",
        "Brent Petrol": "BZ=F",
        "Bakır": "HG=F",
        "Doğalgaz": "NG=F",
    }

    if st.button("Emtia Taramasını Başlat", type="primary"):
        with st.spinner(f"{len(symbols)} emtia taranıyor..."):
            rows, failures = scan_commodities(data_engine, symbols)
        st.session_state["s2_commodity_results"] = rows
        st.session_state["s2_commodity_failures"] = failures

    rows = st.session_state.get("s2_commodity_results", [])
    failures = st.session_state.get("s2_commodity_failures", [])

    if rows:
        frame = pd.DataFrame(rows)
        st.dataframe(
            frame.style.map(_style_decision, subset=["Karar"]),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Henüz emtia taraması yapılmadı.")

    if failures:
        st.warning(f"{len(failures)} emtia taranamadı.")
        st.dataframe(pd.DataFrame(failures), use_container_width=True, hide_index=True)
