from __future__ import annotations

import math
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from engine.performance_analytics import build_performance_report, load_trade_journal_rows
from engine.performance_center import build_performance_center_report


def _fmt_number(value: float, digits: int = 2) -> str:
    if math.isinf(value):
        return "∞"
    return f"{value:,.{digits}f}"


def _frame(items) -> pd.DataFrame:
    rows = [item.to_dict() if hasattr(item, "to_dict") else dict(item) for item in items]
    return pd.DataFrame(rows)


def render_performance_analytics(database) -> None:
    st.title("📊 Performance Center 10.40")
    st.caption("Robotun kapalı sanal işlemlerini ölçer, kazanan/kaybeden farklarını bulur ve yalnızca kanıta dayalı öneri üretir.")

    with database.connect() as connection:
        all_rows = load_trade_journal_rows(connection)

    if not all_rows:
        st.info("Henüz analiz edilecek Trade Journal PRO kaydı bulunmuyor. Robot işlem kapattıkça bu merkez otomatik dolacak.")
        return

    raw = pd.DataFrame(all_rows)
    account_options = ["Tümü"] + sorted(raw["account_id"].dropna().astype(str).unique().tolist())
    market_options = ["Tümü"] + sorted(raw["market"].dropna().astype(str).unique().tolist())

    st.subheader("Analiz kapsamı")
    f1, f2, f3, f4 = st.columns(4)
    account = f1.selectbox("Hesap", account_options)
    market = f2.selectbox("Piyasa", market_options)
    period = f3.selectbox("Dönem", ["Tüm zamanlar", "Son 7 gün", "Son 30 gün", "Son 90 gün", "Özel"])
    include_partial = f4.checkbox("Kısmi çıkışları dahil et", value=True)

    today = date.today()
    date_from = None
    date_to = None
    if period == "Son 7 gün":
        date_from = (today - timedelta(days=7)).isoformat()
    elif period == "Son 30 gün":
        date_from = (today - timedelta(days=30)).isoformat()
    elif period == "Son 90 gün":
        date_from = (today - timedelta(days=90)).isoformat()
    elif period == "Özel":
        d1, d2 = st.columns(2)
        selected_from = d1.date_input("Başlangıç", value=today - timedelta(days=30))
        selected_to = d2.date_input("Bitiş", value=today)
        date_from = selected_from.isoformat()
        date_to = f"{selected_to.isoformat()} 23:59:59"

    starting_equity = st.number_input(
        "Başlangıç özkaynağı",
        min_value=0.0,
        value=0.0,
        step=1000.0,
        help="Drawdown yüzdesini sermaye bazında görmek için kullanılabilir.",
    )

    with database.connect() as connection:
        rows = load_trade_journal_rows(
            connection,
            account_id=None if account == "Tümü" else account,
            market=None if market == "Tümü" else market,
            date_from=date_from,
            date_to=date_to,
            include_partial_exits=include_partial,
        )
        report = build_performance_report(
            connection,
            account_id=None if account == "Tümü" else account,
            market=None if market == "Tümü" else market,
            date_from=date_from,
            date_to=date_to,
            include_partial_exits=include_partial,
            starting_equity=float(starting_equity),
        )

    if not rows:
        st.warning("Seçilen filtrelerde kapalı işlem bulunamadı.")
        return

    intelligence = build_performance_center_report(rows, min_sample=10)
    m = report.metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Net PnL", _fmt_number(m.net_pnl))
    c2.metric("Win Rate", f"%{m.win_rate_pct:.2f}")
    c3.metric("Profit Factor", _fmt_number(m.profit_factor))
    c4.metric("Expectancy", _fmt_number(m.expectancy))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("İşlem", m.trade_count)
    c6.metric("Max Drawdown", _fmt_number(m.max_drawdown))
    c7.metric("Max DD %", f"%{m.max_drawdown_pct:.2f}")
    c8.metric("Toplam Komisyon", _fmt_number(m.total_commission))

    tabs = st.tabs([
        "Yönetici Özeti", "Equity & Dönem", "Kazanan / Kaybeden",
        "Puan ve Risk", "Sembol & Çıkış", "Ham İşlemler"
    ])

    with tabs[0]:
        st.subheader("Kanıta dayalı öneriler")
        st.caption("Bu öneriler robot ayarlarını otomatik değiştirmez; önce backtest ve gölge test gerektirir.")
        for item in intelligence.recommendations:
            with st.container(border=True):
                st.markdown(f"**{item.severity} — {item.title}**")
                st.write(item.detail)
                st.caption(item.evidence)
                st.markdown(f"**Önerilen kontrollü adım:** {item.action}")
        st.subheader("Piyasa dağılımı")
        market_frame = pd.DataFrame(report.market_stats)
        if not market_frame.empty:
            st.dataframe(market_frame, use_container_width=True, hide_index=True)

    with tabs[1]:
        equity = pd.DataFrame(report.equity_curve)
        if not equity.empty:
            st.plotly_chart(px.line(equity, x="trade_no", y="equity", markers=True, title="Equity Curve"), use_container_width=True)
        period_name = st.radio("Dönemsel görünüm", ["Günlük", "Haftalık", "Aylık"], horizontal=True)
        period_data = {"Günlük": report.daily_pnl, "Haftalık": report.weekly_pnl, "Aylık": report.monthly_pnl}[period_name]
        period_frame = pd.DataFrame(period_data)
        if not period_frame.empty:
            st.plotly_chart(px.bar(period_frame, x="period", y="net_pnl", title=f"{period_name} Net PnL"), use_container_width=True)
            st.dataframe(period_frame, use_container_width=True, hide_index=True)

    with tabs[2]:
        comparison = _frame(intelligence.winner_loser_comparison)
        if not comparison.empty:
            st.dataframe(comparison, use_container_width=True, hide_index=True)
            melted = comparison.melt(id_vars=["group"], value_vars=["average_entry_score", "average_exit_score", "average_confirmations"], var_name="metric", value_name="value")
            st.plotly_chart(px.bar(melted, x="group", y="value", color="metric", barmode="group", title="Kazanan ve kaybeden özellik karşılaştırması"), use_container_width=True)

    with tabs[3]:
        score = _frame(intelligence.score_bands)
        risk = _frame(intelligence.risk_stats)
        holding = _frame(intelligence.holding_bands)
        decision = _frame(intelligence.decision_stats)
        strategy = _frame(intelligence.strategy_stats)
        for title, frame in [
            ("Giriş puanı bantları", score), ("Risk sınıfları", risk),
            ("Tutma süresi", holding), ("Karar türleri", decision),
            ("Strateji profilleri", strategy),
        ]:
            st.subheader(title)
            if frame.empty:
                st.info("Bu segment için veri yok.")
            else:
                st.dataframe(frame, use_container_width=True, hide_index=True)

    with tabs[4]:
        left, right = st.columns(2)
        symbols = pd.DataFrame(report.symbol_stats)
        exits = pd.DataFrame(report.exit_stats)
        with left:
            st.subheader("Sembol analizi")
            st.dataframe(symbols, use_container_width=True, hide_index=True)
        with right:
            st.subheader("Çıkış analizi")
            st.dataframe(exits, use_container_width=True, hide_index=True)

    with tabs[5]:
        raw_frame = pd.DataFrame(rows)
        st.dataframe(raw_frame, use_container_width=True, hide_index=True)
        st.download_button(
            "Filtrelenmiş işlemleri CSV indir",
            data=raw_frame.to_csv(index=False).encode("utf-8-sig"),
            file_name="alphascan_performance_10_40.csv",
            mime="text/csv",
        )
