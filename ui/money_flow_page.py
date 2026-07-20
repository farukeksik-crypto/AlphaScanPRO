from __future__ import annotations

import pandas as pd
import streamlit as st


def _flow_score(frame: pd.DataFrame) -> float:
    if frame.empty:
        return 0.0
    score = frame["score"].fillna(0).clip(0, 100)
    confidence = frame["confidence"].fillna(0).clip(0, 100)
    decision_bonus = frame["decision"].map({"NET AL": 15, "AL ADAY": 8, "İZLE": 2, "IZLE": 2, "BEKLE": -5}).fillna(0)
    return float((score * 0.55 + confidence * 0.30 + decision_bonus).mean())


def _label(value: float) -> str:
    if value >= 70:
        return "Güçlü para girişi"
    if value >= 55:
        return "Para girişi"
    if value >= 40:
        return "Nötr"
    if value >= 25:
        return "Para çıkışı"
    return "Güçlü para çıkışı"


def render_money_flow(database):
    st.title("💸 Paranın Yönü")
    st.caption(
        "Bu ilk sürüm gerçek fon girişini doğrudan ölçmez; son taramalardaki teknik puan, güven, "
        "karar ve risk verilerinden sermaye yönü için bir gösterge üretir."
    )

    with database.connect() as connection:
        frame = pd.read_sql_query(
            """
            SELECT r.market, r.universe, r.symbol, r.name, r.decision, r.score,
                   r.confidence, r.risk_level, r.probability, r.created_at
            FROM background_scan_results r
            JOIN (
                SELECT market, MAX(run_id) AS run_id
                FROM background_scan_results
                GROUP BY market
            ) x ON x.market = r.market AND x.run_id = r.run_id
            """,
            connection,
        )

    if frame.empty:
        st.info("Paranın yönünü hesaplamak için Background Worker'ın en az bir tarama yapması gerekiyor.")
        return

    frame["market"] = frame["market"].astype(str).str.upper().replace({"KRİPTO": "KRIPTO", "EMTİA": "EMTIA"})
    markets = [("BIST", "BIST"), ("KRIPTO", "Kripto"), ("EMTIA", "Emtia")]
    cols = st.columns(3)
    summaries = []
    for col, (market, title) in zip(cols, markets):
        part = frame[frame["market"] == market]
        value = _flow_score(part)
        summaries.append((market, title, value, len(part)))
        col.metric(title, f"{value:.1f}/100", _label(value))

    ranked = sorted(summaries, key=lambda item: item[2], reverse=True)
    if ranked:
        st.success(f"Göreceli olarak para yönünün en güçlü olduğu piyasa: **{ranked[0][1]}**")

    st.divider()
    selected = st.selectbox("Detay piyasa", [m[0] for m in markets], format_func=dict(markets).get)
    detail = frame[frame["market"] == selected].copy()
    if detail.empty:
        st.warning("Bu piyasa için son tarama verisi yok.")
        return

    detail["Akış Puanı"] = (
        detail["score"].fillna(0) * 0.55
        + detail["confidence"].fillna(0) * 0.30
        + detail["decision"].map({"NET AL": 15, "AL ADAY": 8, "İZLE": 2, "IZLE": 2, "BEKLE": -5}).fillna(0)
    )
    detail = detail.sort_values("Akış Puanı", ascending=False)
    display = detail.rename(columns={
        "symbol": "Kod", "name": "Ad", "decision": "Karar", "score": "Teknik Puan",
        "confidence": "Güven", "risk_level": "Risk", "probability": "Başarı %", "universe": "Evren",
    })
    st.subheader("En güçlü para yönü adayları")
    st.dataframe(
        display[[c for c in ["Kod", "Ad", "Evren", "Karar", "Teknik Puan", "Güven", "Risk", "Başarı %", "Akış Puanı"] if c in display.columns]].head(25),
        width="stretch", hide_index=True,
    )
