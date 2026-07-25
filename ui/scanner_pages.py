from __future__ import annotations
from database.background_repository import latest_scan_results

from io import BytesIO

import pandas as pd
import streamlit as st

from engine.analysis_engine import analyze_signal_payload
from engine.scanner import scan_yahoo_items


def _style_decision(value: str) -> str:
    styles = {
        "NET AL": "background-color:#00e676;color:black;font-weight:bold",
        "AL ADAY": "background-color:#00bcd4;color:black;font-weight:bold",
        "IZLE": "background-color:#ffb300;color:black",
        "İZLE": "background-color:#ffb300;color:black",
        "BEKLE": "background-color:#757575;color:white",
        "YETERSIZ VERI": "background-color:#f44336;color:white",
        "YETERSİZ VERİ": "background-color:#f44336;color:white",
    }
    return styles.get(value, "")


def _style_quality(value: str) -> str:
    styles = {
        "S": "background-color:#7b1fa2;color:white;font-weight:bold",
        "A+": "background-color:#00c853;color:black;font-weight:bold",
        "A": "background-color:#64dd17;color:black",
        "B+": "background-color:#aeea00;color:black",
        "B": "background-color:#ffd600;color:black",
        "C": "background-color:#ff9100;color:black",
        "D": "background-color:#616161;color:white",
    }
    return styles.get(value, "")


def _style_confidence(value: str) -> str:
    styles = {
        "Çok Güçlü": "background-color:#7b1fa2;color:white;font-weight:bold",
        "Güçlü": "background-color:#00c853;color:black;font-weight:bold",
        "Orta": "background-color:#ffd600;color:black",
        "Zayıf": "background-color:#ff9100;color:black",
        "Riskli": "background-color:#d50000;color:white;font-weight:bold",
    }
    return styles.get(value, "")


def _style_relative(value) -> str:
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return ""

    if numeric_value >= 2:
        return "background-color:#00c853;color:black;font-weight:bold"
    if numeric_value > 0:
        return "background-color:#b9f6ca;color:black"
    if numeric_value <= -2:
        return "background-color:#d50000;color:white;font-weight:bold"
    if numeric_value < 0:
        return "background-color:#ffcdd2;color:black"
    return ""


def _alpha_score(score) -> str:
    try:
        score = float(score)
    except (TypeError, ValueError):
        return "D"

    if score >= 95:
        return "S"
    if score >= 90:
        return "A+"
    if score >= 85:
        return "A"
    if score >= 80:
        return "B+"
    if score >= 75:
        return "B"
    if score >= 70:
        return "C"
    return "D"


def _trend_stars(row: pd.Series) -> str:
    score = float(row.get("Puan", 0) or 0)
    decision = str(row.get("Karar", ""))

    if decision == "NET AL" and score >= 90:
        return "★★★★★"
    if decision == "NET AL":
        return "★★★★☆"
    if decision == "AL ADAY":
        return "★★★☆☆"
    if decision in {"IZLE", "İZLE"}:
        return "★★☆☆☆"
    return "★☆☆☆☆"


def _robot_comment(row: pd.Series) -> str:
    comments: list[str] = []

    score = float(row.get("Puan", 0) or 0)
    decision = str(row.get("Karar", ""))
    relative = row.get("Ayrışma %")
    rsi_value = row.get("RSI")
    adx_value = row.get("ADX")
    confidence = row.get("Güven")

    if decision == "NET AL":
        comments.append("Güçlü sinyal")
    elif decision == "AL ADAY":
        comments.append("Giriş onayı beklenmeli")
    elif decision in {"IZLE", "İZLE"}:
        comments.append("Takip edilmeli")
    else:
        comments.append("Bekle")

    if score >= 90:
        comments.append("yüksek skor")

    if pd.notna(confidence):
        try:
            confidence_value = float(confidence)
            if confidence_value >= 75:
                comments.append(f"güven {confidence_value:.0f}")
            elif confidence_value < 50:
                comments.append("güven düşük")
        except (TypeError, ValueError):
            pass

    if pd.notna(relative):
        try:
            if float(relative) > 1:
                comments.append("BIST'ten güçlü")
            elif float(relative) < -1:
                comments.append("BIST'ten zayıf")
        except (TypeError, ValueError):
            pass

    if pd.notna(adx_value):
        try:
            if float(adx_value) >= 25:
                comments.append("trend güçlü")
        except (TypeError, ValueError):
            pass

    if pd.notna(rsi_value):
        try:
            rsi_number = float(rsi_value)
            if rsi_number >= 70:
                comments.append("RSI yüksek")
            elif rsi_number <= 35:
                comments.append("RSI düşük")
        except (TypeError, ValueError):
            pass

    return " • ".join(comments)


def _merge_relative_strength(frame: pd.DataFrame) -> pd.DataFrame:
    relative_results = st.session_state.get("relative_results", [])

    if not relative_results:
        frame["BIST %"] = pd.NA
        frame["Hisse %"] = pd.NA
        frame["Ayrışma %"] = pd.NA
        return frame

    relative_frame = pd.DataFrame(relative_results)
    required = {"Kod", "BIST 100", "Hisse %", "Göreceli Fark"}

    if not required.issubset(relative_frame.columns):
        frame["BIST %"] = pd.NA
        frame["Hisse %"] = pd.NA
        frame["Ayrışma %"] = pd.NA
        return frame

    relative_frame = relative_frame[
        ["Kod", "BIST 100", "Hisse %", "Göreceli Fark"]
    ].rename(
        columns={
            "BIST 100": "BIST %",
            "Göreceli Fark": "Ayrışma %",
        }
    )

    return frame.merge(relative_frame, on="Kod", how="left")


def _analysis_for_row(row: pd.Series) -> pd.Series:
    participation_payload = None

    if "Arındırma" in row.index or "Arindirma" in row.index:
        participation_payload = {
            "uygun": True,
            "arindirma": row.get("Arındırma", row.get("Arindirma")),
        }

    relative_strength = row.get("Ayrışma %")

    result = analyze_signal_payload(
        signal=row.to_dict(),
        participation=participation_payload,
        relative_strength=relative_strength,
        volume_quality=50,
        volatility_quality=50,
        liquidity_quality=50,
    )

    return pd.Series(
        {
            "Güven": result["confidence"],
            "Güven Durumu": result["confidence_label"],
            "Güven Yıldızı": result["confidence_stars"],
            "Risk": result["risk_level"],
            "Başarı Göstergesi %": result["probability"],
            "AI Analizi": result["summary"],
        }
    )

def _prepare_scanner_frame(results: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(results)

    if frame.empty:
        return frame

    frame = _merge_relative_strength(frame)
    frame["AlphaScore"] = frame["Puan"].apply(_alpha_score)

    analysis_frame = frame.apply(_analysis_for_row, axis=1)
    for column in analysis_frame.columns:
        frame[column] = analysis_frame[column]

    frame["Trend"] = frame.apply(_trend_stars, axis=1)
    frame["Robot Yorumu"] = frame.apply(_robot_comment, axis=1)

    preferred_columns = [
        "Kod",
        "Hisse",
        "Fiyat",
        "Hisse %",
        "BIST %",
        "Ayrışma %",
        "Puan",
        "Güven",
        "Güven Durumu",
        "Güven Yıldızı",
        "Risk",
        "Başarı Göstergesi %",
        "AlphaScore",
        "Karar",
        "Trend",
        "RSI",
        "ADX",
        "Stop",
        "Hedef 1",
        "Hedef 2",
        "R/K 1",
        "R/K 2",
        "Arındırma",
        "Arindirma",
        "Neden",
        "Robot Yorumu",
        "AI Analizi",
        "Mum",
    ]

    available_columns = [
        column for column in preferred_columns if column in frame.columns
    ]

    return frame[available_columns]


def _filter_scanner_frame(
    frame: pd.DataFrame,
    selected_decisions: list[str],
    minimum_score: int,
    minimum_confidence: int,
    minimum_adx: int,
    search_text: str,
    only_positive_relative: bool,
) -> pd.DataFrame:
    filtered = frame.copy()

    if selected_decisions:
        filtered = filtered[filtered["Karar"].isin(selected_decisions)]

    if "Puan" in filtered.columns:
        filtered = filtered[
            pd.to_numeric(filtered["Puan"], errors="coerce").fillna(0)
            >= minimum_score
        ]

    if "Güven" in filtered.columns:
        filtered = filtered[
            pd.to_numeric(filtered["Güven"], errors="coerce").fillna(0)
            >= minimum_confidence
        ]

    if minimum_adx > 0 and "ADX" in filtered.columns:
        filtered = filtered[
            pd.to_numeric(filtered["ADX"], errors="coerce").fillna(0)
            >= minimum_adx
        ]

    if only_positive_relative and "Ayrışma %" in filtered.columns:
        filtered = filtered[
            pd.to_numeric(filtered["Ayrışma %"], errors="coerce").fillna(-999)
            > 0
        ]

    search_text = search_text.strip().lower()

    if search_text:
        mask = (
            filtered["Kod"]
            .astype(str)
            .str.lower()
            .str.contains(search_text, na=False)
        )

        if "Hisse" in filtered.columns:
            mask = mask | (
                filtered["Hisse"]
                .astype(str)
                .str.lower()
                .str.contains(search_text, na=False)
            )

        filtered = filtered[mask]

    return filtered


def _to_excel(frame: pd.DataFrame) -> bytes:
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name="Scanner PRO", index=False)

    return output.getvalue()


def _render_summary(frame: pd.DataFrame):
    if frame.empty:
        return

    total = len(frame)
    net_count = int((frame["Karar"] == "NET AL").sum())
    candidate_count = int((frame["Karar"] == "AL ADAY").sum())
    watch_count = int(frame["Karar"].isin(["IZLE", "İZLE"]).sum())
    wait_count = int((frame["Karar"] == "BEKLE").sum())

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Toplam", total)
    c2.metric("NET AL", net_count)
    c3.metric("AL ADAY", candidate_count)
    c4.metric("İZLE", watch_count)
    c5.metric("BEKLE", wait_count)


def _render_pro_table(frame: pd.DataFrame):
    if frame.empty:
        st.info("Filtrelere uygun sonuç bulunamadı.")
        return

    style = frame.style

    if "Karar" in frame.columns:
        style = style.map(_style_decision, subset=["Karar"])

    if "AlphaScore" in frame.columns:
        style = style.map(_style_quality, subset=["AlphaScore"])

    if "Güven Durumu" in frame.columns:
        style = style.map(_style_confidence, subset=["Güven Durumu"])

    if "Ayrışma %" in frame.columns:
        style = style.map(_style_relative, subset=["Ayrışma %"])

    numeric_formats = {
        "Fiyat": "{:,.4f}",
        "Hisse %": "{:+.2f}%",
        "BIST %": "{:+.2f}%",
        "Ayrışma %": "{:+.2f}%",
        "Puan": "{:.1f}",
        "Güven": "{:.1f}",
        "Başarı Göstergesi %": "{:.1f}%",
        "RSI": "{:.2f}",
        "ADX": "{:.2f}",
        "Stop": "{:,.4f}",
        "Hedef 1": "{:,.4f}",
        "Hedef 2": "{:,.4f}",
        "R/K 1": "{:.2f}",
        "R/K 2": "{:.2f}",
        "Arındırma": "{:.2f}",
        "Arindirma": "{:.2f}",
    }

    available_formats = {
        key: value for key, value in numeric_formats.items() if key in frame.columns
    }

    style = style.format(available_formats, na_rep="—")

    st.dataframe(
        style,
        width="stretch",
        hide_index=True,
        height=620,
    )


def _render_bist_universe(
    data_engine,
    *,
    title: str,
    button_label: str,
    items: list[dict],
    session_prefix: str,
    universe_name: str,
):
    st.title(title)

    if not items:
        st.warning(f"{universe_name} listesi boş.")
        return

    st.session_state["selected_bist_universe"] = universe_name

    top1, top2, top3 = st.columns(3)

    workers = top1.slider(
        "Paralel işçi",
        min_value=1,
        max_value=8,
        value=4,
        key=f"{session_prefix}_workers",
    )

    top2.metric("Takip edilen hisse", len(items))

    relative_results = st.session_state.get("relative_results", [])
    top3.metric("Göreceli güç verisi", "Hazır" if relative_results else "Yok")

    results_key = f"{session_prefix}_results"
    failures_key = f"{session_prefix}_failures"

    if st.button(button_label, type="primary", key=f"{session_prefix}_scan"):
        with st.spinner(f"{len(items)} hisse taranıyor..."):
            results, failures = scan_yahoo_items(data_engine, items, workers)

        st.session_state[results_key] = results
        st.session_state[failures_key] = failures
        # Robot ekranı son çalıştırılan BIST evrenini bağımsız olarak okuyabilsin.
        st.session_state["s2_bist_results"] = results
        st.session_state["s2_bist_failures"] = failures
        st.session_state["selected_bist_universe"] = universe_name

    results = st.session_state.get(results_key, [])
    failures = st.session_state.get(failures_key, [])

    if not results:
        st.info("Henüz tarama yapılmadı.")
        return

    frame = _prepare_scanner_frame(results)
    _render_summary(frame)

    st.subheader("Filtreler")
    f1, f2, f3, f4, f5 = st.columns(5)

    selected_decisions = f1.multiselect(
        "Kararlar",
        options=["NET AL", "AL ADAY", "IZLE", "BEKLE"],
        default=["NET AL", "AL ADAY", "IZLE"],
        key=f"{session_prefix}_decisions",
    )

    minimum_score = f2.slider(
        "Minimum skor", 0, 100, 50, key=f"{session_prefix}_score"
    )
    minimum_confidence = f3.slider(
        "Minimum güven", 0, 100, 0, key=f"{session_prefix}_confidence"
    )
    minimum_adx = f4.slider(
        "Minimum ADX", 0, 50, 0, key=f"{session_prefix}_adx"
    )
    only_positive_relative = f5.checkbox(
        "Sadece BIST'ten güçlüler",
        value=False,
        disabled="Ayrışma %" not in frame.columns,
        key=f"{session_prefix}_relative",
    )

    search_text = st.text_input(
        "Hisse ara",
        placeholder="Örnek: BIMAS",
        key=f"{session_prefix}_search",
    )

    filtered = _filter_scanner_frame(
        frame=frame,
        selected_decisions=selected_decisions,
        minimum_score=minimum_score,
        minimum_confidence=minimum_confidence,
        minimum_adx=minimum_adx,
        search_text=search_text,
        only_positive_relative=only_positive_relative,
    )

    sort_options = [
        column
        for column in [
            "Güven",
            "Başarı Göstergesi %",
            "Puan",
            "Ayrışma %",
            "RSI",
            "ADX",
            "Fiyat",
        ]
        if column in filtered.columns
    ]

    if sort_options:
        s1, s2 = st.columns(2)
        sort_column = s1.selectbox(
            "Sıralama", sort_options, key=f"{session_prefix}_sort"
        )
        descending = s2.checkbox(
            "Büyükten küçüğe", value=True, key=f"{session_prefix}_descending"
        )
        filtered = filtered.sort_values(
            by=sort_column,
            ascending=not descending,
            na_position="last",
        )

    st.subheader(f"Sonuçlar — {len(filtered)} hisse")
    _render_pro_table(filtered)

    export1, export2 = st.columns(2)
    csv_data = filtered.to_csv(index=False).encode("utf-8-sig")
    safe_name = session_prefix.replace("s2_", "")

    export1.download_button(
        "CSV indir",
        data=csv_data,
        file_name=f"alphascan_{safe_name}.csv",
        mime="text/csv",
        key=f"{session_prefix}_csv",
    )

    try:
        excel_data = _to_excel(filtered)
        export2.download_button(
            "Excel indir",
            data=excel_data,
            file_name=f"alphascan_{safe_name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{session_prefix}_xlsx",
        )
    except ImportError:
        export2.info("Excel aktarımı için openpyxl gerekli.")

    if failures:
        st.warning(f"{len(failures)} hisse taranamadı.")
        st.dataframe(pd.DataFrame(failures), width="stretch", hide_index=True)


def render_bist(data_engine, watchlists):
    _render_bist_universe(
        data_engine,
        title="📈 Scanner PRO — Arındırma 0",
        button_label="Arındırma 0 Taramasını Başlat",
        items=watchlists.get("arindirma_0", []),
        session_prefix="s2_arindirma0",
        universe_name="Arındırma 0",
    )


def render_katilim(data_engine, items):
    _render_bist_universe(
        data_engine,
        title="🕌 Scanner PRO — Katılım Tüm",
        button_label="Katılım Tüm Taramasını Başlat",
        items=items,
        session_prefix="s2_katilim_tum",
        universe_name="Katılım Tüm",
    )


def render_katilim_100(data_engine, items):
    _render_bist_universe(
        data_engine,
        title="🕌 Scanner PRO — Katılım 100",
        button_label="Katılım 100 Taramasını Başlat",
        items=items,
        session_prefix="s2_katilim100",
        universe_name="Katılım 100",
    )

def _prepare_simple_market_frame(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)

    if frame.empty:
        return frame

    if "Puan" in frame.columns:
        frame["AlphaScore"] = frame["Puan"].apply(_alpha_score)
        analysis_frame = frame.apply(_analysis_for_row, axis=1)
        for column in analysis_frame.columns:
            frame[column] = analysis_frame[column]

    return frame


def render_crypto(data_engine, database):
    """SQLite'taki son başarılı kripto arka plan taramasını gösterir."""
    st.title("₿ Kripto Tarama")

    rows = latest_scan_results(
        database,
        market="KRIPTO",
    )

    if not rows:
        st.info("Henüz kripto arka plan taraması bulunamadı.")
        return

    frame = _prepare_simple_market_frame(rows)
    st.caption(f"Arka plan veritabanından yüklenen sonuç: {len(frame)} kripto")
    _render_pro_table(frame)


def render_commodity(data_engine, database):
    """SQLite'taki son başarılı emtia arka plan taramasını gösterir."""
    st.title("🥇 Emtia Tarama")

    rows = latest_scan_results(
        database,
        market="EMTIA",
    )

    if not rows:
        st.info("Henüz emtia arka plan taraması bulunamadı.")
        return

    frame = _prepare_simple_market_frame(rows)
    st.caption(f"Arka plan veritabanından yüklenen sonuç: {len(frame)} emtia")
    _render_pro_table(frame)
