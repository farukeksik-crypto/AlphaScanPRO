from __future__ import annotations

import streamlit as st

from config.market_universes import get_bist_universe
from config.settings import CACHE_DIR, DATABASE_FILE, load_watchlists
from database.db import Database
from database.background_migrations import ensure_background_schema
from database.robot_migrations import migrate_database_object
from engine.cache_engine import CacheEngine
from engine.data_engine import DataEngine
from engine.diagnostics import run_diagnostics
from ui.ai_learning_page import render_ai_learning
from ui.backtest_page import render_backtest
from ui.background_page import render_background_status
from ui.dashboard_page import render_dashboard
from ui.diagnostics_page import render_diagnostics
from ui.financial_analysis_page import render_financial_analysis
from ui.advanced_chart_page import render_advanced_chart
from ui.relative_strength_page import render_relative_strength
from ui.money_flow_page import render_money_flow
from ui.robot_page import render_robot
from ui.robot_replay_page import render_robot_replay
from ui.strategy_lab_page import render_strategy_lab
from ui.glossary import render_page_glossary
from ui.scanner_pages import (
    render_bist,
    render_commodity,
    render_crypto,
    render_katilim,
    render_katilim_100,
)


st.set_page_config(
    page_title="AlphaScan PRO",
    page_icon="📈",
    layout="wide",
)


cache_engine = CacheEngine(CACHE_DIR)
data_engine = DataEngine(cache_engine)
database = Database(DATABASE_FILE)
ensure_background_schema(database)
migrate_database_object(database)
watchlists = load_watchlists()


st.sidebar.title("📈 AlphaScan PRO")

page = st.sidebar.radio(
    "Panel",
    [
        "Ana Panel",
        "Arındırma 0",
        "Katılım Tüm",
        "Katılım 100",
        "Göreceli Güç",
        "Paranın Yönü",
        "Kripto",
        "Emtia",
        "Gelişmiş Grafik",
        "Bilanço ve Yapay Zekâ Analizi",
        "Strateji Laboratuvarı",
        "Geçmiş Strateji Testi",
        "Sanal İşlem Robotu",
        "Robot İşlem Tekrarı",
        "Yapay Zekâ Öğrenme",
        "Arka Plan Platformu",
        "Sistem Durumu",
    ],
)


if page == "Ana Panel":
    render_dashboard(cache_engine, database)

elif page == "Arındırma 0":
    render_bist(data_engine, watchlists)

elif page == "Katılım Tüm":
    render_katilim(data_engine, get_bist_universe("Katılım Tüm"))

elif page == "Katılım 100":
    render_katilim_100(data_engine, get_bist_universe("Katılım 100"))

elif page == "Göreceli Güç":
    render_relative_strength(data_engine, watchlists)

elif page == "Paranın Yönü":
    render_money_flow(database)

elif page == "Kripto":
    render_crypto(data_engine)

elif page == "Emtia":
    render_commodity(data_engine)

elif page == "Gelişmiş Grafik":
    render_advanced_chart(data_engine, watchlists, database)

elif page == "Bilanço ve Yapay Zekâ Analizi":
    render_financial_analysis()

elif page == "Strateji Laboratuvarı":
    render_strategy_lab(data_engine, watchlists)

elif page == "Geçmiş Strateji Testi":
    render_backtest(data_engine, watchlists)

elif page == "Sanal İşlem Robotu":
    render_robot(database)

elif page == "Robot İşlem Tekrarı":
    render_robot_replay(database)

elif page == "Yapay Zekâ Öğrenme":
    render_ai_learning(database)

elif page == "Arka Plan Platformu":
    render_background_status(database)

elif page == "Sistem Durumu":
    render_diagnostics(
        data_engine=data_engine,
        cache_engine=cache_engine,
        database=database,
        run_diagnostics=run_diagnostics,
    )



render_page_glossary(page)

st.caption(
    "AlphaScan PRO v3.0 Sprint 1: SQLite tabanlı arka plan taraması, "
    "bağımsız sanal robot, çoklu hisse bilanço analizi ve Türkçe finansal tablolar."
)

