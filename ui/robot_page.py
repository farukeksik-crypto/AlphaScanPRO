from __future__ import annotations

import pandas as pd
import streamlit as st

from database.background_repository import latest_results_by_source
from engine.robot_engine import RobotConfig, RobotEngine
from engine.market_accounts import MARKET_ACCOUNTS, account_for_market, normalize_market


def _format_money(value: float, currency: str = "TRY") -> str:
    suffix = {"TRY": "TL", "USDT": "USDT", "USD": "USD"}.get(currency, currency)
    return f"{float(value):,.2f} {suffix}"


def _render_action_messages(actions: list[dict]):
    if not actions:
        st.info("Robot herhangi bir işlem oluşturmadı.")
        return

    for action in actions:
        message = str(action.get("message", "İşlem tamamlandı."))
        if action.get("ok"):
            st.success(message)
        else:
            st.warning(message)


def _get_available_scanner_sources(database) -> dict[str, list[dict]]:
    # Birincil kaynak SQLite: background_worker sonuçlarıdır.
    sources = latest_results_by_source(database)

    # Worker henüz hiç çalışmadıysa, geçici geri dönüş olarak bu oturumdaki
    # manuel tarama sonuçlarını gösterir.
    if sources:
        return sources

    fallback: dict[str, list[dict]] = {}
    bist_results = st.session_state.get("s2_bist_results", [])
    if bist_results:
        universe = st.session_state.get("selected_bist_universe", "Son BIST taraması")
        fallback[f"BIST — {universe} (Oturum)"] = bist_results
    crypto_results = st.session_state.get("s2_crypto_results", [])
    if crypto_results:
        group = st.session_state.get("selected_crypto_group", "Son kripto taraması")
        fallback[f"Kripto — {group} (Oturum)"] = crypto_results
    commodity_results = st.session_state.get("s2_commodity_results", [])
    if commodity_results:
        fallback["Emtia — Son tarama (Oturum)"] = commodity_results
    return fallback


def _parse_source(source: str) -> tuple[str, str]:
    if " — " not in source:
        return source, ""

    market, universe = source.split(" — ", 1)
    return market.strip().upper().replace("KRIPTO", "KRIPTO"), universe.replace("(SQLite)", "").replace("(Oturum)", "").strip()


def _filter_robot_candidates(
    rows: list[dict],
    minimum_score: float,
    minimum_confidence: float,
    minimum_probability: float,
    allowed_risks: tuple[str, ...],
    allowed_decisions: tuple[str, ...],
) -> list[dict]:
    filtered: list[dict] = []

    for row in rows:
        decision = str(row.get("Karar", ""))
        score = float(row.get("Puan", 0) or 0)
        confidence = float(row.get("Güven", 0) or 0)
        probability = float(
            row.get("Başarı Göstergesi %", 0) or 0
        )
        risk_level = str(row.get("Risk", "")).strip()

        if decision not in allowed_decisions:
            continue
        if score < minimum_score:
            continue
        if confidence < minimum_confidence:
            continue
        if probability < minimum_probability:
            continue
        if allowed_risks and risk_level not in allowed_risks:
            continue

        filtered.append(row)

    return sorted(
        filtered,
        key=lambda item: (
            float(item.get("Başarı Göstergesi %", 0) or 0),
            float(item.get("Güven", 0) or 0),
            float(item.get("Puan", 0) or 0),
        ),
        reverse=True,
    )


def render_robot(database):
    st.title("🤖 Sanal İşlem Robotu")

    selected_market_label = st.radio(
        "Sanal hesap", ["BIST", "KRIPTO", "EMTIA"], horizontal=True,
        format_func=lambda x: MARKET_ACCOUNTS[x]["label"],
    )
    selected_account = account_for_market(selected_market_label)

    st.warning(
        "Bu robot yalnızca sanal işlem yapar. Gerçek emir göndermez. "
        "Birincil sinyal kaynağı Background Worker tarafından SQLite'a kaydedilen son taramalardır."
    )

    with st.expander("Robot Ayarları", expanded=True):
        a1, a2, a3, a4, a5 = st.columns(5)

        minimum_score = a1.slider(
            "Minimum teknik puan",
            min_value=50,
            max_value=100,
            value=80,
        )
        minimum_confidence = a2.slider(
            "Minimum güven puanı",
            min_value=0,
            max_value=100,
            value=65,
        )
        minimum_probability = a3.slider(
            "Minimum başarı göstergesi",
            min_value=0,
            max_value=100,
            value=65,
        )
        max_positions = a4.slider(
            "Maksimum açık pozisyon",
            min_value=1,
            max_value=10,
            value=5,
        )
        position_size_pct = a5.slider(
            "Pozisyon başına bakiye (%)",
            min_value=5,
            max_value=30,
            value=20,
            step=5,
        )

        allowed_decisions_list = st.multiselect(
            "İşlem açılabilecek kararlar",
            ["NET AL", "AL ADAY"],
            default=["NET AL"],
        )

        allowed_risk_list = st.multiselect(
            "İşlem açılabilecek risk seviyeleri",
            ["Düşük", "Orta", "Yüksek"],
            default=["Düşük", "Orta"],
        )

        strategy_profile = st.text_input(
            "Strateji profili",
            value="Default",
        )

        if not allowed_decisions_list:
            allowed_decisions_list = ["NET AL"]

    config = RobotConfig(
        starting_balance=float(selected_account["starting_balance"]),
        commission_rate=0.001,
        max_positions=int(max_positions),
        position_size_pct=float(position_size_pct) / 100,
        minimum_score=float(minimum_score),
        minimum_probability=float(minimum_probability),
        allowed_decisions=tuple(allowed_decisions_list),
        strategy_profile=strategy_profile.strip() or "Default",
        market=selected_market_label,
        account_id=selected_account["account_id"],
        currency=selected_account["currency"],
    )

    robot = RobotEngine(database=database, config=config)

    state = robot.get_state()
    positions = robot.get_open_positions()

    robot_status = "Aktif" if state["enabled"] else "Kapalı"

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Robot", robot_status)
    c2.metric("Nakit Bakiye", _format_money(state["balance"], state["currency"]))
    c3.metric("Günlük K/Z", _format_money(state["daily_profit"], state["currency"]))
    c4.metric("Toplam K/Z", _format_money(state["total_profit"], state["currency"]))
    c5.metric("Açık Pozisyon", len(positions))

    st.caption(
        "Son güncelleme: "
        + str(state.get("updated_at") or "Henüz güncelleme yok")
    )

    st.divider()
    st.subheader("Robot Kontrolü")

    control1, control2, control3 = st.columns(3)

    if state["enabled"]:
        if control1.button(
            "Robotu Kapat",
            type="primary",
            use_container_width=True,
        ):
            robot.set_enabled(False)
            st.success("Sanal işlem robotu kapatıldı.")
            st.rerun()
    else:
        if control1.button(
            "Robotu Aç",
            type="primary",
            use_container_width=True,
        ):
            robot.set_enabled(True)
            st.success("Sanal işlem robotu açıldı. Worker'ın yeni taramasında otomatik çalışacaktır.")
            st.rerun()

    scanner_sources = _get_available_scanner_sources(database)
    scanner_sources = {
        source: rows for source, rows in scanner_sources.items()
        if normalize_market(_parse_source(source)[0]) == selected_market_label
    }

    if scanner_sources:
        selected_source = control2.selectbox(
            "Tarama kaynağı",
            list(scanner_sources),
        )
        scanner_results = scanner_sources[selected_source]
        selected_market, selected_universe = _parse_source(selected_source)
        scanner_results = [row for row in scanner_results if normalize_market(selected_market) == selected_market_label]
    else:
        selected_source = "Tarama yok"
        scanner_results = []
        selected_market = ""
        selected_universe = ""

    if scanner_sources:
        sqlite_source = any("(SQLite)" in source for source in scanner_sources)
        if sqlite_source:
            st.success("Robot kaynağı: SQLite / Background Worker. Tarama ekranlarını açman gerekmez.")
        else:
            st.warning("Henüz SQLite arka plan taraması yok; geçici olarak açık oturum sonuçları kullanılıyor.")
    else:
        st.warning("Kayıtlı tarama bulunamadı. Background Worker'ı çalıştırın.")

    filtered_candidates = _filter_robot_candidates(
        rows=scanner_results,
        minimum_score=float(minimum_score),
        minimum_confidence=float(minimum_confidence),
        minimum_probability=float(minimum_probability),
        allowed_risks=tuple(allowed_risk_list),
        allowed_decisions=tuple(allowed_decisions_list),
    )

    control2.metric("Uygun aday", len(filtered_candidates))

    if control2.button(
        "Son SQLite Taramasını Şimdi İşle",
        disabled=not state["enabled"] or not filtered_candidates,
        use_container_width=True,
    ):
        actions = robot.process_scanner_results(
            filtered_candidates,
            market=selected_market,
            universe=selected_universe,
            strategy_profile=config.strategy_profile,
        )

        st.session_state["robot_last_actions"] = actions
        st.session_state["robot_last_source"] = selected_source
        st.rerun()

    reset_confirm = control3.checkbox(
        "Sıfırlamayı onayla",
        value=False,
    )

    if control3.button(
        "Sanal Hesabı Sıfırla",
        disabled=not reset_confirm,
        use_container_width=True,
    ):
        robot.reset_account()
        st.session_state.pop("robot_last_actions", None)
        st.session_state.pop("robot_last_source", None)
        st.success(f"{MARKET_ACCOUNTS[selected_market_label]['label']} sanal hesabı başlangıç bakiyesine sıfırlandı.")
        st.rerun()

    if scanner_results:
        st.subheader("Robot Adayları")
        candidate_frame = pd.DataFrame(filtered_candidates)

        if candidate_frame.empty:
            st.info(
                "Seçilen minimum puan ve güven şartlarına "
                "uygun aday bulunamadı."
            )
        else:
            columns = [
                column
                for column in [
                    "Kod",
                    "Hisse",
                    "Karar",
                    "Puan",
                    "Güven",
                    "Güven Durumu",
                    "Güven Yıldızı",
                    "Risk",
                    "Başarı Göstergesi %",
                    "Fiyat",
                    "Stop",
                    "Hedef 1",
                    "Hedef 2",
                    "Neden",
                    "AI Analizi",
                ]
                if column in candidate_frame.columns
            ]

            st.dataframe(
                candidate_frame[columns].style.format(
                    {
                        "Puan": "{:.1f}",
                        "Güven": "{:.1f}",
                        "Başarı Göstergesi %": "{:.1f}%",
                        "Fiyat": "{:,.4f}",
                        "Stop": "{:,.4f}",
                        "Hedef 1": "{:,.4f}",
                        "Hedef 2": "{:,.4f}",
                    },
                    na_rep="—",
                ),
                width="stretch",
                hide_index=True,
            )

    last_actions = st.session_state.get("robot_last_actions", [])

    if last_actions:
        st.subheader("Son Robot İşlemleri")
        st.caption(
            "Kaynak: "
            + st.session_state.get("robot_last_source", "Bilinmeyen")
        )
        _render_action_messages(last_actions)

    st.divider()
    st.subheader("Açık Pozisyonlar")

    positions = robot.get_open_positions()

    if positions.empty:
        st.info("Robotun açık sanal pozisyonu bulunmuyor.")
    else:
        display_positions = positions.rename(
            columns={
                "id": "ID",
                "symbol": "Kod",
                "quantity": "Miktar",
                "entry_price": "Giriş Fiyatı",
                "stop_price": "Stop",
                "target1": "Hedef 1",
                "target2": "Hedef 2",
                "opened_at": "Açılış Tarihi",
                "status": "Durum",
                "market": "Piyasa",
                "universe": "Evren",
                "technical_score": "Teknik Puan",
                "confidence_score": "Güven",
                "confidence_label": "Güven Durumu",
                "decision": "Karar",
                "entry_reason": "Giriş Nedeni",
                "strategy_profile": "Strateji Profili",
            }
        )

        st.dataframe(
            display_positions.style.format(
                {
                    "Miktar": "{:,.4f}",
                    "Giriş Fiyatı": "{:,.4f}",
                    "Stop": "{:,.4f}",
                    "Hedef 1": "{:,.4f}",
                    "Hedef 2": "{:,.4f}",
                    "Teknik Puan": "{:.1f}",
                    "Güven": "{:.1f}",
                },
                na_rep="—",
            ),
            width="stretch",
            hide_index=True,
        )

        st.subheader("Manuel Sanal Pozisyon Kapatma")

        options = {
            f"{row['symbol']} | Giriş: {float(row['entry_price']):,.4f}": int(row["id"])
            for _, row in positions.iterrows()
        }

        selected_label = st.selectbox(
            "Kapatılacak pozisyon",
            list(options),
        )
        position_id = options[selected_label]
        row = positions[positions["id"] == position_id].iloc[0]
        default_exit_price = float(row["entry_price"])

        exit_price = st.number_input(
            "Sanal çıkış fiyatı",
            min_value=0.0001,
            value=default_exit_price,
            step=max(default_exit_price * 0.001, 0.0001),
            format="%.4f",
        )

        exit_reason = st.selectbox(
            "Çıkış nedeni",
            [
                "MANUEL SATIŞ",
                "STOP",
                "HEDEF 1",
                "HEDEF 2",
                "SİNYAL ZAYIFLADI",
            ],
        )

        if st.button("Seçili Pozisyonu Kapat", type="primary"):
            result = robot.close_position(
                position_id=position_id,
                exit_price=float(exit_price),
                exit_reason=exit_reason,
            )

            if result.get("ok"):
                st.success(result["message"])
                st.rerun()
            else:
                st.error(result["message"])

    st.divider()
    st.subheader("İşlem Geçmişi")

    history = robot.get_trade_history()

    if history.empty:
        st.info("Henüz sanal işlem geçmişi oluşmadı.")
    else:
        display_history = history.rename(
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
                "reason": "Neden",
                "strategy_profile": "Strateji Profili",
                "position_id": "Pozisyon ID",
            }
        )

        st.dataframe(
            display_history.style.format(
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

        csv_data = display_history.to_csv(index=False).encode("utf-8-sig")

        st.download_button(
            "İşlem Geçmişini CSV İndir",
            data=csv_data,
            file_name="alphascan_robot_islem_gecmisi.csv",
            mime="text/csv",
        )

    st.divider()

    with st.expander("Robot Kuralları"):
        st.markdown(
            f'''
            - Başlangıç sanal bakiyesi: **{config.starting_balance:,.0f} TL**
            - Minimum teknik puan: **{config.minimum_score:.0f}**
            - Minimum güven puanı: **{minimum_confidence:.0f}**
            - Minimum başarı göstergesi: **%{minimum_probability:.0f}**
            - Kabul edilen risk seviyeleri: **{", ".join(allowed_risk_list) or "Yok"}**
            - Geçerli kararlar: **{", ".join(config.allowed_decisions)}**
            - Maksimum açık pozisyon: **{config.max_positions}**
            - Pozisyon başına bakiye kullanımı: **%{config.position_size_pct * 100:.0f}**
            - Tek yön komisyon: **%{config.commission_rate * 100:.2f}**
            - Strateji profili: **{config.strategy_profile}**
            - Aynı varlıkta ikinci açık pozisyon açılmaz.
            - Robot gerçek emir göndermez.
            '''
        )
