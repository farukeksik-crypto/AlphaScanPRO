from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from config.market_universes import (
    BIST_UNIVERSES,
    get_bist_universe,
    get_crypto_groups,
    get_crypto_pairs,
)
from engine.backtest_analyzer import analyze_backtest
from engine.backtest_engine import BacktestConfig, run_backtest


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
    selected_universe: str | None = None,
    selected_crypto_group: str | None = None,
) -> tuple[pd.DataFrame, str]:
    if market == "BIST":
        symbol = selected_label if selected_label.endswith(".IS") else f"{selected_label}.IS"
        period = "10y" if interval == "1d" else "60d"
        return data_engine.get_yahoo(symbol, period, interval), selected_label

    if market == "Kripto":
        pairs = get_crypto_pairs(selected_crypto_group)
        symbol = pairs[selected_label]
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


def _build_bist_map(
    watchlists: dict,
    selected_universe: str,
) -> dict[str, str]:
    if selected_universe == "Arındırma 0":
        items = watchlists.get("arindirma_0", [])
    else:
        items = get_bist_universe(selected_universe)

    result: dict[str, str] = {}

    for item in items:
        code = str(item.get("kod", "")).strip()
        if not code:
            continue
        result[code] = str(item.get("ad", code))

    return result


def _render_intelligent_analysis(result: dict):
    analysis = analyze_backtest(result)

    st.divider()
    st.subheader("🧠 Backtest Akıllı Analiz")

    health_score = float(analysis.get("health_score", 0))

    score_col, status_col = st.columns(2)

    score_col.metric(
        "Strateji Sağlık Puanı",
        f"{health_score:.1f} / 100",
    )

    if health_score >= 80:
        health_status = "Güçlü"
    elif health_score >= 65:
        health_status = "Geliştirilebilir"
    elif health_score >= 50:
        health_status = "Zayıf"
    else:
        health_status = "Riskli"

    status_col.metric(
        "Strateji Durumu",
        health_status,
    )

    summary = analysis.get("summary", {})

    s1, s2, s3 = st.columns(3)

    s1.metric(
        "Net Kâr",
        f"{float(summary.get('net_profit', 0)):,.2f}",
    )

    s2.metric(
        "Komisyon / Brüt Kâr",
        f"%{float(summary.get('commission_share_pct', 0)):.2f}",
    )

    s3.metric(
        "İlk 3 İşlemin Kâr Payı",
        f"%{float(summary.get('top_3_profit_share_pct', 0)):.2f}",
    )

    strengths = analysis.get("strengths", [])
    warnings = analysis.get("warnings", [])
    recommendations = analysis.get("recommendations", [])

    if strengths:
        st.success(
            "**Güçlü yönler**\n\n"
            + "\n".join(f"- {item}" for item in strengths)
        )

    if warnings:
        st.warning(
            "**Uyarılar**\n\n"
            + "\n".join(f"- {item}" for item in warnings)
        )

    if recommendations:
        st.info(
            "**Test edilmesi önerilen fikirler**\n\n"
            + "\n".join(f"- {item}" for item in recommendations)
            + "\n\nBu öneriler ayrı backtestlerle doğrulanmalıdır."
        )

    exit_analysis = analysis.get(
        "exit_reason_analysis",
        pd.DataFrame(),
    )

    if not exit_analysis.empty:
        st.subheader("Çıkış Nedeni Analizi")

        st.dataframe(
            exit_analysis.style.format(
                {
                    "Toplam_KZ": "{:+,.2f}",
                    "Ortalama_KZ": "{:+,.2f}",
                    "Başarı_Oranı": "{:.2f}%",
                }
            ),
            width="stretch",
            hide_index=True,
        )

    entry_score_analysis = analysis.get(
        "entry_score_analysis",
        analysis.get(
            "score_band_analysis",
            pd.DataFrame(),
        ),
    )

    if not entry_score_analysis.empty:
        st.subheader("Giriş Skoru Analizi")

        st.dataframe(
            entry_score_analysis.style.format(
                {
                    "Toplam_KZ": "{:+,.2f}",
                    "Ortalama_KZ": "{:+,.2f}",
                    "Medyan_KZ": "{:+,.2f}",
                    "Başarı_Oranı": "{:.2f}%",
                }
            ),
            width="stretch",
            hide_index=True,
        )

    exit_score_analysis = analysis.get(
        "exit_score_analysis",
        pd.DataFrame(),
    )

    if not exit_score_analysis.empty:
        st.subheader("Çıkış Skoru Analizi")

        st.dataframe(
            exit_score_analysis.style.format(
                {
                    "Toplam_KZ": "{:+,.2f}",
                    "Ortalama_KZ": "{:+,.2f}",
                    "Medyan_KZ": "{:+,.2f}",
                    "Başarı_Oranı": "{:.2f}%",
                }
            ),
            width="stretch",
            hide_index=True,
        )


def render_backtest(data_engine, watchlists: dict):
    st.title("📉 Backtest PRO v3")
    st.caption(
        "Sinyal kapanmış mumda hesaplanır. İşlem varsayılan olarak "
        "sonraki mum açılışında yapılır."
    )

    market = st.radio(
        "Piyasa",
        ["BIST", "Kripto", "Emtia"],
        horizontal=True,
    )

    selected_universe = None
    selected_crypto_group = None

    if market == "BIST":
        universe_options = [
            "Arındırma 0",
            *BIST_UNIVERSES.keys(),
        ]

        selected_universe = st.selectbox(
            "BIST evreni",
            universe_options,
        )

        stock_map = _build_bist_map(
            watchlists,
            selected_universe,
        )

        if not stock_map:
            st.warning(f"{selected_universe} listesi boş.")
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
        selected_crypto_group = st.selectbox(
            "Kripto grubu",
            get_crypto_groups(),
        )

        crypto_pairs = get_crypto_pairs(selected_crypto_group)

        if not crypto_pairs:
            st.warning("Seçilen kripto grubunda varlık bulunamadı.")
            return

        selected_label = st.selectbox(
            "Coin",
            list(crypto_pairs),
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

    st.subheader("Test dönemi")

    today = date.today()
    default_start = today - timedelta(days=365 * 3)

    d1, d2 = st.columns(2)

    start_date = d1.date_input(
        "Başlangıç tarihi",
        value=default_start,
        max_value=today,
    )

    end_date = d2.date_input(
        "Bitiş tarihi",
        value=today,
        min_value=start_date,
        max_value=today,
    )

    st.subheader("Sermaye ve gerçekçilik ayarları")

    c1, c2, c3, c4 = st.columns(4)

    initial_cash = c1.number_input(
        "Başlangıç sermayesi",
        min_value=1_000.0,
        value=1_000_000.0,
        step=100_000.0,
    )

    commission_pct = c2.number_input(
        "Tek yön komisyon (%)",
        min_value=0.0,
        value=0.10,
        step=0.01,
        format="%.2f",
    )

    slippage_pct = c3.number_input(
        "Fiyat kayması (%)",
        min_value=0.0,
        value=0.05,
        step=0.01,
        format="%.2f",
    )

    position_size_pct = c4.slider(
        "Azami pozisyon büyüklüğü (%)",
        min_value=5,
        max_value=100,
        value=25,
        step=5,
    )

    c1, c2, c3 = st.columns(3)

    risk_per_trade_pct = c1.number_input(
        "İşlem başına risk (%)",
        min_value=0.05,
        max_value=5.0,
        value=0.50,
        step=0.05,
        format="%.2f",
    )

    target1_exit_pct = c2.slider(
        "Hedef 1'de satılacak bölüm (%)",
        min_value=0,
        max_value=100,
        value=50,
        step=5,
    )

    close_at_day_end = c3.checkbox(
        "Gün sonunda pozisyonu kapat",
        value=interval != "1d",
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

        if start_date > end_date:
            st.error("Başlangıç tarihi bitiş tarihinden sonra olamaz.")
            return

        try:
            with st.spinner(
                "Veri hazırlanıyor ve geçmiş işlemler hesaplanıyor..."
            ):
                frame, display_name = _load_market_data(
                    data_engine=data_engine,
                    watchlists=watchlists,
                    market=market,
                    selected_label=selected_label,
                    interval=interval,
                    selected_universe=selected_universe,
                    selected_crypto_group=selected_crypto_group,
                )

                if frame.empty:
                    st.error("Seçilen varlık için veri alınamadı.")
                    return

                frame = frame.copy()
                frame.index = pd.to_datetime(frame.index)

                start_ts = pd.Timestamp(start_date)
                end_ts = pd.Timestamp(end_date) + pd.Timedelta(days=1)

                if frame.index.tz is not None:
                    start_ts = start_ts.tz_localize(frame.index.tz)
                    end_ts = end_ts.tz_localize(frame.index.tz)

                frame = frame[
                    (frame.index >= start_ts)
                    & (frame.index < end_ts)
                ]

                config = BacktestConfig(
                    initial_cash=float(initial_cash),
                    commission_rate=float(commission_pct) / 100,
                    slippage_rate=float(slippage_pct) / 100,
                    position_size_pct=float(position_size_pct) / 100,
                    risk_per_trade_pct=float(risk_per_trade_pct) / 100,
                    entry_decisions=tuple(entry_choice),
                    minimum_entry_score=float(minimum_entry_score),
                    exit_score=float(exit_score),
                    use_signal_exit=bool(use_signal_exit),
                    max_holding_bars=int(max_holding_bars),
                    close_at_day_end=bool(close_at_day_end),
                    target1_exit_pct=float(target1_exit_pct) / 100,
                )

                result = run_backtest(frame, config)

            universe_text = (
                selected_universe
                if market == "BIST"
                else selected_crypto_group
                if market == "Kripto"
                else "Emtia"
            )

            st.session_state["backtest_result"] = result
            st.session_state["backtest_title"] = (
                f"{universe_text} — {display_name} — {interval} — "
                f"{start_date.strftime('%d.%m.%Y')} / "
                f"{end_date.strftime('%d.%m.%Y')}"
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
        chart_data = equity.copy()
        chart_data["Tarih"] = pd.to_datetime(chart_data["Tarih"])
        chart_data = chart_data.set_index("Tarih")

        st.subheader("Portföy Bakiye Eğrisi")
        st.line_chart(chart_data[["Bakiye"]])

        if "Drawdown %" in chart_data.columns:
            st.subheader("Drawdown Eğrisi")
            st.line_chart(chart_data[["Drawdown %"]])

        st.subheader("Aylık Performans")

        monthly_equity = (
            chart_data["Bakiye"]
            .resample("ME")
            .last()
            .dropna()
        )

        if not monthly_equity.empty:
            monthly_returns = monthly_equity.pct_change()

            initial_balance = float(
                metrics.get("Başlangıç Bakiye", 0)
            )

            if initial_balance > 0:
                monthly_returns.iloc[0] = (
                    monthly_equity.iloc[0] / initial_balance - 1
                )

            month_names = {
                1: "Ocak",
                2: "Şubat",
                3: "Mart",
                4: "Nisan",
                5: "Mayıs",
                6: "Haziran",
                7: "Temmuz",
                8: "Ağustos",
                9: "Eylül",
                10: "Ekim",
                11: "Kasım",
                12: "Aralık",
            }

            monthly_frame = monthly_returns.reset_index()
            monthly_frame.columns = ["Tarih", "Getiri"]
            monthly_frame["Yıl"] = monthly_frame["Tarih"].dt.year
            monthly_frame["Ay"] = (
                monthly_frame["Tarih"]
                .dt.month
                .map(month_names)
            )
            monthly_frame["Getiri %"] = (
                monthly_frame["Getiri"] * 100
            )

            st.bar_chart(
                monthly_frame.set_index("Tarih")[["Getiri %"]]
            )

            st.dataframe(
                monthly_frame[
                    ["Yıl", "Ay", "Getiri %"]
                ].style.format(
                    {"Getiri %": "{:+.2f}%"}
                ),
                width="stretch",
                hide_index=True,
            )

    trades = result["trades"]

    st.subheader("İşlem Günlüğü")

    if trades.empty:
        st.info(
            "Seçilen ayarlarda işlem oluşmadı. "
            "Minimum giriş puanını azaltmayı deneyebilirsin."
        )
        _render_intelligent_analysis(result)
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
                "Hedef 1": "{:,.4f}",
                "Hedef 2": "{:,.4f}",
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

    _render_intelligent_analysis(result)

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