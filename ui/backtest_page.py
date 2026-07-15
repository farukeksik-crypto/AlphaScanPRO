from __future__ import annotations

import pandas as pd
import streamlit as st

from engine.backtest_engine import BacktestConfig, run_backtest


CRYPTO_SYMBOLS = {
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

COMMODITY_SYMBOLS = {
    "Altın": "GC=F",
    "Gümüş": "SI=F",
    "WTI Petrol": "CL=F",
    "Brent Petrol": "BZ=F",
    "Bakır": "HG=F",
    "Doğalgaz": "NG=F",
}


def _load_market_data(
    data_engine,
    watchlists: dict,
    market: str,
    selected_label: str,
    interval: str,
) -> tuple[pd.DataFrame, str]:
    if market == "Arındırma 0":
        symbol = (
            selected_label
            if selected_label.endswith(".IS")
            else f"{selected_label}.IS"
        )
        period = "10y" if interval == "1d" else "60d"
        return data_engine.get_yahoo(symbol, period, interval), selected_label

    if market == "Kripto":
        symbol = CRYPTO_SYMBOLS[selected_label]
        return data_engine.get_binance(symbol, interval, 1000), selected_label

    symbol = COMMODITY_SYMBOLS[selected_label]
    period = "10y" if interval == "1d" else "60d"
    return data_engine.get_yahoo(symbol, period, interval), selected_label


def _metric_value(metrics: dict, key: str, suffix: str = "") -> str:
    value = metrics.get(key, 0)

    if isinstance(value, int):
        return f"{value}{suffix}"

    if key == "Kâr Faktörü" and value == float("inf"):
        return "∞"

    return f"{float(value):,.2f}{suffix}"


def render_backtest(data_engine, watchlists: dict):
    st.title("📉 Backtest PRO")
    st.caption(
        "Tarama ile aynı sinyal motorunu kullanır. "
        "Sinyal kapanmış mumda hesaplanır ve işlem sonraki mum açılışında yapılır."
    )

    market = st.radio(
        "Piyasa",
        ["Arındırma 0", "Kripto", "Emtia"],
        horizontal=True,
    )

    if market == "Arındırma 0":
        items = watchlists.get("arindirma_0", [])
        stock_map = {
            item["kod"]: item.get("ad", item["kod"])
            for item in items
        }

        if not stock_map:
            st.warning("Arındırma 0 listesi boş.")
            return

        selected_label = st.selectbox(
            "Hisse",
            list(stock_map),
            format_func=lambda code: f"{code} — {stock_map[code]}",
        )
        interval = st.selectbox(
            "Zaman dilimi",
            ["1d", "1h", "30m"],
            format_func=lambda value: {
                "1d": "Günlük",
                "1h": "1 Saat",
                "30m": "30 Dakika",
            }[value],
        )

    elif market == "Kripto":
        selected_label = st.selectbox(
            "Coin",
            list(CRYPTO_SYMBOLS),
        )
        interval = st.selectbox(
            "Zaman dilimi",
            ["1h", "4h", "1d"],
            format_func=lambda value: {
                "1h": "1 Saat",
                "4h": "4 Saat",
                "1d": "Günlük",
            }[value],
        )

    else:
        selected_label = st.selectbox(
            "Emtia",
            list(COMMODITY_SYMBOLS),
        )
        interval = st.selectbox(
            "Zaman dilimi",
            ["1d", "1h"],
            format_func=lambda value: {
                "1d": "Günlük",
                "1h": "1 Saat",
            }[value],
        )

    st.subheader("Sermaye ve işlem ayarları")

    c1, c2, c3 = st.columns(3)
    initial_cash = c1.number_input(
        "Başlangıç sermayesi",
        min_value=1_000.0,
        value=100_000.0,
        step=10_000.0,
    )
    commission_pct = c2.number_input(
        "Tek yön komisyon (%)",
        min_value=0.0,
        value=0.10,
        step=0.01,
        format="%.2f",
    )
    position_size_pct = c3.slider(
        "İşlemde kullanılacak sermaye (%)",
        min_value=10,
        max_value=100,
        value=95,
        step=5,
    )

    st.subheader("Strateji ayarları")

    c1, c2, c3 = st.columns(3)
    minimum_entry_score = c1.slider(
        "Minimum giriş puanı",
        min_value=50,
        max_value=90,
        value=62,
    )
    exit_score = c2.slider(
        "Sinyal çıkış puanı",
        min_value=20,
        max_value=60,
        value=42,
    )
    max_holding_bars = c3.number_input(
        "Maksimum bekleme mumu",
        min_value=0,
        value=40,
        step=5,
        help="0 seçilirse süreye bağlı çıkış kapatılır.",
    )

    use_signal_exit = st.checkbox(
        "Skor zayıflayınca satış yap",
        value=True,
    )

    entry_choice = st.multiselect(
        "Alım için geçerli kararlar",
        ["NET AL", "AL ADAY"],
        default=["NET AL", "AL ADAY"],
    )

    if st.button("Backtest Başlat", type="primary"):
        if not entry_choice:
            st.error("En az bir alım kararı seçmelisin.")
            return

        try:
            with st.spinner("Veri hazırlanıyor ve geçmiş işlemler hesaplanıyor..."):
                frame, display_name = _load_market_data(
                    data_engine=data_engine,
                    watchlists=watchlists,
                    market=market,
                    selected_label=selected_label,
                    interval=interval,
                )

                config = BacktestConfig(
                    initial_cash=float(initial_cash),
                    commission_rate=float(commission_pct) / 100,
                    position_size_pct=float(position_size_pct) / 100,
                    entry_decisions=tuple(entry_choice),
                    minimum_entry_score=float(minimum_entry_score),
                    exit_score=float(exit_score),
                    use_signal_exit=bool(use_signal_exit),
                    max_holding_bars=int(max_holding_bars),
                )

                result = run_backtest(frame, config)

            st.session_state["backtest_result"] = result
            st.session_state["backtest_title"] = (
                f"{display_name} — {interval}"
            )

        except Exception as exc:
            st.error(f"Backtest çalıştırılamadı: {exc}")
            return

    result = st.session_state.get("backtest_result")
    if not result:
        st.info("Henüz backtest başlatılmadı.")
        return

    if result.get("error"):
        st.error(result["error"])
        return

    metrics = result["metrics"]
    title = st.session_state.get("backtest_title", "Backtest")

    st.subheader(f"Sonuç — {title}")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric(
        "Toplam Getiri",
        _metric_value(metrics, "Toplam Getiri %", "%"),
    )
    c2.metric(
        "Başarı Oranı",
        _metric_value(metrics, "Başarı Oranı %", "%"),
    )
    c3.metric(
        "Kâr Faktörü",
        _metric_value(metrics, "Kâr Faktörü"),
    )
    c4.metric(
        "Maksimum Düşüş",
        _metric_value(metrics, "Maksimum Düşüş %", "%"),
    )
    c5.metric(
        "Toplam İşlem",
        _metric_value(metrics, "Toplam İşlem"),
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric(
        "Son Bakiye",
        _metric_value(metrics, "Son Bakiye"),
    )
    c2.metric(
        "Al-Tut",
        _metric_value(metrics, "Al-Tut Getirisi %", "%"),
    )
    c3.metric(
        "Beklenen Değer",
        _metric_value(metrics, "Beklenen Değer"),
    )
    c4.metric(
        "Sharpe",
        _metric_value(metrics, "Sharpe"),
    )
    c5.metric(
        "Toplam Komisyon",
        _metric_value(metrics, "Toplam Komisyon"),
    )

    equity = result["equity"]
    if not equity.empty:
        st.subheader("Portföy Bakiye Eğrisi")
        chart_data = equity.copy()
        chart_data["Tarih"] = pd.to_datetime(chart_data["Tarih"])
        chart_data = chart_data.set_index("Tarih")
        st.line_chart(chart_data[["Bakiye"]])

    trades = result["trades"]
    st.subheader("İşlem Günlüğü")

    if trades.empty:
        st.info(
            "Seçilen ayarlarda işlem oluşmadı. "
            "Minimum giriş puanını azaltmayı veya zaman dilimini değiştirmeyi deneyebilirsin."
        )
        return

    display_trades = trades.copy()
    display_trades["Tarih"] = pd.to_datetime(
        display_trades["Tarih"]
    ).dt.strftime("%d.%m.%Y %H:%M")

    st.dataframe(
        display_trades.style.format(
            {
                "Fiyat": "{:,.4f}",
                "Miktar": "{:,.4f}",
                "Komisyon": "{:,.2f}",
                "Skor": "{:.1f}",
                "Stop": "{:,.4f}",
                "Hedef": "{:,.4f}",
                "Net K/Z": "{:+,.2f}",
                "K/Z %": "{:+.2f}%",
            },
            na_rep="—",
        ),
        width="stretch",
        hide_index=True,
    )

    csv_data = display_trades.to_csv(
        index=False,
    ).encode("utf-8-sig")

    st.download_button(
        "İşlem Günlüğünü CSV İndir",
        csv_data,
        file_name="alphascan_backtest_islemleri.csv",
        mime="text/csv",
    )

    with st.expander("Tüm performans ölçümleri"):
        metric_frame = pd.DataFrame(
            {
                "Ölçüm": list(metrics.keys()),
                "Değer": list(metrics.values()),
            }
        )
        st.dataframe(
            metric_frame,
            width="stretch",
            hide_index=True,
        )