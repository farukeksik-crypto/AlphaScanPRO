from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from database.background_repository import latest_results_by_source
from database.robot_settings_repository import load_robot_settings, save_robot_settings
from engine.robot_engine import RobotConfig, RobotEngine
from engine.market_accounts import MARKET_ACCOUNTS, account_for_market, normalize_market
from engine.trade_performance_analytics import equity_curve, performance_by, summarize_trade_history


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



def _safe_robot_metric(robot, method_name: str, default):
    """Risk panelinde eksik motor metodları yüzünden ekranın çökmesini önler."""
    method = getattr(robot, method_name, None)
    if not callable(method):
        return default
    try:
        return method()
    except Exception:
        return default

def _format_duration(minutes: float | int | None) -> str:
    value = float(minutes or 0)
    if value < 60:
        return f"{value:.0f} dk"
    hours = value / 60
    if hours < 24:
        return f"{hours:.1f} saat"
    return f"{hours / 24:.1f} gün"


def _render_trade_intelligence_summary(history: pd.DataFrame) -> None:
    summary = summarize_trade_history(history)
    if summary.closed_trades == 0:
        return

    st.subheader("Trade Intelligence 10.18A")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Kapanan İşlem", summary.closed_trades)
    c2.metric("Başarı Oranı", f"%{summary.win_rate_pct:.1f}")
    c3.metric("Net K/Z", f"{summary.net_profit:+,.2f}")
    c4.metric(
        "Profit Factor",
        "∞" if summary.profit_factor == float("inf") else (f"{summary.profit_factor:.2f}" if summary.profit_factor is not None else "—"),
    )

    d1, d2, d3, d4 = st.columns(4)
    d1.metric("Ortalama Kazanç", f"{summary.average_win:+,.2f}")
    d2.metric("Ortalama Kayıp", f"-{summary.average_loss:,.2f}" if summary.average_loss else "0.00")
    d3.metric("Maksimum Drawdown", f"-{summary.maximum_drawdown:,.2f}")
    d4.metric("Ortalama Süre", _format_duration(summary.average_holding_minutes))

    e1, e2, e3, e4 = st.columns(4)
    e1.metric("En İyi İşlem", f"{summary.best_trade:+,.2f}")
    e2.metric("En Kötü İşlem", f"{summary.worst_trade:+,.2f}")
    e3.metric("Ortalama MFE", f"%{summary.average_mfe_pct:+.2f}")
    e4.metric("Ortalama MAE", f"%{summary.average_mae_pct:+.2f}")

    curve = equity_curve(history)
    if not curve.empty:
        st.caption("Gerçekleşmiş kâr/zarar eğrisi")
        st.line_chart(curve, x="Tarih", y="Kümülatif K/Z")

    tabs = st.tabs(["Piyasa Performansı", "Çıkış Nedenleri", "Sembol Performansı"])
    breakdowns = [
        ("market", tabs[0], "Piyasa"),
        ("reason", tabs[1], "Çıkış Nedeni"),
        ("symbol", tabs[2], "Kod"),
    ]
    for column, tab, label in breakdowns:
        with tab:
            table = performance_by(history, column)
            if table.empty:
                st.info("Yeterli kapanmış işlem verisi yok.")
            else:
                st.dataframe(table.rename(columns={column: label}), width="stretch", hide_index=True)



def _candidate_risk_preview(robot, state: dict, row: dict) -> dict:
    # Tarama adayı için işlem açılmadan risk ve miktar önizlemesi üretir.
    price = float(row.get("Fiyat", 0) or 0)
    stop_price = float(row.get("Stop", 0) or 0)

    empty = {
        "Önerilen Miktar": 0.0,
        "Önerilen Bütçe": 0.0,
        "Tahmini İşlem Riski": 0.0,
        "İşlem Riski %": 0.0,
        "Sizing Modu": "HESAPLANAMADI",
        "Portföy Risk Sonrası %": 0.0,
        "Portföy Maruziyet Sonrası %": 0.0,
        "Önizleme Durumu": "Geçersiz fiyat/stop",
    }

    if price <= 0 or stop_price <= 0 or stop_price >= price:
        return empty

    calculator = getattr(robot, "calculate_position_quantity", None)
    if not callable(calculator):
        empty["Önizleme Durumu"] = "Miktar hesaplayıcı bulunamadı"
        return empty

    quantity_info = None
    attempts = (
        lambda: calculator(state=state, price=price, stop_price=stop_price),
        lambda: calculator(
            balance=float(state.get("balance", 0) or 0),
            price=price,
            stop_price=stop_price,
        ),
        lambda: calculator(price=price, stop_price=stop_price),
    )

    for attempt in attempts:
        try:
            quantity_info = attempt()
            if quantity_info:
                break
        except TypeError:
            continue
        except Exception:
            break

    if not isinstance(quantity_info, dict):
        empty["Önizleme Durumu"] = "Hesaplama başarısız"
        return empty

    quantity = float(quantity_info.get("quantity", 0) or 0)
    budget = float(quantity_info.get("budget", quantity * price) or 0)
    risk_amount = float(
        quantity_info.get(
            "risk_amount",
            quantity_info.get("estimated_risk", quantity * (price - stop_price)),
        )
        or 0
    )
    sizing_mode = str(quantity_info.get("sizing_mode", "RISK_BASED"))

    starting_balance = float(
        state.get("starting_balance")
        or getattr(getattr(robot, "config", None), "starting_balance", 0)
        or 0
    )
    risk_pct = risk_amount / starting_balance * 100 if starting_balance > 0 else 0.0

    portfolio_summary = {}
    summary_method = getattr(robot, "get_portfolio_risk_summary", None)
    if callable(summary_method):
        try:
            portfolio_summary = summary_method(state=state) or {}
        except TypeError:
            try:
                portfolio_summary = summary_method() or {}
            except Exception:
                portfolio_summary = {}
        except Exception:
            portfolio_summary = {}

    current_risk = float(portfolio_summary.get("open_risk", 0) or 0)
    current_exposure = float(portfolio_summary.get("open_exposure", 0) or 0)

    projected_risk_pct = (
        (current_risk + risk_amount) / starting_balance * 100
        if starting_balance > 0
        else 0.0
    )
    projected_exposure_pct = (
        (current_exposure + budget) / starting_balance * 100
        if starting_balance > 0
        else 0.0
    )

    lock_reason = ""
    lock_method = getattr(robot, "portfolio_risk_lock_reason", None)
    if callable(lock_method) and quantity > 0:
        try:
            lock_reason = str(
                lock_method(
                    state=state,
                    price=price,
                    stop_price=stop_price,
                    quantity=quantity,
                )
                or ""
            )
        except Exception:
            lock_reason = ""

    return {
        "Önerilen Miktar": quantity,
        "Önerilen Bütçe": budget,
        "Tahmini İşlem Riski": risk_amount,
        "İşlem Riski %": risk_pct,
        "Sizing Modu": sizing_mode,
        "Portföy Risk Sonrası %": projected_risk_pct,
        "Portföy Maruziyet Sonrası %": projected_exposure_pct,
        "Önizleme Durumu": lock_reason or "UYGUN",
    }


def _add_candidate_risk_preview(robot, state: dict, candidate_frame: pd.DataFrame) -> pd.DataFrame:
    if candidate_frame.empty:
        return candidate_frame

    preview_rows = [
        _candidate_risk_preview(robot, state, row)
        for row in candidate_frame.to_dict("records")
    ]
    preview_frame = pd.DataFrame(preview_rows)
    return pd.concat(
        [candidate_frame.reset_index(drop=True), preview_frame.reset_index(drop=True)],
        axis=1,
    )

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



def _latest_robot_diagnostics(database, market: str):
    with database.connect() as connection:
        rows = connection.execute(
            """
            SELECT message
            FROM system_events
            WHERE event_type = 'ROBOT_DIAGNOSTIC'
            ORDER BY id DESC
            LIMIT 50
            """
        ).fetchall()

    requested_market = normalize_market(market)

    for row in rows:
        try:
            payload = json.loads(row[0])
        except (TypeError, ValueError, json.JSONDecodeError):
            continue

        saved_market = normalize_market(str(payload.get("market", "")))
        if saved_market == requested_market:
            return payload

    return None


def _diagnostics_frame(diagnostics: list[str]) -> pd.DataFrame:
    rows: list[dict] = []

    for item in diagnostics:
        text = str(item).strip()

        if ":" in text:
            symbol, reasons = text.split(":", 1)
        else:
            symbol, reasons = "-", text

        reason_parts = [
            reason.strip()
            for reason in reasons.split(",")
            if reason.strip()
        ]

        rows.append(
            {
                "Kod": symbol.strip(),
                "İşlem Açılmama Nedenleri": " • ".join(reason_parts),
                "Neden Sayısı": len(reason_parts),
                "Açık Pozisyon": (
                    "Evet"
                    if "açık pozisyon var" in reasons.lower()
                    else "Hayır"
                ),
            }
        )

    return pd.DataFrame(rows)


def _diagnostic_reason_counts(diagnostic_frame: pd.DataFrame) -> pd.DataFrame:
    if diagnostic_frame.empty:
        return pd.DataFrame(columns=["Engel", "Adet"])

    reasons = diagnostic_frame["İşlem Açılmama Nedenleri"].fillna("")

    counts = {
        "Güven": int(reasons.str.contains("güven", case=False, na=False).sum()),
        "Risk": int(reasons.str.contains("risk=", case=False, na=False).sum()),
        "Puan": int(reasons.str.contains("puan", case=False, na=False).sum()),
        "Olasılık": int(reasons.str.contains("olasılık", case=False, na=False).sum()),
        "Karar": int(reasons.str.contains("karar=", case=False, na=False).sum()),
        "Açık Pozisyon": int(
            diagnostic_frame["Açık Pozisyon"].eq("Evet").sum()
        ),
    }

    return pd.DataFrame(
        [
            {"Engel": reason, "Adet": count}
            for reason, count in counts.items()
        ]
    )


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
    saved_settings = load_robot_settings(
        database,
        account_id=selected_account["account_id"],
        market=selected_market_label,
    )

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
            value=int(saved_settings["minimum_score"]),
        )
        minimum_confidence = a2.slider(
            "Minimum güven puanı",
            min_value=0,
            max_value=100,
            value=int(saved_settings["minimum_confidence"]),
        )
        minimum_probability = a3.slider(
            "Minimum başarı göstergesi",
            min_value=0,
            max_value=100,
            value=int(saved_settings["minimum_probability"]),
        )
        max_positions = a4.slider(
            "Maksimum açık pozisyon",
            min_value=1,
            max_value=10,
            value=int(saved_settings["max_positions"]),
        )
        position_size_pct = a5.slider(
            "Pozisyon başına bakiye (%)",
            min_value=5,
            max_value=30,
            value=int(float(saved_settings["position_size_pct"]) * 100),
            step=5,
        )

        allowed_decisions_list = st.multiselect(
            "İşlem açılabilecek kararlar",
            ["NET AL", "AL ADAY"],
            default=list(saved_settings["allowed_decisions"]),
        )

        allowed_risk_list = st.multiselect(
            "İşlem açılabilecek risk seviyeleri",
            ["Düşük", "Orta", "Yüksek"],
            default=list(saved_settings["allowed_risks"]),
        )

        strategy_profile = st.text_input(
            "Strateji profili",
            value=str(saved_settings["strategy_profile"]),
        )

        if not allowed_decisions_list:
            allowed_decisions_list = ["NET AL"]

        if st.button("Ayarları Worker İçin Kaydet", use_container_width=True):
            save_robot_settings(
                database,
                account_id=selected_account["account_id"],
                market=selected_market_label,
                minimum_score=float(minimum_score),
                minimum_confidence=float(minimum_confidence),
                minimum_probability=float(minimum_probability),
                max_positions=int(max_positions),
                position_size_pct=float(position_size_pct) / 100,
                allowed_decisions=allowed_decisions_list,
                allowed_risks=allowed_risk_list,
                strategy_profile=strategy_profile,
            )
            st.success(
                f"{selected_market_label} robot ayarları SQLite'a kaydedildi. "
                "Worker sonraki döngüde bu ayarları kullanacak."
            )

    config = RobotConfig(
        starting_balance=float(selected_account["starting_balance"]),
        commission_rate=0.001,
        max_positions=int(max_positions),
        position_size_pct=float(position_size_pct) / 100,
        minimum_score=float(minimum_score),
        minimum_confidence=float(minimum_confidence),
        minimum_probability=float(minimum_probability),
        allowed_decisions=tuple(allowed_decisions_list),
        allowed_risks=tuple(allowed_risk_list),
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

    today_trade_count = int(_safe_robot_metric(robot, "get_today_trade_count", 0) or 0)
    today_realized_profit = float(_safe_robot_metric(robot, "get_today_realized_profit", 0.0) or 0.0)
    today_commission = float(_safe_robot_metric(robot, "get_today_commission", 0.0) or 0.0)
    consecutive_losses = int(_safe_robot_metric(robot, "get_consecutive_losses", 0) or 0)
    risk_lock_reason = str(_safe_robot_metric(robot, "risk_lock_reason", "") or "")

    max_daily_trades = int(getattr(config, "max_daily_trades", 0) or 0)
    max_consecutive_losses = int(getattr(config, "max_consecutive_losses", 0) or 0)
    max_daily_loss_pct = float(getattr(config, "max_daily_loss_pct", 0.0) or 0.0)
    max_daily_commission_pct = float(getattr(config, "max_daily_commission_pct", 0.0) or 0.0)
    risk_per_trade_pct = float(getattr(config, "risk_per_trade_pct", 0.0) or 0.0)

    remaining_trades = max(max_daily_trades - today_trade_count, 0) if max_daily_trades > 0 else 0
    risk_status = "🔴 KİLİTLİ" if risk_lock_reason else "🟢 AKTİF"

    st.subheader("🛡 Risk Manager")
    r1, r2, r3, r4, r5, r6 = st.columns(6)
    r1.metric("Risk Durumu", risk_status)
    r2.metric(
        "Bugünkü İşlem",
        f"{today_trade_count} / {max_daily_trades}" if max_daily_trades > 0 else str(today_trade_count),
        delta=f"{remaining_trades} işlem hakkı" if max_daily_trades > 0 else None,
    )
    r3.metric("Gerçekleşmiş K/Z", _format_money(today_realized_profit, state["currency"]))
    r4.metric("Günlük Komisyon", _format_money(today_commission, state["currency"]))
    r5.metric(
        "Arka Arkaya Zarar",
        f"{consecutive_losses} / {max_consecutive_losses}" if max_consecutive_losses > 0 else str(consecutive_losses),
    )
    r6.metric("İşlem Riski", f"%{risk_per_trade_pct:.2f}")

    if risk_lock_reason:
        st.error("Yeni alımlar Risk Manager tarafından durduruldu: " + risk_lock_reason)
    else:
        st.success("Risk limitleri uygun. Yeni alımlar için risk kilidi bulunmuyor.")

    st.caption(
        f"Günlük zarar limiti: %{max_daily_loss_pct:.2f} · "
        f"Günlük komisyon limiti: %{max_daily_commission_pct:.2f} · "
        "Risk kilidi açık pozisyonların çıkış yönetimini engellemez."
    )


    portfolio_summary = _safe_robot_metric(
        robot,
        "get_portfolio_risk_summary",
        {},
    ) or {}

    portfolio_risk_pct = float(
        portfolio_summary.get("risk_pct", 0.0) or 0.0
    )
    portfolio_exposure_pct = float(
        portfolio_summary.get("exposure_pct", 0.0) or 0.0
    )
    cash_reserve_pct = float(
        portfolio_summary.get("cash_reserve_pct", 0.0) or 0.0
    )
    open_risk_amount = float(
        portfolio_summary.get("open_risk", 0.0) or 0.0
    )
    open_exposure_amount = float(
        portfolio_summary.get("open_exposure", 0.0) or 0.0
    )

    max_portfolio_risk_pct = float(
        getattr(config, "max_portfolio_risk_pct", 0.0) or 0.0
    )
    max_portfolio_exposure_pct = float(
        getattr(config, "max_portfolio_exposure_pct", 0.0) or 0.0
    )
    min_cash_reserve_pct = float(
        getattr(config, "min_cash_reserve_pct", 0.0) or 0.0
    )

    remaining_risk_capacity = max(
        max_portfolio_risk_pct - portfolio_risk_pct,
        0.0,
    )
    remaining_exposure_capacity = max(
        max_portfolio_exposure_pct - portfolio_exposure_pct,
        0.0,
    )

    st.subheader("📊 Portföy Risk Özeti")
    p1, p2, p3, p4, p5, p6 = st.columns(6)

    p1.metric(
        "Toplam Stop Riski",
        f"%{portfolio_risk_pct:.2f}",
        delta=f"Limit %{max_portfolio_risk_pct:.2f}",
    )
    p2.metric(
        "Kalan Risk Kapasitesi",
        f"%{remaining_risk_capacity:.2f}",
    )
    p3.metric(
        "Toplam Maruziyet",
        f"%{portfolio_exposure_pct:.2f}",
        delta=f"Limit %{max_portfolio_exposure_pct:.2f}",
    )
    p4.metric(
        "Kalan Maruziyet",
        f"%{remaining_exposure_capacity:.2f}",
    )
    p5.metric(
        "Nakit Rezervi",
        f"%{cash_reserve_pct:.2f}",
        delta=f"Minimum %{min_cash_reserve_pct:.2f}",
    )
    p6.metric(
        "Açık Risk Tutarı",
        _format_money(open_risk_amount, state["currency"]),
    )

    st.progress(
        min(max(portfolio_risk_pct / max_portfolio_risk_pct, 0.0), 1.0)
        if max_portfolio_risk_pct > 0
        else 0.0,
        text=(
            f"Portföy risk kullanımı: %{portfolio_risk_pct:.2f} / "
            f"%{max_portfolio_risk_pct:.2f}"
        ),
    )
    st.progress(
        min(
            max(
                portfolio_exposure_pct / max_portfolio_exposure_pct,
                0.0,
            ),
            1.0,
        )
        if max_portfolio_exposure_pct > 0
        else 0.0,
        text=(
            f"Portföy maruziyeti: %{portfolio_exposure_pct:.2f} / "
            f"%{max_portfolio_exposure_pct:.2f}"
        ),
    )

    st.caption(
        "Açık pozisyon büyüklüğü: "
        f"{_format_money(open_exposure_amount, state['currency'])} · "
        "Bu panel yalnızca açık sanal pozisyonları ve mevcut stop seviyelerini "
        "kullanır."
    )

    if max_portfolio_risk_pct > 0 and portfolio_risk_pct >= max_portfolio_risk_pct:
        st.error("Portföy stop riski limiti doldu. Yeni pozisyon açılamaz.")
    elif (
        max_portfolio_exposure_pct > 0
        and portfolio_exposure_pct >= max_portfolio_exposure_pct
    ):
        st.error("Portföy maruziyet limiti doldu. Yeni pozisyon açılamaz.")
    elif cash_reserve_pct < min_cash_reserve_pct:
        st.error("Minimum nakit rezervinin altına düşüldü.")
    elif (
        max_portfolio_risk_pct > 0
        and remaining_risk_capacity <= max_portfolio_risk_pct * 0.25
    ):
        st.warning("Portföy risk kapasitesinin büyük bölümü kullanıldı.")
    else:
        st.success("Portföy risk kapasitesi yeni işlemler için uygun.")

    diagnostic = _latest_robot_diagnostics(
        database,
        selected_market_label,
    )

    if diagnostic:
        st.divider()
        st.subheader("🔍 Son Tarama Tanılaması")
        st.caption(
            f"{diagnostic.get('market', '')} / "
            f"{diagnostic.get('universe', '')} • "
            f"{diagnostic.get('scanned_count', 0)} aday incelendi"
        )

        diagnostics = diagnostic.get("diagnostics", [])

        if diagnostics:
            diagnostic_frame = _diagnostics_frame(diagnostics)
            d1, d2, d3, d4 = st.columns(4)

            d1.metric("Gösterilen Varlık", len(diagnostic_frame))
            d2.metric(
                "Güven Engeli",
                int(
                    diagnostic_frame["İşlem Açılmama Nedenleri"]
                    .str.contains("güven", case=False, na=False)
                    .sum()
                ),
            )
            d3.metric(
                "Risk Engeli",
                int(
                    diagnostic_frame["İşlem Açılmama Nedenleri"]
                    .str.contains("risk=", case=False, na=False)
                    .sum()
                ),
            )
            d4.metric(
                "Açık Pozisyon",
                int(diagnostic_frame["Açık Pozisyon"].eq("Evet").sum()),
            )

            reason_counts = _diagnostic_reason_counts(diagnostic_frame)
            chart_data = reason_counts.set_index("Engel")[["Adet"]]

            st.markdown("#### İşlem Açılmama Nedenleri Dağılımı")
            st.bar_chart(chart_data, height=320)

            st.dataframe(
                diagnostic_frame,
                width="stretch",
                hide_index=True,
                column_config={
                    "Kod": st.column_config.TextColumn("Kod", width="small"),
                    "İşlem Açılmama Nedenleri": st.column_config.TextColumn(
                        "İşlem Açılmama Nedenleri",
                        width="large",
                    ),
                    "Neden Sayısı": st.column_config.NumberColumn(
                        "Neden Sayısı",
                        width="small",
                    ),
                    "Açık Pozisyon": st.column_config.TextColumn(
                        "Açık Pozisyon",
                        width="small",
                    ),
                },
            )
        else:
            st.info("İşlem açılmama nedeni bulunamadı.")

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
        "Son SQLite Taramasını Űşle",
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
        candidate_frame = _add_candidate_risk_preview(
            robot,
            state,
            candidate_frame,
        )

        if candidate_frame.empty:
            st.info(
                "Seçilen minimum puan ve güven şartlarına "
                "uygun aday bulunamadı."
            )
        else:
            st.caption(
                "Aday risk önizlemesi yalnızca tahmindir. Gerçek sanal işlem "
                "açılırken bakiye, komisyon ve güncel portföy limitleri yeniden kontrol edilir."
            )
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
                    "Önerilen Miktar",
                    "Önerilen Bütçe",
                    "Tahmini İşlem Riski",
                    "İşlem Riski %",
                    "Sizing Modu",
                    "Portföy Risk Sonrası %",
                    "Portföy Maruziyet Sonrası %",
                    "Önizleme Durumu",
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
                        "Önerilen Miktar": "{:,.4f}",
                        "Önerilen Bütçe": "{:,.2f}",
                        "Tahmini İşlem Riski": "{:,.2f}",
                        "İşlem Riski %": "{:.2f}%",
                        "Portföy Risk Sonrası %": "{:.2f}%",
                        "Portföy Maruziyet Sonrası %": "{:.2f}%",
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
        positions = positions.copy()
        quantity_numeric = pd.to_numeric(positions["quantity"], errors="coerce").fillna(0.0)
        entry_numeric = pd.to_numeric(positions["entry_price"], errors="coerce").fillna(0.0)
        stop_numeric = pd.to_numeric(positions["stop_price"], errors="coerce").fillna(0.0)

        positions["position_value"] = quantity_numeric * entry_numeric
        positions["stop_distance_pct"] = (
            ((entry_numeric - stop_numeric) / entry_numeric.replace(0, pd.NA)) * 100
        )
        positions["estimated_risk"] = quantity_numeric * (entry_numeric - stop_numeric).clip(lower=0)
        reference_balance = float(state.get("starting_balance") or config.starting_balance or 0.0)
        positions["portfolio_pct"] = (
            positions["position_value"] / reference_balance * 100
            if reference_balance > 0
            else 0.0
        )

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
                "position_value": "Pozisyon Değeri",
                "stop_distance_pct": "Stop Mesafesi %",
                "estimated_risk": "Tahmini Risk",
                "portfolio_pct": "Portföy %",
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
                    "Pozisyon Değeri": "{:,.2f}",
                    "Stop Mesafesi %": "{:.2f}%",
                    "Tahmini Risk": "{:,.2f}",
                    "Portföy %": "{:.2f}%",
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
                "MANUEL SATIŰNYAL ZAYIFLADI",
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
        _render_trade_intelligence_summary(history)

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
                "entry_price": "Giriş Fiyatı",
                "exit_price": "Çıkış Fiyatı",
                "profit_pct": "Kâr %",
                "holding_minutes": "Süre (dk)",
                "mfe_pct": "MFE %",
                "mae_pct": "MAE %",
                "risk_pct": "Risk %",
                "reward_pct": "Ödül %",
                "risk_reward": "Risk/Ödül",
                "entry_efficiency": "Giriş Verimi",
                "exit_efficiency": "Çıkış Verimi",
                "trade_quality_score": "Kalite Puanı",
                "trade_grade": "İşlem Notu",
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
                    "Giriş Fiyatı": "{:,.4f}",
                    "Çıkış Fiyatı": "{:,.4f}",
                    "Kâr %": "{:+.2f}%",
                    "Süre (dk)": "{:,.0f}",
                    "MFE %": "{:+.2f}%",
                    "MAE %": "{:+.2f}%",
                    "Risk %": "{:.2f}%",
                    "Ödül %": "{:.2f}%",
                    "Risk/Ödül": "{:.2f}",
                    "Giriş Verimi": "{:.1f}",
                    "Çıkış Verimi": "{:.1f}",
                    "Kalite Puanı": "{:.1f}",
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
            - Risk bazlı pozisyon büyüklüğü: **{"Aktif" if getattr(config, "risk_based_position_sizing", False) else "Kapalı"}**
            - İşlem başına azami risk: **%{getattr(config, "risk_per_trade_pct", 0.0):.2f}**
            - Günlük zarar limiti: **%{getattr(config, "max_daily_loss_pct", 0.0):.2f}**
            - Günlük işlem limiti: **{getattr(config, "max_daily_trades", 0)}**
            - Arka arkaya zarar limiti: **{getattr(config, "max_consecutive_losses", 0)}**
            - Tek yön komisyon: **%{config.commission_rate * 100:.2f}**
            - Strateji profili: **{config.strategy_profile}**
            - Aynı varlıkta ikinci açık pozisyon açılmaz.
            - Robot gerçek emir göndermez.
            '''
        )
