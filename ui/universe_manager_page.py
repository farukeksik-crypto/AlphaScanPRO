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


def _render_universe_performance_center() -> None:
    from config.settings import DATABASE_FILE
    from database.db import Database
    from engine.universe_performance import UniversePerformanceAnalytics

    st.divider()
    st.subheader("📊 Evren Performans Merkezi — Sprint 10.19B")
    st.caption(
        "Background Worker taramaları ile sanal robot işlemlerini evren bazında karşılaştırır. "
        "Bu panel robot kurallarını değiştirmez."
    )
    days = st.selectbox("Rapor dönemi", [7, 30, 90], index=1, format_func=lambda value: f"Son {value} gün")
    analytics = UniversePerformanceAnalytics(Database(DATABASE_FILE))
    summary = analytics.summary(days)
    rows = analytics.rows(days)

    columns = st.columns(5)
    columns[0].metric("Evren", summary["universe_count"])
    columns[1].metric("Taranan", summary["scanned"])
    columns[2].metric("Robot Aksiyonu", summary["robot_actions"])
    columns[3].metric("Açık Pozisyon", summary["open_positions"])
    columns[4].metric("Kapanan İşlem", summary["closed_trades"])

    if not rows:
        st.info("Seçilen dönemde evren performans verisi bulunmuyor.")
        return

    frame = pd.DataFrame([row.to_dict() for row in rows]).rename(columns={
        "market": "Piyasa", "universe": "Evren", "scan_runs": "Tarama",
        "scanned": "Taranan", "failures": "Veri Hatası", "robot_actions": "Robot Aksiyonu",
        "open_positions": "Açık Pozisyon", "closed_trades": "Kapanan İşlem",
        "winning_trades": "Kazanan", "net_profit": "Net K/Z",
        "win_rate": "Başarı %", "average_profit_pct": "Ort. K/Z %",
    })
    st.dataframe(frame, width="stretch", hide_index=True)
    st.bar_chart(frame.set_index("Evren")[["Taranan", "Robot Aksiyonu", "Kapanan İşlem"]])


_original_render_universe_manager = render_universe_manager


def render_universe_manager(manager: UniverseManager) -> None:
    _original_render_universe_manager(manager)
    _render_universe_performance_center()


def _render_multi_universe_accounts() -> None:
    from config.settings import DATABASE_FILE
    from database.db import Database
    from database.robot_migrations import migrate_database_object

    st.divider()
    st.subheader("💼 Evren Bazlı Sanal Hesaplar — Sprint 10.20B")
    st.caption(
        "BIST Katılım, Arındırma 0 ve Tüm BIST robotları ayrı nakit, pozisyon ve "
        "performans hesapları kullanır. Bir evrenin zararı veya sermaye kullanımı diğerini etkilemez."
    )
    database = Database(DATABASE_FILE)
    migrate_database_object(database)
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT account_id, market, currency, enabled, starting_balance, balance,
                   daily_profit, total_profit
            FROM robot_accounts
            WHERE account_id IN ('bist_katilim','bist_arindirma0','bist_all')
            ORDER BY CASE account_id
                WHEN 'bist_katilim' THEN 1
                WHEN 'bist_arindirma0' THEN 2
                ELSE 3 END
            """
        ).fetchall()
    labels = {
        "bist_katilim": "BIST Katılım",
        "bist_arindirma0": "Arındırma 0",
        "bist_all": "Tüm BIST",
    }
    frame = pd.DataFrame([
        {
            "Hesap": labels.get(row[0], row[0]),
            "Durum": "Aktif" if row[3] else "Kapalı",
            "Başlangıç": float(row[4]),
            "Nakit": float(row[5]),
            "Günlük K/Z": float(row[6]),
            "Toplam K/Z": float(row[7]),
            "Para Birimi": row[2],
        }
        for row in rows
    ])
    if frame.empty:
        st.info("Evren hesapları henüz oluşturulmadı.")
    else:
        st.dataframe(frame, width="stretch", hide_index=True)


_previous_render_universe_manager_1020b = render_universe_manager


def render_universe_manager(manager: UniverseManager) -> None:
    _previous_render_universe_manager_1020b(manager)
    _render_multi_universe_accounts()
