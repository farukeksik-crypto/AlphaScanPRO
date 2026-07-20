from __future__ import annotations

from pathlib import Path
import re

TARGET = Path(r"C:\Users\Faruk\AlphaScanPRO_Sprint2\ui\scanner_pages.py")

if not TARGET.exists():
    raise FileNotFoundError(f"Dosya bulunamadı: {TARGET}")

text = TARGET.read_text(encoding="utf-8")

import_line = "from engine.relative_strength_engine import scan_relative_strength"
if import_line not in text:
    anchor = "import streamlit as st"
    if anchor not in text:
        raise RuntimeError("streamlit import satırı bulunamadı.")
    text = text.replace(anchor, anchor + "\n\n" + import_line, 1)

new_render_bist = '''def render_bist(data_engine, watchlists):
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

    top2.metric("Takip edilen hisse", len(items))

    relative_results = st.session_state.get("relative_results", [])
    top3.metric(
        "Göreceli güç verisi",
        "Hazır" if relative_results else "Yok",
    )

    if st.button("Arındırma 0 Taramasını Başlat", type="primary"):
        with st.spinner(
            f"{len(items)} hisse teknik ve göreceli güç açısından taranıyor..."
        ):
            results, failures = scan_yahoo_items(
                data_engine,
                items,
                workers,
            )

            relative_results = []
            relative_failures = []
            relative_summary = {}

            try:
                (
                    relative_results,
                    relative_failures,
                    relative_summary,
                ) = scan_relative_strength(
                    data_engine=data_engine,
                    items=items,
                    interval="1d",
                    workers=workers,
                    force_refresh=False,
                )
            except Exception as exc:
                st.warning(f"Göreceli güç hesaplanamadı: {exc}")

        st.session_state["s2_bist_results"] = results
        st.session_state["s2_bist_failures"] = failures
        st.session_state["relative_results"] = relative_results
        st.session_state["relative_failures"] = relative_failures
        st.session_state["relative_summary"] = relative_summary
        st.rerun()

    results = st.session_state.get("s2_bist_results", [])
    failures = st.session_state.get("s2_bist_failures", [])
    relative_results = st.session_state.get("relative_results", [])
    relative_failures = st.session_state.get("relative_failures", [])
    relative_summary = st.session_state.get("relative_summary", {})

    if not results:
        st.info("Henüz tarama yapılmadı.")
        return

    if relative_results:
        st.success(
            f"Göreceli güç hazır: {len(relative_results)} hisse karşılaştırıldı."
        )

        if relative_summary:
            r1, r2, r3 = st.columns(3)

            r1.metric(
                "BIST değişimi",
                f"{relative_summary.get('benchmark_change', 0):+.2f}%",
            )
            r2.metric(
                "BIST'ten güçlü",
                relative_summary.get("endeksten_guclu", 0),
            )
            r3.metric(
                "BIST'ten zayıf",
                relative_summary.get("endeksten_zayif", 0),
            )

    frame = _prepare_scanner_frame(results)
    _render_summary(frame)

    st.subheader("Filtreler")
    f1, f2, f3, f4, f5 = st.columns(5)

    selected_decisions = f1.multiselect(
        "Kararlar",
        options=["NET AL", "AL ADAY", "IZLE", "İZLE", "BEKLE"],
        default=["NET AL", "AL ADAY", "IZLE", "İZLE"],
    )

    minimum_score = f2.slider("Minimum skor", 0, 100, 50)
    minimum_confidence = f3.slider("Minimum güven", 0, 100, 0)
    minimum_adx = f4.slider("Minimum ADX", 0, 50, 0)

    relative_available = (
        "Ayrışma %" in frame.columns
        and pd.to_numeric(
            frame["Ayrışma %"],
            errors="coerce",
        ).notna().any()
    )

    only_positive_relative = f5.checkbox(
        "Sadece BIST'ten güçlüler",
        value=False,
        disabled=not relative_available,
    )

    search_text = st.text_input(
        "Hisse ara",
        placeholder="Örnek: BIMAS",
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
        f"Arındırma 0 sonuçları — {len(filtered)} hisse"
    )

    _render_pro_table(filtered)

    export1, export2 = st.columns(2)

    csv_data = (
        filtered.to_csv(index=False)
        .encode("utf-8-sig")
    )

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
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
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

    if relative_failures:
        with st.expander(
            f"Göreceli güçte taranamayanlar: "
            f"{len(relative_failures)}"
        ):
            st.dataframe(
                pd.DataFrame(relative_failures),
                width="stretch",
                hide_index=True,
            )


'''

pattern = re.compile(
    r"def render_bist\(data_engine, watchlists\):.*?(?=^def render_(?:crypto|commodity|commodities)\()",
    re.MULTILINE | re.DOTALL,
)

match = pattern.search(text)
if not match:
    raise RuntimeError(
        "render_bist bölümü bulunamadı. Dosya yapısı beklenenden farklı."
    )

backup = TARGET.with_suffix(".py.bak")
backup.write_text(text, encoding="utf-8")

text = pattern.sub(new_render_bist, text, count=1)
TARGET.write_text(text, encoding="utf-8")

compile(text, str(TARGET), "exec")

print("Düzeltme tamamlandı.")
print(f"Yedek: {backup}")
print(f"Güncel dosya: {TARGET}")