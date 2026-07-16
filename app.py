from __future__ import annotations

import streamlit as st

from config.settings import CACHE_DIR, DATABASE_FILE, load_watchlists
from database.db import Database
from engine.cache_engine import CacheEngine
from engine.data_engine import DataEngine
from engine.diagnostics import run_diagnostics
from ui.backtest_page import render_backtest
from ui.dashboard_page import render_dashboard
from ui.diagnostics_page import render_diagnostics
from ui.relative_strength_page import render_relative_strength
from ui.scanner_pages import render_bist, render_commodity, render_crypto


st.set_page_config(
    page_title="AlphaScan PRO",
    page_icon="📈",
    layout="wide",
)


cache_engine = CacheEngine(CACHE_DIR)
data_engine = DataEngine(cache_engine)
database = Database(DATABASE_FILE)
watchlists = load_watchlists()


st.sidebar.title("📈 AlphaScan PRO")

page = st.sidebar.radio(
    "Panel",
    [
        "Dashboard",
        "Arındırma 0",
        "Göreceli Güç",
        "Kripto",
        "Emtia",
        "Backtest PRO",
        "Sistem Durumu",
    ],
)


if page == "Dashboard":
    render_dashboard(cache_engine)

elif page == "Arındırma 0":
    render_bist(data_engine, watchlists)

elif page == "Göreceli Güç":
    render_relative_strength(data_engine, watchlists)

elif page == "Kripto":
    render_crypto(data_engine)

elif page == "Emtia":
    render_commodity(data_engine)

elif page == "Backtest PRO":
    render_backtest(data_engine, watchlists)

elif page == "Sistem Durumu":
    render_diagnostics(
        data_engine=data_engine,
        cache_engine=cache_engine,
        database=database,
        run_diagnostics=run_diagnostics,
    )


st.caption(
    "Sprint 3: Skor, risk, göreceli güç ve geçmiş strateji testi."
)