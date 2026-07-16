from __future__ import annotations

from io import BytesIO

import pandas as pd
import streamlit as st

from engine.scanner import (
    scan_commodities,
    scan_crypto,
    scan_yahoo_items,
)


def _style_decision(value: str) -> str:
    styles = {
        "NET AL": "background-color:#00e676;color:black;font-weight:bold",
        "AL ADAY": "background-color:#00bcd4;color:black;font-weight:bold",
        "IZLE": "background-color:#ffb300;color:black",
        "BEKLE": "background-color:#757575;color:white",
        "YETERSIZ VERI": "background-color:#f44336;color:white",
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

    if decision == "IZLE":
        return "★★☆☆☆"

    return "★☆☆☆☆"


def _robot_comment(row: pd.Series) -> str:
    comments = []

    score = float(row.get("Puan", 0) or 0)
    decision = str(row.get("Karar", ""))
    relative = row.get("Ayrışma %")
    rsi_value = row.get("RSI")
    adx_value = row.get("ADX")

    if decision == "NET AL":
        comments.append("Güçlü sinyal")

    elif decision == "AL ADAY":
        comments.append("Giriş onayı beklenmeli")

    elif decision == "IZLE":
        comments.append("Takip edilmeli")

    else:
        comments.append("Şimdilik uygun değil")

    if score >= 90:
        comments.append("yüksek skor")

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

    required = {
        "Kod",
        "BIST 100",
        "Hisse %",
        "Göreceli Fark",
    }

    if not required.issubset(relative_frame.columns):
        frame["BIST %"] = pd.NA
        frame["Hisse %"] = pd.NA
        frame["Ayrışma %"] = pd.NA
        return frame

    relative_frame = relative_frame[
        [
            "Kod",
            "BIST 100",
            "Hisse %",
            "Göreceli Fark",
        ]
    ].rename(
        columns={
            "BIST 100": "BIST %",
            "Göreceli Fark": "Ayrışma %",
        }
    )

    return frame.merge(
        relative_frame,
        on="Kod",
        how="left",
    )


def _prepare_scanner_frame(results: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(results)

    if frame.empty:
        return frame

    frame = _merge_relative_strength(frame)

    frame["AlphaScore"] = frame["Puan"].apply(_alpha_score)
    frame["Trend"] = frame.apply(_trend_stars, axis=1)
    frame["Robot Yorumu"] = frame.apply(
        _robot_comment,
        axis=1,
    )

    preferred_columns = [
        "Kod",
        "Hisse",
        "Fiyat",
        "Hisse %",
        "BIST %",
        "Ayrışma %",
        "Puan",
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
        "Neden",
        "Robot Yorumu",
        "Mum",
    ]

    available_columns = [
        column
        for column in preferred_columns
        if column in frame.columns
    ]

    return frame[available_columns]


def _filter_scanner_frame(
    frame: pd.DataFrame,
    selected_decisions: list[str],
    minimum_score: int,
    minimum_adx: int,
    search_text: str,
    only_positive_relative: bool,
) -> pd.DataFrame:
    filtered = frame.copy()

    if selected_decisions:
        filtered = filtered[
            filtered["Karar"].isin(selected_decisions)
        ]

    if "Puan" in filtered.columns:
        filtered = filtered[
            pd.to_numeric(
                filtered["Puan"],
                errors="coerce",
            ).fillna(0) >= minimum_score
        ]

    if minimum_adx > 0 and "ADX" in filtered.columns:
        adx_values = pd.to_numeric(
            filtered["ADX"],
            errors="coerce",
        )

        filtered = filtered[
            adx_values.fillna(0) >= minimum_adx
        ]

    if only_positive_relative and "Ayrışma %" in filtered.columns:
        relative_values = pd.to_numeric(
            filtered["Ayrışma %"],
            errors="coerce",
        )

        filtered = filtered[
            relative_values.fillna(-999) > 0
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

    with pd.ExcelWriter(
        output,
        engine="openpyxl",
    ) as writer:
        frame.to_excel(
            writer,
            sheet_name="Scanner PRO",
            index=False,
        )

    return output.getvalue()


def _render_summary(frame: pd.DataFrame):
    if frame.empty:
        return

    total = len(frame)
    net_count = int((frame["Karar"] == "NET AL").sum())
    candidate_count = int(
        (frame["Karar"] == "AL ADAY").sum()
    )
    watch_count = int((frame["Karar"] == "IZLE").sum())
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
        style = style.map(
            _style_decision,
            subset=["Karar"],
        )

    if "AlphaScore" in frame.columns:
        style = style.map(
            _style_quality,
            subset=["AlphaScore"],
        )

    if "Ayrışma %" in frame.columns:
        style = style.map(
            _style_relative,
            subset=["Ayrışma %"],
        )

    numeric_formats = {
        "Fiyat": "{:,.4f}",
        "Hisse %": "{:+.2f}%",
        "BIST %": "{:+.2f}%",
        "Ayrışma %": "{:+.2f}%",
        "Puan": "{:.1f}",
        "RSI": "{:.2f}",
        "ADX": "{:.2f}",
        "Stop": "{:,.4f}",
        "Hedef 1": "{:,.4f}",
        "Hedef 2": "{:,.4f}",
        "R/K 1": "{:.2f}",
        "R/K 2": "{:.2f}",
    }

    available_formats = {
        key: value
        for key, value in numeric_formats.items()
        if key in frame.columns
    }

    style = style.format(
        available_formats,
        na_rep="—",
    )

    st.dataframe(
        style,
        width="stretch",
        hide_index=True,
        height=620,
    )


def render_bist(data_engine, watchlists):
    st.title("📈 Scanner PRO — Arındırma 0")

    items = watchlists.get("arindirma_0", [])

    if not items:
        st.warning("Arındırma 0 listesi boş.")
        return

    top1, top2, top3 = st.columns(3)

    workers = top1.slider(
        "Paralel işçi",
        min_value=1,
        max_value=8,
        value=4,
    )

    top2.metric(
        "Takip edilen hisse",
        len(items),
    )

    relative_results = st.session_state.get(
        "relative_results",
        [],
    )

    top3.metric(
        "Göreceli güç verisi",
        "Hazır" if relative_results else "Yok",
    )

    if st.button(
        "Arındırma 0 Taramasını Başlat",
        type="primary",
    ):
        with st.spinner(
            f"{len(items)} hisse taranıyor..."
        ):
            results, failures = scan_yahoo_items(
                data_engine,
                items,
                workers,
            )

        st.session_state["s2_bist_results"] = results
        st.session_state["s2_bist_failures"] = failures

    results = st.session_state.get(
        "s2_bist_results",
        [],
    )

    failures = st.session_state.get(
        "s2_bist_failures",
        [],
    )

    if not results:
        st.info("Henüz tarama yapılmadı.")
        return

    frame = _prepare_scanner_frame(results)

    _render_summary(frame)

    st.subheader("Filtreler")

    f1, f2, f3, f4 = st.columns(4)

    selected_decisions = f1.multiselect(
        "Kararlar",
        options=[
            "NET AL",
            "AL ADAY",
            "IZLE",
            "BEKLE",
        ],
        default=[
            "NET AL",
            "AL ADAY",
            "IZLE",
        ],
    )

    minimum_score = f2.slider(
        "Minimum skor",
        min_value=0,
        max_value=100,
        value=50,
    )

    minimum_adx = f3.slider(
        "Minimum ADX",
        min_value=0,
        max_value=50,
        value=0,
    )

    only_positive_relative = f4.checkbox(
        "Sadece BIST'ten güçlüler",
        value=False,
        disabled="Ayrışma %" not in frame.columns,
    )

    search_text = st.text_input(
        "Hisse ara",
        placeholder="Örnek: BIMAS",
    )

    filtered = _filter_scanner_frame(
        frame=frame,
        selected_decisions=selected_decisions,
        minimum_score=minimum_score,
        minimum_adx=minimum_adx,
        search_text=search_text,
        only_positive_relative=only_positive_relative,
    )

    sort_options = [
        column
        for column in [
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
            "Sıralama",
            sort_options,
        )

        descending = s2.checkbox(
            "Büyükten küçüğe",
            value=True,
        )

        filtered = filtered.sort_values(
            by=sort_column,
            ascending=not descending,
            na_position="last",
        )

    st.subheader(
        f"Sonuçlar — {len(filtered)} hisse"
    )

    _render_pro_table(filtered)

    export1, export2 = st.columns(2)

    csv_data = filtered.to_csv(
        index=False,
    ).encode("utf-8-sig")

    export1.download_button(
        "CSV indir",
        data=csv_data,
        file_name="alphascan_scanner_pro.csv",
        mime="text/csv",
    )

    try:
        excel_data = _to_excel(filtered)

        export2.download_button(
            "Excel indir",
            data=excel_data,
            file_name="alphascan_scanner_pro.xlsx",
            mime=(
                "application/vnd.openxmlformats-"
                "officedocument.spreadsheetml.sheet"
            ),
        )

    except ImportError:
        export2.info(
            "Excel aktarımı için openpyxl gerekli."
        )

    if failures:
        st.warning(
            f"{len(failures)} hisse taranamadı."
        )

        st.dataframe(
            pd.DataFrame(failures),
            width="stretch",
            hide_index=True,
        )


def render_crypto(data_engine):
    st.title("₿ Kripto Tarama")

    pairs = {
        "BTC": "BTC/USDT",
        "ETH": "ETH/USDT",
        "SOL": "SOL/USDT",
        "BNB": "BNB/USDT",
        "LINK": "LINK/USDT",
        "XRP": "XRP/USDT",
        "ADA": "ADA/USDT",
        "AVAX": "AVAX/USDT",
        "DOGE": "DOGE/USDT",
        "DOT": "DOT/USDT",
    }

    if st.button(
        "Kripto Taramasını Başlat",
        type="primary",
    ):
        with st.spinner(
            f"{len(pairs)} coin taranıyor..."
        ):
            rows, failures = scan_crypto(
                data_engine,
                pairs,
            )

        st.session_state["s2_crypto_results"] = rows
        st.session_state["s2_crypto_failures"] = failures

    rows = st.session_state.get(
        "s2_crypto_results",
        [],
    )

    failures = st.session_state.get(
        "s2_crypto_failures",
        [],
    )

    if rows:
        frame = pd.DataFrame(rows)

        if "Puan" in frame.columns:
            frame["AlphaScore"] = frame[
                "Puan"
            ].apply(_alpha_score)

        st.dataframe(
            frame.style.map(
                _style_decision,
                subset=["Karar"],
            ),
            width="stretch",
            hide_index=True,
        )

    else:
        st.info(
            "Henüz kripto taraması yapılmadı."
        )

    if failures:
        st.warning(
            f"{len(failures)} coin taranamadı."
        )

        st.dataframe(
            pd.DataFrame(failures),
            width="stretch",
            hide_index=True,
        )


def render_commodity(data_engine):
    st.title("🥇 Emtia Tarama")

    symbols = {
        "Altın": "GC=F",
        "Gümüş": "SI=F",
        "WTI Petrol": "CL=F",
        "Brent Petrol": "BZ=F",
        "Bakır": "HG=F",
        "Doğalgaz": "NG=F",
    }

    if st.button(
        "Emtia Taramasını Başlat",
        type="primary",
    ):
        with st.spinner(
            f"{len(symbols)} emtia taranıyor..."
        ):
            rows, failures = scan_commodities(
                data_engine,
                symbols,
            )

        st.session_state[
            "s2_commodity_results"
        ] = rows

        st.session_state[
            "s2_commodity_failures"
        ] = failures

    rows = st.session_state.get(
        "s2_commodity_results",
        [],
    )

    failures = st.session_state.get(
        "s2_commodity_failures",
        [],
    )

    if rows:
        frame = pd.DataFrame(rows)

        if "Puan" in frame.columns:
            frame["AlphaScore"] = frame[
                "Puan"
            ].apply(_alpha_score)

        st.dataframe(
            frame.style.map(
                _style_decision,
                subset=["Karar"],
            ),
            width="stretch",
            hide_index=True,
        )

    else:
        st.info(
            "Henüz emtia taraması yapılmadı."
        )

    if failures:
        st.warning(
            f"{len(failures)} emtia taranamadı."
        )

        st.dataframe(
            pd.DataFrame(failures),
            width="stretch",
            hide_index=True,
        )