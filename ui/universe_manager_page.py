from __future__ import annotations

import pandas as pd
import streamlit as st

from engine.universe_manager import UniverseManager


def render_universe_manager(manager: UniverseManager) -> None:
    st.title("🧭 Evren Yöneticisi")
    st.caption(
        "BIST Katılım ve Arındırma 0 listelerini tek merkezden yönetir. "
        "Listeden çıkarılan hisseler silinmez; geçmiş işlemler korunarak pasif yapılır."
    )

    summaries = manager.list_universes()
    columns = st.columns(max(1, len(summaries)))
    for column, summary in zip(columns, summaries):
        with column:
            st.metric(summary.name, summary.active_count, f"Toplam kayıt: {summary.total_count}")
            st.caption(f"Son güncelleme: {summary.updated_at or '-'}")

    st.subheader("Arındırma 0 — Aktif Liste")
    zero_items = manager.get_items("arindirma_0")
    st.dataframe(
        pd.DataFrame(zero_items)[["kod", "ad", "sembol"]] if zero_items else pd.DataFrame(),
        width="stretch",
        hide_index=True,
    )

    left, right = st.columns(2)
    with left:
        st.markdown("#### Hisse ekle / yeniden etkinleştir")
        with st.form("universe_add_form", clear_on_submit=True):
            code = st.text_input("Hisse kodu", placeholder="Örnek: BIMAS")
            name = st.text_input("Şirket adı", placeholder="İsteğe bağlı")
            add_submitted = st.form_submit_button("Arındırma 0 listesine ekle", type="primary")
        if add_submitted:
            try:
                item = manager.add_or_update("arindirma_0", code=code, name=name, arindirma=0.0)
                st.success(f"{item['kod']} Arındırma 0 evrenine eklendi/etkinleştirildi.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    with right:
        st.markdown("#### Hisseyi pasif yap")
        choices = [item["kod"] for item in zero_items]
        selected = st.selectbox("Çıkarılacak hisse", choices, disabled=not choices)
        confirm = st.checkbox("Listeden çıkarmayı onaylıyorum", disabled=not choices)
        if st.button("Arındırma 0 listesinden çıkar", disabled=not choices or not confirm):
            if manager.deactivate("arindirma_0", selected):
                st.success(f"{selected} pasif yapıldı. Geçmiş kayıtları korunuyor.")
                st.rerun()
            else:
                st.warning("Hisse aktif listede bulunamadı.")

    st.subheader("Katılım Tüm Senkronizasyonu")
    st.write(
        "Bu işlem projedeki Katılım Tüm ana listesini kayıt sistemine aktarır; "
        "yeni sembolleri ekler ve ana listeden çıkanları pasif yapar."
    )
    if st.button("Katılım Tüm listesini senkronize et"):
        result = manager.synchronize_katilim_master()
        st.success(
            "Senkronizasyon tamamlandı — "
            f"Eklenen: {result['added']} · Yeniden etkin: {result['reactivated']} · "
            f"Pasif: {result['deactivated']}"
        )
        st.rerun()

    st.subheader("Son Evren Değişiklikleri")
    changes = manager.recent_changes(50)
    if changes:
        st.dataframe(pd.DataFrame(changes), width="stretch", hide_index=True)
    else:
        st.info("Henüz evren değişikliği kaydı bulunmuyor.")
