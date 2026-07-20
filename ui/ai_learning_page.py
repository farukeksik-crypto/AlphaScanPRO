from __future__ import annotations

import pandas as pd
import streamlit as st

from engine.ai.learning_engine import analyze_learning
from engine.robot_engine import RobotEngine


def _render_learning_table(title: str, frame: pd.DataFrame):
    if frame is None or frame.empty:
        return

    st.subheader(title)

    formats = {
        "Toplam_KZ": "{:+,.2f}",
        "Ortalama_KZ": "{:+,.2f}",
        "Medyan_KZ": "{:+,.2f}",
        "Komisyon": "{:,.2f}",
        "Başarı_Oranı": "{:.2f}%",
        "Kâr_Faktörü": "{:.2f}",
    }

    st.dataframe(
        frame.style.format(
            {
                key: value
                for key, value in formats.items()
                if key in frame.columns
            },
            na_rep="—",
        ),
        width="stretch",
        hide_index=True,
    )


def render_ai_learning(database):
    st.title("🧠 AI Öğrenme")

    st.caption(
        "Bu ekran kapanmış sanal robot işlemlerinden öğrenir. "
        "Öneriler otomatik uygulanmaz; Backtest PRO ve Strategy Lab ile doğrulanır."
    )

    robot = RobotEngine(database)
    history = robot.get_trade_history(limit=10_000)
    analysis = analyze_learning(history)

    learning_score = float(analysis.get("learning_score", 0))
    sample_status = str(analysis.get("sample_status", "Veri yok"))
    closed_trades = int(analysis.get("closed_trades", 0))

    c1, c2, c3 = st.columns(3)
    c1.metric("Öğrenme Puanı", f"{learning_score:.1f} / 100")
    c2.metric("Veri Yeterliliği", sample_status)
    c3.metric("Kapanmış İşlem", closed_trades)

    if learning_score >= 75:
        st.success("Öğrenme verisi güçlü.")
    elif learning_score >= 40:
        st.warning("Öğrenme verisi sınırlı.")
    else:
        st.info("Daha fazla kapanmış sanal işlem gerekir.")

    insights = analysis.get("insights", [])
    recommendations = analysis.get("recommendations", [])

    if insights:
        st.subheader("Sistemin Öğrendikleri")
        for item in insights:
            st.markdown(f"- {item}")

    if recommendations:
        st.subheader("Doğrulanması Gereken Öneriler")
        st.info("\n".join(f"- {item}" for item in recommendations))

    tables = analysis.get("tables", {})

    st.divider()

    table_map = [
        ("Güven Puanı Öğrenmesi", "confidence_bands"),
        ("Teknik Puan Öğrenmesi", "score_bands"),
        ("Piyasa Bazlı Öğrenme", "by_market"),
        ("Evren Bazlı Öğrenme", "by_universe"),
        ("Strateji Profili Öğrenmesi", "by_profile"),
        ("Varlık Bazlı Öğrenme", "by_symbol"),
        ("Çıkış Nedeni Öğrenmesi", "by_exit_reason"),
        ("Haftanın Günü Analizi", "by_weekday"),
        ("Saat Bazlı Analiz", "by_hour"),
        ("Aylık Öğrenme", "by_month"),
    ]

    for title, key in table_map:
        _render_learning_table(title, tables.get(key))

    sales = analysis.get("sales", pd.DataFrame())

    if not sales.empty:
        st.divider()
        st.subheader("Öğrenme Veri Seti")

        display_sales = sales.rename(
            columns={
                "id": "ID",
                "symbol": "Kod",
                "side": "İşlem",
                "quantity": "Miktar",
                "price": "Fiyat",
                "commission": "Komisyon",
                "profit": "Kâr/Zarar",
                "created_at": "Tarih",
                "market": "Piyasa",
                "universe": "Evren",
                "technical_score": "Teknik Puan",
                "confidence_score": "Güven",
                "confidence_label": "Güven Durumu",
                "decision": "Karar",
                "reason": "Çıkış Nedeni",
                "strategy_profile": "Strateji Profili",
                "weekday": "Gün",
                "hour": "Saat",
                "month": "Ay",
            }
        )

        st.dataframe(
            display_sales.style.format(
                {
                    "Miktar": "{:,.4f}",
                    "Fiyat": "{:,.4f}",
                    "Komisyon": "{:,.2f}",
                    "Kâr/Zarar": "{:+,.2f}",
                    "Teknik Puan": "{:.1f}",
                    "Güven": "{:.1f}",
                },
                na_rep="—",
            ),
            width="stretch",
            hide_index=True,
        )

        csv_data = display_sales.to_csv(index=False).encode("utf-8-sig")

        st.download_button(
            "AI Öğrenme Verisini CSV İndir",
            data=csv_data,
            file_name="alphascan_ai_learning.csv",
            mime="text/csv",
        )