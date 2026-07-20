from __future__ import annotations

import math

import pandas as pd
import streamlit as st

from engine.ai.replay_analyzer import analyze_robot_history
from engine.robot_engine import RobotEngine


def _format_profit_factor(value: float) -> str:
    return "∞" if math.isinf(value) else f"{float(value):.2f}"


def _render_performance_table(
    title: str,
    frame: pd.DataFrame,
) -> None:
    if frame is None or frame.empty:
        return

    st.subheader(title)

    formats = {
        "Toplam_KZ": "{:+,.2f}",
        "Ortalama_KZ": "{:+,.2f}",
        "Medyan_KZ": "{:+,.2f}",
        "En_İyi": "{:+,.2f}",
        "En_Kötü": "{:+,.2f}",
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


def render_robot_replay(database) -> None:
    st.title("🧠 Robot Replay PRO")

    st.caption(
        "Kapanmış sanal işlemleri analiz eder ve Backtest PRO'da "
        "doğrulanması gereken fikirler üretir. Öneriler otomatik uygulanmaz."
    )

    history = RobotEngine(database).get_trade_history(limit=10_000)

    if history.empty:
        st.info("Henüz robot işlem geçmişi bulunmuyor.")
        return

    analysis = analyze_robot_history(history)
    summary = analysis["summary"]
    calibration = analysis["calibration"]

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Kapanmış İşlem", int(summary["closed_trades"]))
    c2.metric("Başarı Oranı", f"%{summary['win_rate']:.2f}")
    c3.metric("Toplam K/Z", f"{summary['total_profit']:+,.2f} TL")
    c4.metric("Kâr Faktörü", _format_profit_factor(summary["profit_factor"]))
    c5.metric("Max Drawdown", f"{summary['max_drawdown']:+,.2f} TL")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Kazanan", int(summary["winners"]))
    c2.metric("Kaybeden", int(summary["losers"]))
    c3.metric("Ortalama K/Z", f"{summary['average_profit']:+,.2f} TL")
    c4.metric("En İyi İşlem", f"{summary['best_trade']:+,.2f} TL")
    c5.metric("En Kötü İşlem", f"{summary['worst_trade']:+,.2f} TL")

    st.subheader("Veri Kalibrasyon Durumu")
    p1, p2 = st.columns([1, 3])
    p1.metric("Seviye", calibration["level"])
    p2.progress(int(calibration["progress"]))
    p2.caption(calibration["message"])

    warnings = analysis.get("warnings", [])
    recommendations = analysis.get("recommendations", [])

    if warnings:
        st.warning(
            "**Replay uyarıları**\n\n"
            + "\n".join(f"- {item}" for item in warnings)
        )

    if recommendations:
        st.info(
            "**Backtest'te denenmesi önerilen fikirler**\n\n"
            + "\n".join(f"- {item}" for item in recommendations)
            + "\n\nBu öneriler otomatik olarak robot ayarını değiştirmez."
        )

    curve = analysis.get("equity_curve", pd.DataFrame())

    if not curve.empty:
        st.subheader("Robot Kümülatif Kâr/Zarar Eğrisi")
        chart = curve.set_index("İşlem")[["Kümülatif K/Z"]]
        st.line_chart(chart, height=320)

        st.subheader("Robot Drawdown Eğrisi")
        drawdown = curve.set_index("İşlem")[["Drawdown"]]
        st.line_chart(drawdown, height=260)

    st.divider()

    _render_performance_table(
        "Aylık Performans",
        analysis.get("monthly"),
    )
    _render_performance_table(
        "Haftalık Performans",
        analysis.get("weekly"),
    )
    _render_performance_table(
        "Piyasa Bazlı Performans",
        analysis.get("by_market"),
    )
    _render_performance_table(
        "Evren Bazlı Performans",
        analysis.get("by_universe"),
    )
    _render_performance_table(
        "Strateji Profili Bazlı Performans",
        analysis.get("by_profile"),
    )
    _render_performance_table(
        "Varlık Bazlı Performans",
        analysis.get("by_symbol"),
    )
    _render_performance_table(
        "Çıkış Nedeni Analizi",
        analysis.get("by_exit_reason"),
    )
    _render_performance_table(
        "Güven Aralığı Analizi",
        analysis.get("confidence_bands"),
    )
    _render_performance_table(
        "Teknik Puan Aralığı Analizi",
        analysis.get("score_bands"),
    )

    st.divider()
    st.subheader("Kapanmış İşlem Kayıtları")

    sales = analysis.get("sales", pd.DataFrame())

    if sales.empty:
        st.info("Henüz kapanmış işlem bulunmuyor.")
        return

    display_sales = sales.rename(
        columns={
            "id": "ID",
            "symbol": "Kod",
            "side": "İşlem",
            "quantity": "Miktar",
            "price": "Çıkış Fiyatı",
            "commission": "Komisyon",
            "profit": "Kâr/Zarar",
            "created_at": "Tarih",
            "market": "Piyasa",
            "universe": "Evren",
            "technical_score": "Teknik Puan",
            "confidence_score": "Güven",
            "confidence_label": "Güven Durumu",
            "decision": "Karar",
            "reason": "AI Analizi / Çıkış Nedeni",
            "strategy_profile": "Strateji Profili",
            "position_id": "Pozisyon ID",
        }
    )

    st.dataframe(
        display_sales.style.format(
            {
                "Miktar": "{:,.4f}",
                "Çıkış Fiyatı": "{:,.4f}",
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

    st.download_button(
        "Replay Raporunu CSV İndir",
        data=display_sales.to_csv(index=False).encode("utf-8-sig"),
        file_name="alphascan_robot_replay_pro.csv",
        mime="text/csv",
    )
