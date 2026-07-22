from __future__ import annotations

import math

import pandas as pd
import plotly.express as px
import streamlit as st

from engine.performance_analytics import build_performance_report, load_trade_journal_rows


def _fmt_number(value: float, digits: int = 2) -> str:
    if math.isinf(value):
        return "∞"
    return f"{value:,.{digits}f}"


def render_performance_analytics(database) -> None:
    st.title("📊 Performance Analytics PRO")
    st.caption("Trade Journal PRO kayıtlarından gerçek robot performansını ölçer.")

    with database.connect() as connection:
        rows = load_trade_journal_rows(connection)

    if not rows:
        st.info("Henüz analiz edilecek Trade Journal PRO kaydı bulunmuyor.")
        return

    frame = pd.DataFrame(rows)
    account_options = ["Tümü"] + sorted(frame["account_id"].dropna().astype(str).unique().tolist())
    market_options = ["Tümü"] + sorted(frame["market"].dropna().astype(str).unique().tolist())

    f1, f2, f3 = st.columns(3)
    account = f1.selectbox("Hesap", account_options)
    market = f2.selectbox("Piyasa", market_options)
    include_partial = f3.checkbox("Kısmi çıkışları dahil et", value=True)

    starting_equity = st.number_input(
        "Başlangıç özkaynağı",
        min_value=0.0,
        value=0.0,
        step=1000.0,
        help="Drawdown yüzdesini sermaye bazında görmek için kullanılabilir.",
    )

    with database.connect() as connection:
        report = build_performance_report(
            connection,
            account_id=None if account == "Tümü" else account,
            market=None if market == "Tümü" else market,
            include_partial_exits=include_partial,
            starting_equity=float(starting_equity),
        )

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

    tab_equity, tab_period, tab_symbols, tab_exits = st.tabs(
        ["Equity Curve", "Dönemsel PnL", "Sembol Analizi", "Çıkış Analizi"]
    )

    with tab_equity:
        equity = pd.DataFrame(report.equity_curve)
        if not equity.empty:
            fig = px.line(equity, x="trade_no", y="equity", markers=True, title="Equity Curve")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(equity, use_container_width=True, hide_index=True)

    with tab_period:
        period_name = st.radio("Dönem", ["Günlük", "Haftalık", "Aylık"], horizontal=True)
        data = {
            "Günlük": report.daily_pnl,
            "Haftalık": report.weekly_pnl,
            "Aylık": report.monthly_pnl,
        }[period_name]
        period_frame = pd.DataFrame(data)
        if period_frame.empty:
            st.info("Seçilen dönem için veri yok.")
        else:
            fig = px.bar(period_frame, x="period", y="net_pnl", title=f"{period_name} Net PnL")
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(period_frame, use_container_width=True, hide_index=True)

    with tab_symbols:
        symbols = pd.DataFrame(report.symbol_stats)
        if symbols.empty:
            st.info("Sembol analizi için veri yok.")
        else:
            st.subheader("En iyi / en kötü semboller")
            st.dataframe(symbols, use_container_width=True, hide_index=True)

    with tab_exits:
        exits = pd.DataFrame(report.exit_stats)
        if exits.empty:
            st.info("Çıkış analizi için veri yok.")
        else:
            st.dataframe(exits, use_container_width=True, hide_index=True)
