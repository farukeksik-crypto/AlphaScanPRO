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
