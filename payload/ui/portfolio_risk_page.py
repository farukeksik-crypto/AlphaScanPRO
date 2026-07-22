from __future__ import annotations

import pandas as pd
import streamlit as st

from engine.portfolio_risk_analytics import build_portfolio_risk_report
from engine.robot_engine import RobotConfig, RobotEngine


def _money(value: float, currency: str) -> str:
    return f"{float(value):,.2f} {currency}".replace(",", "X").replace(".", ",").replace("X", ".")


def render_portfolio_risk(database) -> None:
    st.title("🛡️ Portföy Risk Merkezi")
    st.caption("Açık pozisyon yoğunluğu, stop riski, kapasite kullanımı ve stres senaryoları.")

    account = st.selectbox(
        "Hesap",
        [
            ("BIST", "bist_main", "TRY"),
            ("KRIPTO", "crypto_main", "USDT"),
            ("EMTIA", "commodity_main", "USD"),
        ],
        format_func=lambda item: item[0],
    )
    market, account_id, currency = account
    config = RobotConfig(market=market, account_id=account_id, currency=currency)
    robot = RobotEngine(database=database, config=config)
    state = robot.get_state()
    frame = robot.get_open_positions()

    equity = max(
        float(state.get("starting_balance") or 0.0) + float(state.get("total_profit") or 0.0),
        float(state.get("balance") or 0.0),
        1.0,
    )
    positions = frame.to_dict("records") if isinstance(frame, pd.DataFrame) else list(frame or [])
    report = build_portfolio_risk_report(
        positions,
        equity=equity,
        max_total_exposure_pct=config.max_portfolio_exposure_pct,
        max_total_risk_pct=config.max_portfolio_risk_pct,
        max_symbol_exposure_pct=config.max_single_position_exposure_pct,
        base_risk_per_trade_pct=config.risk_per_trade_pct,
        daily_loss_pct=max(-float(state.get("daily_profit") or 0.0) / equity * 100, 0.0),
        daily_loss_limit_pct=config.max_daily_loss_pct,
    )

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Risk Seviyesi", report.risk_level)
    c2.metric("Özkaynak", _money(report.equity, currency))
    c3.metric("Maruziyet", f"%{report.exposure_pct:.2f}")
    c4.metric("Stop Riski", f"%{report.stop_risk_pct:.2f}")
    c5.metric("En Büyük Sembol", f"%{report.largest_symbol_pct:.2f}")
    c6.metric("Önerilen İşlem Riski", f"%{report.recommended_risk_per_trade_pct:.2f}")

    if report.warnings:
        for warning in report.warnings:
            st.warning(warning)
    else:
        st.success("Portföy risk limitleri ve yoğunlaşma göstergeleri normal aralıkta.")

    st.subheader("Sembol Yoğunluğu")
    symbol_df = pd.DataFrame(report.symbol_exposure)
    if symbol_df.empty:
        st.info("Açık pozisyon bulunmuyor.")
    else:
        st.dataframe(symbol_df, use_container_width=True, hide_index=True)
        st.bar_chart(symbol_df.set_index("symbol")["exposure_pct"])

    st.subheader("Piyasa / Grup Dağılımı")
    group_df = pd.DataFrame(report.group_exposure)
    if not group_df.empty:
        st.dataframe(group_df, use_container_width=True, hide_index=True)

    st.subheader("Stres Testi")
    stress_df = pd.DataFrame(report.stress_results)
    st.dataframe(stress_df, use_container_width=True, hide_index=True)

    st.caption(
        f"Yoğunlaşma HHI: {report.concentration_hhi:.3f} · "
        f"Etkin pozisyon sayısı: {report.effective_position_count:.2f}. "
        "Stres testi korelasyonların yükseldiği ortak piyasa düşüşünü yaklaşık olarak simüle eder."
    )

    _render_risk_control_console(database, account_id, currency)


def _render_risk_control_console(database, account_id: str, currency: str) -> None:
    from engine.robot_risk_monitor import (
        get_risk_lock,
        list_risk_events,
        set_risk_lock,
        summarize_risk_events,
    )

    st.divider()
    st.subheader("Robot Risk Kontrol Konsolu")
    lock = get_risk_lock(database, account_id)
    status_col, action_col = st.columns([2, 3])
    with status_col:
        if lock["locked"]:
            st.error(f"Acil risk kilidi AKTİF · {lock['reason'] or 'Neden girilmedi'}")
        else:
            st.success("Acil risk kilidi kapalı; robot risk kuralları içinde işlem açabilir.")
        if lock.get("updated_at"):
            st.caption(f"Son güncelleme: {lock['updated_at']}")

    with action_col:
        reason = st.text_input(
            "Kilit nedeni",
            value=lock.get("reason", ""),
            placeholder="Örn. piyasa şoku, veri kaynağı sorunu, manuel inceleme",
            key=f"risk_lock_reason_{account_id}",
        )
        c_lock, c_unlock = st.columns(2)
        if c_lock.button("Acil kilidi etkinleştir", type="primary", key=f"risk_lock_{account_id}"):
            set_risk_lock(database, account_id, locked=True, reason=reason or "Manuel risk kilidi")
            st.rerun()
        if c_unlock.button("Kilidi kaldır", key=f"risk_unlock_{account_id}"):
            set_risk_lock(database, account_id, locked=False, reason="")
            st.rerun()

    summary = summarize_risk_events(database, account_id, limit=500)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Risk Kararı", summary.total_events)
    c2.metric("Onay", f"%{summary.approval_rate_pct:.1f}", summary.approved_count)
    c3.metric("Küçültme", f"%{summary.reduction_rate_pct:.1f}", summary.reduced_count)
    c4.metric("Ret", f"%{summary.rejection_rate_pct:.1f}", summary.rejected_count)
    c5.metric("Engellenen Tutar", _money(summary.blocked_value, currency))

    filter_col, limit_col = st.columns(2)
    event_type = filter_col.selectbox(
        "Karar filtresi",
        ["ALL", "RISK_APPROVED", "RISK_REDUCED", "RISK_REJECTED"],
        format_func=lambda value: {
            "ALL": "Tümü", "RISK_APPROVED": "Onaylanan",
            "RISK_REDUCED": "Küçültülen", "RISK_REJECTED": "Reddedilen",
        }[value],
        key=f"risk_event_type_{account_id}",
    )
    limit = limit_col.selectbox("Gösterilecek kayıt", [25, 50, 100, 250], index=1)
    events = list_risk_events(database, account_id, limit=limit, event_type=event_type)
    if events:
        event_df = pd.DataFrame(events)
        visible = [
            "created_at", "symbol", "event_type", "reason", "message",
            "requested_quantity", "approved_quantity", "requested_value",
            "approved_value", "risk_amount",
        ]
        st.dataframe(event_df[visible], use_container_width=True, hide_index=True)
    else:
        st.info("Bu hesap için henüz risk kararı kaydı bulunmuyor.")

    if summary.top_reasons:
        st.caption("En sık risk nedenleri")
        st.dataframe(pd.DataFrame(summary.top_reasons), use_container_width=True, hide_index=True)
