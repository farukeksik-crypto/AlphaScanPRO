from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st


ISTANBUL_TZ = ZoneInfo("Europe/Istanbul")
STARTING_BALANCE = 1_000_000.0


def _market_status(now: datetime) -> tuple[str, str]:
    """
    Hafta içi 10:00–18:00 aralığını BIST seansı olarak gösterir.
    Resmî tatil kontrolü sonraki sürümde eklenecektir.
    """

    if now.weekday() >= 5:
        return "Kapalı", "Hafta sonu"

    current_time = now.time()

    if current_time < time(10, 0):
        return "Kapalı", "Seans öncesi"

    if current_time <= time(18, 0):
        return "Açık", "Normal seans"

    return "Kapalı", "Seans sona erdi"


def _get_scan_summary() -> dict[str, int]:
    results = st.session_state.get("s2_bist_results", [])

    summary = {
        "NET AL": 0,
        "AL ADAY": 0,
        "IZLE": 0,
        "BEKLE": 0,
        "YETERSIZ VERI": 0,
    }

    for row in results:
        decision = row.get("Karar", "YETERSIZ VERI")

        if decision in summary:
            summary[decision] += 1

    return summary


def _get_top_opportunities(limit: int = 10) -> pd.DataFrame:
    results = st.session_state.get("s2_bist_results", [])

    if not results:
        return pd.DataFrame()

    frame = pd.DataFrame(results)

    if "Puan" not in frame.columns:
        return pd.DataFrame()

    frame = frame.sort_values(
        by="Puan",
        ascending=False,
    ).head(limit)

    preferred_columns = [
        "Kod",
        "Hisse",
        "Karar",
        "Kalite",
        "Puan",
        "Fiyat",
        "Stop",
        "Hedef 1",
        "Hedef 2",
        "R/K 2",
    ]

    available_columns = [
        column
        for column in preferred_columns
        if column in frame.columns
    ]

    return frame[available_columns]


def _get_last_scan_time() -> str:
    scan_time = st.session_state.get("last_scan_time")

    if scan_time:
        return str(scan_time)

    if st.session_state.get("s2_bist_results"):
        return "Bu oturumda tarama yapıldı"

    return "Henüz tarama yok"


def render_dashboard(cache_engine):
    now = datetime.now(ISTANBUL_TZ)
    market_status, market_detail = _market_status(now)

    cache_status = cache_engine.status()
    scan_summary = _get_scan_summary()
    relative_summary = st.session_state.get("relative_summary", {})

    portfolio_balance = st.session_state.get(
        "paper_portfolio_balance",
        STARTING_BALANCE,
    )

    daily_profit = st.session_state.get(
        "paper_daily_profit",
        0.0,
    )

    open_positions = st.session_state.get(
        "paper_open_positions",
        [],
    )

    robot_status = st.session_state.get(
        "paper_robot_status",
        "Beklemede",
    )

    st.title("🏠 AlphaScan PRO Dashboard")

    st.caption(
        f"Son ekran yenileme: {now.strftime('%d.%m.%Y %H:%M:%S')}"
    )

    # Tarih, saat ve sistem durumu
    date_col, time_col, market_col, system_col = st.columns(4)

    date_col.metric(
        "📅 Tarih",
        now.strftime("%d.%m.%Y"),
    )

    time_col.metric(
        "🕐 Saat",
        now.strftime("%H:%M:%S"),
    )

    market_col.metric(
        "📊 BIST",
        market_status,
        market_detail,
    )

    system_col.metric(
        "⚙️ Sistem",
        "Aktif",
        f"{len(cache_status)} cache kaydı",
    )

    st.divider()

    # Sanal portföy
    st.subheader("💰 Sanal İşlem Robotu")

    portfolio_col, profit_col, position_col, robot_col = st.columns(4)

    portfolio_col.metric(
        "Sanal bakiye",
        f"{portfolio_balance:,.2f} TL",
    )

    profit_col.metric(
        "Bugünkü sonuç",
        f"{daily_profit:,.2f} TL",
        f"%{(daily_profit / STARTING_BALANCE) * 100:+.2f}",
    )

    position_col.metric(
        "Açık pozisyon",
        len(open_positions),
    )

    robot_col.metric(
        "Robot",
        robot_status,
    )

    st.info(
        "Robot şu anda gerçek emir göndermez. "
        "1.000.000 TL sanal bakiyeyle test edilmek üzere hazırlanacaktır."
    )

    st.divider()

    # Arındırma 0 tarama özeti
    st.subheader("📈 Arındırma 0 Tarama Özeti")

    net_col, candidate_col, watch_col, wait_col = st.columns(4)

    net_col.metric(
        "NET AL",
        scan_summary["NET AL"],
    )

    candidate_col.metric(
        "AL ADAY",
        scan_summary["AL ADAY"],
    )

    watch_col.metric(
        "İZLE",
        scan_summary["IZLE"],
    )

    wait_col.metric(
        "BEKLE",
        scan_summary["BEKLE"],
    )

    st.caption(f"Son tarama: {_get_last_scan_time()}")

    st.divider()

    # Göreceli güç özeti
    st.subheader("⚖️ BIST 100 Göreceli Güç")

    relative_col1, relative_col2, relative_col3, relative_col4 = st.columns(4)

    relative_col1.metric(
        "BIST 100 değişim",
        f'%{relative_summary.get("benchmark_change", 0):+.2f}',
    )

    relative_col2.metric(
        "Endeksten güçlü",
        relative_summary.get("endeksten_guclu", 0),
    )

    relative_col3.metric(
        "Endeksten zayıf",
        relative_summary.get("endeksten_zayif", 0),
    )

    benchmark_change = relative_summary.get("benchmark_change", 0)

    if benchmark_change < 0:
        relative_col4.metric(
            "BIST düşerken yükselen",
            relative_summary.get("bist_duserken_yukselen", 0),
        )
    else:
        relative_col4.metric(
            "BIST yükselirken düşen",
            relative_summary.get("bist_yukselirken_dusen", 0),
        )

    if not relative_summary:
        st.caption(
            "Göreceli Güç ekranında tarama yapıldığında sonuçlar burada görünür."
        )

    st.divider()

    # En güçlü fırsatlar
    st.subheader("🔥 Günün En Güçlü Fırsatları")

    top_opportunities = _get_top_opportunities(limit=10)

    if top_opportunities.empty:
        st.info(
            "Arındırma 0 taraması yapıldığında en yüksek puanlı hisseler "
            "burada listelenecek."
        )
    else:
        st.dataframe(
            top_opportunities,
            width="stretch",
            hide_index=True,
        )

    st.divider()

    st.subheader("🧭 Geliştirme Durumu")

    st.markdown(
        """
        - ✅ Arındırması %0 hisse taraması
        - ✅ Skor ve sinyal motoru
        - ✅ Stop, iki hedef ve risk/kazanç
        - ✅ BIST 100 göreceli güç analizi
        - 🔄 Gün içi çoklu zaman dilimi stratejisi
        - ⏳ TradingView benzeri gelişmiş grafik
        - ⏳ 1.000.000 TL sanal işlem robotu
        - ⏳ Tarih aralıklı geçmiş strateji testi
        - ⏳ Gün sonu robot performans raporu
        """
    )