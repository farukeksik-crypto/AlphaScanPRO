from __future__ import annotations

import math
import pandas as pd
import plotly.express as px
import streamlit as st

from engine.robot_intelligence import build_robot_intelligence_snapshot
from engine.robot_learning import build_robot_learning_report


def _fmt(value: float) -> str:
    return "∞" if math.isinf(value) else f"{value:,.2f}"


def render_robot_intelligence(database) -> None:
    st.title("🧠 Robot Intelligence Dashboard")
    st.caption("Robotun canlı durumunu, son performansını, pozisyon yükünü ve risk uyarılarını tek ekranda gösterir.")

    c1, c2, c3 = st.columns(3)
    lookback = c1.selectbox("Analiz dönemi", [7, 14, 30, 60, 90], index=2, format_func=lambda x: f"Son {x} gün")
    recent_limit = c2.selectbox("Son işlem tablosu", [10, 20, 50, 100], index=1)
    refresh = c3.button("🔄 Yenile", use_container_width=True)
    if refresh:
        st.rerun()

    with database.connect() as connection:
        snapshot = build_robot_intelligence_snapshot(connection, lookback_days=int(lookback), recent_limit=int(recent_limit))

    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Robot", "AKTİF" if snapshot.enabled else "KAPALI")
    s2.metric("Bakiye", _fmt(snapshot.balance))
    s3.metric("Günlük PnL", _fmt(snapshot.daily_profit))
    s4.metric("Toplam PnL", _fmt(snapshot.total_profit))

    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Açık Pozisyon", snapshot.open_position_count)
    p2.metric("Son Dönem Net PnL", _fmt(snapshot.recent_net_pnl))
    p3.metric("Win Rate", f"%{snapshot.recent_win_rate:.2f}")
    p4.metric("Profit Factor", _fmt(snapshot.recent_profit_factor))

    if snapshot.alerts:
        st.subheader("Uyarılar")
        for alert in snapshot.alerts:
            text = f"{alert['code']}: {alert['message']}"
            if alert["level"] == "CRITICAL": st.error(text)
            elif alert["level"] == "WARN": st.warning(text)
            else: st.info(text)

    tabs = st.tabs(["Açık Pozisyonlar", "Son İşlemler", "Sembol Zekâsı", "Çıkış Zekâsı", "Robot Öğrenme", "Yönetim Kullanımı"])
    with tabs[0]:
        frame = pd.DataFrame(snapshot.open_positions)
        st.dataframe(frame, use_container_width=True, hide_index=True) if not frame.empty else st.info("Açık pozisyon yok.")
    with tabs[1]:
        frame = pd.DataFrame(snapshot.recent_trades)
        st.dataframe(frame, use_container_width=True, hide_index=True) if not frame.empty else st.info("Son işlem kaydı yok.")
    with tabs[2]:
        frame = pd.DataFrame(snapshot.symbol_performance)
        if frame.empty: st.info("Sembol performansı için veri yok.")
        else:
            st.write(f"En iyi sembol: **{snapshot.best_symbol}** · En zayıf sembol: **{snapshot.worst_symbol}**")
            st.plotly_chart(px.bar(frame, x="symbol", y="net_pnl", title="Sembol Bazlı Net PnL"), use_container_width=True)
            st.dataframe(frame, use_container_width=True, hide_index=True)
    with tabs[3]:
        frame = pd.DataFrame(snapshot.exit_action_performance)
        if frame.empty: st.info("Çıkış analizi için veri yok.")
        else:
            st.plotly_chart(px.bar(frame, x="exit_action", y="net_pnl", title="Çıkış Kararı Bazlı Net PnL"), use_container_width=True)
            st.dataframe(frame, use_container_width=True, hide_index=True)
    with tabs[4]:
        with database.connect() as connection:
            learning = build_robot_learning_report(connection, lookback_days=int(lookback), minimum_sample=20)
        l1, l2, l3 = st.columns(3)
        l1.metric("Kapalı İşlem", learning.trade_count)
        l2.metric("Güven Eşiği", learning.minimum_sample)
        l3.metric("Öğrenme Durumu", "HAZIR" if learning.data_ready else "VERİ BİRİKİYOR")
        for recommendation in learning.recommendations:
            message = f"{recommendation.title} — {recommendation.evidence} Öneri: {recommendation.proposed_action}"
            if recommendation.priority == "UYARI": st.warning(message)
            elif recommendation.priority == "FIRSAT": st.success(message)
            else: st.info(message)
        learning_frame = pd.DataFrame([item.to_dict() for item in learning.segments])
        if learning_frame.empty:
            st.info("Öğrenme analizi için kapanmış işlem yok.")
        else:
            st.caption("Robot hiçbir ayarı otomatik değiştirmez; yalnızca kanıta dayalı öneri üretir.")
            st.dataframe(learning_frame, use_container_width=True, hide_index=True)

    with tabs[5]:
        u1, u2, u3, u4 = st.columns(4)
        u1.metric("Ortalama Bekleme", f"{snapshot.average_holding_minutes:.1f} dk")
        u2.metric("Break-even Kullanımı", f"%{snapshot.break_even_usage_pct:.1f}")
        u3.metric("Trailing Kullanımı", f"%{snapshot.trailing_usage_pct:.1f}")
        u4.metric("Kısmi Çıkış Kullanımı", f"%{snapshot.partial_exit_usage_pct:.1f}")

    st.caption(f"Son güncelleme: {snapshot.generated_at}")
