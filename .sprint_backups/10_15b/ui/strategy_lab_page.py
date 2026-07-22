from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from config.market_universes import (
    BIST_UNIVERSES, get_bist_universe, get_crypto_groups, get_crypto_pairs,
)
from engine.ai.parameter_lab import best_profile, run_parameter_lab
from engine.ai.walk_forward_lab import (
    add_parameter_robustness, best_robust_profile, best_walk_forward_profile, run_walk_forward_lab,
)
from engine.backtest_engine import BacktestConfig, run_backtest


def _bist_map(watchlists: dict, universe: str) -> dict[str, str]:
    items = watchlists.get("arindirma_0", []) if universe == "Arındırma 0" else get_bist_universe(universe)
    return {
        str(item.get("kod", "")).strip(): str(item.get("ad", item.get("kod", "")))
        for item in items if str(item.get("kod", "")).strip()
    }


def _load(data_engine, market, symbol, interval, crypto_group):
    if market == "BIST":
        yahoo_symbol = symbol if symbol.endswith(".IS") else f"{symbol}.IS"
        return data_engine.get_yahoo(yahoo_symbol, "10y" if interval == "1d" else "60d", interval)
    return data_engine.get_binance(get_crypto_pairs(crypto_group)[symbol], interval, 1000)


def render_strategy_lab(data_engine, watchlists: dict):
    st.title("🧪 Strategy Lab PRO V3")
    st.warning(
        "Walk-Forward PRO veriyi eğitim ve doğrulama dönemlerine ayırır. "
        "Bu yöntem aşırı uyum riskini azaltır fakat tamamen ortadan kaldırmaz."
    )

    mode = st.radio(
        "Test yöntemi",
        ["Walk-Forward PRO", "Klasik Parametre Tarama"],
        horizontal=True,
    )
    market = st.radio("Piyasa", ["BIST", "Kripto"], horizontal=True)
    crypto_group = None

    if market == "BIST":
        universe = st.selectbox("BIST evreni", ["Arındırma 0", *BIST_UNIVERSES.keys()])
        symbols = _bist_map(watchlists, universe)
        if not symbols:
            st.warning("Seçilen evrende hisse bulunamadı.")
            return
        symbol = st.selectbox("Hisse", list(symbols), format_func=lambda x: f"{x} — {symbols[x]}")
        interval = st.selectbox("Zaman dilimi", ["1d", "1h"])
    else:
        crypto_group = st.selectbox("Kripto grubu", get_crypto_groups())
        pairs = get_crypto_pairs(crypto_group)
        if not pairs:
            st.warning("Coin bulunamadı.")
            return
        symbol = st.selectbox("Coin", list(pairs))
        interval = st.selectbox("Zaman dilimi", ["1h", "4h", "1d"])

    today = date.today()
    c1, c2 = st.columns(2)
    start_date = c1.date_input("Başlangıç", today - timedelta(days=365 * 3), max_value=today)
    end_date = c2.date_input("Bitiş", today, min_value=start_date, max_value=today)

    p1, p2, p3 = st.columns(3)
    entries = p1.multiselect("Giriş puanları", [55, 60, 62, 65, 70, 75, 80, 85], [62, 70, 75, 80])
    exits = p2.multiselect("Çıkış puanları", [25, 30, 35, 40, 42, 45, 50], [35, 42, 50])
    holdings = p3.multiselect("Bekleme mumları", [0, 10, 20, 30, 40, 60], [20, 40, 60])

    count = len(entries) * len(exits) * len(holdings)
    st.metric("Toplam kombinasyon", count)

    train_ratio = 0.70
    folds = 1
    if mode == "Walk-Forward PRO":
        train_ratio = st.slider("İlk eğitim oranı (%)", 50, 85, 60, 5) / 100
        folds = st.slider("Rolling doğrulama fold sayısı", 1, 5, 3, 1)

    c1, c2, c3, c4 = st.columns(4)
    cash = c1.number_input("Başlangıç sermayesi", 1_000.0, value=1_000_000.0, step=100_000.0)
    commission = c2.number_input("Komisyon (%)", 0.0, value=0.10, step=0.01)
    position_pct = c3.slider("Pozisyon büyüklüğü (%)", 5, 100, 25, 5)
    risk_pct = c4.number_input("İşlem başına risk (%)", 0.05, 5.0, 0.50, 0.05)
    decisions = st.multiselect("Alım kararları", ["NET AL", "AL ADAY"], ["NET AL", "AL ADAY"])

    disabled = not entries or not exits or not holdings or not decisions or count > 200
    if count > 200:
        st.error("En fazla 200 kombinasyon seçilebilir.")

    if st.button("Strategy Lab'i Başlat", type="primary", disabled=disabled):
        try:
            with st.spinner(f"{count} kombinasyon test ediliyor..."):
                data = _load(data_engine, market, symbol, interval, crypto_group)
                data = data.copy()
                data.index = pd.to_datetime(data.index)
                start_ts = pd.Timestamp(start_date)
                end_ts = pd.Timestamp(end_date) + pd.Timedelta(days=1)
                if data.index.tz is not None:
                    start_ts = start_ts.tz_localize(data.index.tz)
                    end_ts = end_ts.tz_localize(data.index.tz)
                data = data[(data.index >= start_ts) & (data.index < end_ts)]

                config = BacktestConfig(
                    initial_cash=float(cash),
                    commission_rate=float(commission) / 100,
                    slippage_rate=0.0005,
                    position_size_pct=float(position_pct) / 100,
                    risk_per_trade_pct=float(risk_pct) / 100,
                    entry_decisions=tuple(decisions),
                    minimum_entry_score=62.0,
                    exit_score=42.0,
                    use_signal_exit=True,
                    max_holding_bars=40,
                    close_at_day_end=False,
                    target1_exit_pct=0.50,
                )

                common = dict(
                    data=data, base_config=config, run_backtest=run_backtest,
                    entry_scores=entries, exit_scores=exits, holding_bars=holdings,
                )
                results = (
                    run_walk_forward_lab(**common, train_ratio=train_ratio, folds=folds)
                    if mode == "Walk-Forward PRO"
                    else run_parameter_lab(**common)
                )

            if mode == "Walk-Forward PRO":
                results = add_parameter_robustness(results)
            st.session_state["strategy_lab_v2"] = results
            st.session_state["strategy_lab_mode_v2"] = mode
            st.session_state["strategy_lab_asset_v2"] = f"{market} — {symbol} — {interval}"
        except Exception as exc:
            st.error(f"Strategy Lab çalıştırılamadı: {exc}")
            return

    results = st.session_state.get("strategy_lab_v2")
    stored_mode = st.session_state.get("strategy_lab_mode_v2", mode)
    if results is None or results.empty:
        st.info("Henüz test yapılmadı.")
        return

    st.subheader("Sonuçlar — " + st.session_state.get("strategy_lab_asset_v2", ""))

    if stored_mode == "Walk-Forward PRO":
        best = best_walk_forward_profile(results)
        robust = best_robust_profile(results)
        if best:
            c1, c2, c3, c4, c5, c6 = st.columns(6)
            c1.metric("Giriş", int(best["Minimum Giriş Puanı"]))
            c2.metric("Çıkış", int(best["Çıkış Puanı"]))
            c3.metric("Bekleme", int(best["Maksimum Bekleme"]))
            c4.metric("Doğrulama Getirisi", f"%{best['Doğrulama Getirisi %']:.2f}")
            c5.metric("Pozitif Fold", f"%{best.get('Pozitif Fold %', 0):.0f}")
            c6.metric("Sağlamlık", best["Sağlamlık"])
        if robust:
            risk = robust.get("Aşırı Uyum Riski", "Bilinmiyor")
            st.info(
                "En sağlam parametre platosu: "
                f"G{int(robust['Minimum Giriş Puanı'])} / "
                f"Ç{int(robust['Çıkış Puanı'])} / "
                f"B{int(robust['Maksimum Bekleme'])} — "
                f"parametre sağlamlığı %{robust.get('Parametre Sağlamlığı', 0):.1f}, "
                f"aşırı uyum riski: {risk}."
            )
        format_map = {
            "Eğitim Getirisi %": "{:+.2f}%", "Doğrulama Getirisi %": "{:+.2f}%",
            "Doğrulama Kâr Faktörü": "{:.2f}", "Doğrulama Başarı Oranı %": "{:.2f}%",
            "Doğrulama Maksimum Düşüş %": "{:.2f}%", "Doğrulama Sharpe": "{:.2f}",
            "Walk-Forward Puanı": "{:.2f}", "Pozitif Fold %": "{:.2f}%",
            "Stabilite Puanı": "{:.2f}", "Komşu Ortalama Puan": "{:.2f}",
            "Parametre Sağlamlığı": "{:.2f}",
        }
        chart_col = "Walk-Forward Puanı"
    else:
        best = best_profile(results)
        if best:
            st.success(
                f"En iyi klasik profil: giriş {int(best['Minimum Giriş Puanı'])}, "
                f"çıkış {int(best['Çıkış Puanı'])}, bekleme {int(best['Maksimum Bekleme'])}."
            )
        format_map = {
            "Toplam Getiri %": "{:+.2f}%", "Başarı Oranı %": "{:.2f}%",
            "Kâr Faktörü": "{:.2f}", "Maksimum Düşüş %": "{:.2f}%",
            "Sharpe": "{:.2f}", "Strateji Puanı": "{:.2f}",
        }
        chart_col = "Strateji Puanı"

    st.dataframe(results.style.format(format_map, na_rep="—"), width="stretch", hide_index=True, height=620)

    chart = results[results["Durum"] == "Tamamlandı"].head(20).copy()
    if not chart.empty and chart_col in chart.columns:
        chart["Profil"] = (
            "G" + chart["Minimum Giriş Puanı"].astype(int).astype(str)
            + "-Ç" + chart["Çıkış Puanı"].astype(int).astype(str)
            + "-B" + chart["Maksimum Bekleme"].astype(int).astype(str)
        )
        st.bar_chart(chart.set_index("Profil")[[chart_col]])

    st.download_button(
        "Sonuçları CSV İndir",
        results.to_csv(index=False).encode("utf-8-sig"),
        "alphascan_strategy_lab_pro_v2.csv",
        "text/csv",
    )
