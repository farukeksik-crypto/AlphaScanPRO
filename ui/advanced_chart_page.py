from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from engine.chart_engine import prepare_chart_data


CRYPTO_SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
    "ADA/USDT", "DOGE/USDT", "AVAX/USDT", "LINK/USDT", "DOT/USDT",
    "LTC/USDT", "SUI/USDT", "AAVE/USDT", "INJ/USDT", "HBAR/USDT",
]

BIST_SYMBOLS = [
    "THYAO", "ASELS", "BIMAS", "TUPRS", "EREGL", "KCHOL", "SAHOL",
    "AKBNK", "GARAN", "ISCTR", "YKBNK", "SISE", "FROTO", "TOASO",
    "TCELL", "ENKAI", "PETKM", "PGSUS", "ASTOR", "ALBRK",
]

COMMODITY_SYMBOLS = {
    "Altın": "GC=F",
    "Gümüş": "SI=F",
    "Brent Petrol": "BZ=F",
    "WTI Petrol": "CL=F",
    "Bakır": "HG=F",
    "Doğal Gaz": "NG=F",
}

TIMEFRAMES = {
    "15 Dakika": "15m",
    "1 Saat": "1h",
    "4 Saat": "4h",
    "1 Gün": "1d",
}


def _resample_ohlcv(frame: pd.DataFrame, rule: str) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()

    result = frame.resample(rule).agg(
        {
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        }
    )
    return result.dropna(subset=["Open", "High", "Low", "Close"])


def _load_chart_frame(
    data_engine,
    market: str,
    symbol: str,
    timeframe: str,
    force_refresh: bool,
) -> pd.DataFrame:
    if market == "Kripto":
        return data_engine.get_binance(symbol, timeframe, limit=1000)

    yahoo_symbol = symbol
    if market == "BIST":
        clean_symbol = symbol.strip().upper().replace(".IS", "")
        yahoo_symbol = f"{clean_symbol}.IS"

    if timeframe == "4h":
        hourly = data_engine.get_yahoo(
            yahoo_symbol,
            period="60d",
            interval="1h",
            force_refresh=force_refresh,
        )
        return _resample_ohlcv(hourly, "4h")

    period = "2y" if timeframe == "1d" else "60d"
    yahoo_interval = "1h" if timeframe == "1h" else timeframe

    return data_engine.get_yahoo(
        yahoo_symbol,
        period=period,
        interval=yahoo_interval,
        force_refresh=force_refresh,
    )


def _format_value(value: Any, digits: int = 2) -> str:
    try:
        if value is None or pd.isna(value):
            return "-"
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return "-"


def _normalize_robot_symbol(symbol: str) -> str:
    value = str(symbol or "").strip().upper()
    value = value.replace(".IS", "").replace("/USDT", "").replace("-USDT", "")
    return value


def _load_robot_overlay(database, market: str, symbol: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    if database is None:
        return pd.DataFrame(), pd.DataFrame()

    market_code = {"Kripto": "KRIPTO", "BIST": "BIST", "Emtia": "EMTIA"}.get(market, market.upper())
    normalized_symbol = _normalize_robot_symbol(symbol)

    try:
        with database.connect() as connection:
            trades = pd.read_sql_query(
                """
                SELECT id, symbol, side, quantity, price, commission, profit, created_at,
                       market, decision, reason, strategy_profile, position_id,
                       entry_price, exit_price, profit_pct
                FROM trade_history
                WHERE UPPER(COALESCE(market, '')) = ?
                ORDER BY created_at ASC, id ASC
                """,
                connection,
                params=[market_code],
            )
            positions = pd.read_sql_query(
                """
                SELECT id, symbol, quantity, entry_price, stop_price, target1, target2,
                       opened_at, status, market, entry_reason, strategy_profile,
                       target1_completed
                FROM positions
                WHERE UPPER(COALESCE(market, '')) = ?
                ORDER BY opened_at ASC, id ASC
                """,
                connection,
                params=[market_code],
            )
    except Exception:
        return pd.DataFrame(), pd.DataFrame()

    if not trades.empty:
        trades = trades[trades["symbol"].map(_normalize_robot_symbol) == normalized_symbol].copy()
        trades["created_at"] = pd.to_datetime(trades["created_at"], errors="coerce")
        trades = trades.dropna(subset=["created_at", "price"])

    if not positions.empty:
        positions = positions[positions["symbol"].map(_normalize_robot_symbol) == normalized_symbol].copy()
        positions["opened_at"] = pd.to_datetime(positions["opened_at"], errors="coerce")

    return trades, positions


def _add_robot_overlays(
    figure: go.Figure,
    trades: pd.DataFrame,
    positions: pd.DataFrame,
) -> None:
    if not trades.empty:
        buys = trades[trades["side"].astype(str).str.upper() == "BUY"]
        sells = trades[trades["side"].astype(str).str.upper() == "SELL"]

        if not buys.empty:
            buy_text = buys.apply(
                lambda row: (
                    f"BUY<br>Fiyat: {float(row['price']):,.4f}"
                    f"<br>Miktar: {float(row.get('quantity') or 0):,.4f}"
                    f"<br>Karar: {row.get('decision') or '-'}"
                    f"<br>Neden: {row.get('reason') or '-'}"
                ),
                axis=1,
            )
            figure.add_trace(
                go.Scatter(
                    x=buys["created_at"], y=buys["price"], mode="markers", name="Robot BUY",
                    marker={"symbol": "triangle-up", "size": 14},
                    text=buy_text, hovertemplate="%{text}<extra></extra>",
                ), row=1, col=1,
            )

        if not sells.empty:
            sell_text = sells.apply(
                lambda row: (
                    f"SELL<br>Fiyat: {float(row['price']):,.4f}"
                    f"<br>Kâr/Zarar: {float(row.get('profit') or 0):,.2f}"
                    f"<br>Getiri: {float(row.get('profit_pct') or 0):,.2f}%"
                    f"<br>Neden: {row.get('reason') or '-'}"
                ),
                axis=1,
            )
            figure.add_trace(
                go.Scatter(
                    x=sells["created_at"], y=sells["price"], mode="markers", name="Robot SELL",
                    marker={"symbol": "triangle-down", "size": 14},
                    text=sell_text, hovertemplate="%{text}<extra></extra>",
                ), row=1, col=1,
            )

        if "position_id" in trades.columns:
            for _, group in trades.dropna(subset=["position_id"]).groupby("position_id"):
                group = group.sort_values("created_at")
                buy_rows = group[group["side"].astype(str).str.upper() == "BUY"]
                sell_rows = group[group["side"].astype(str).str.upper() == "SELL"]
                if buy_rows.empty or sell_rows.empty:
                    continue
                entry = buy_rows.iloc[0]
                exit_row = sell_rows.iloc[-1]
                figure.add_trace(
                    go.Scatter(
                        x=[entry["created_at"], exit_row["created_at"]],
                        y=[entry["price"], exit_row["price"]],
                        mode="lines", name="İşlem Bağlantısı",
                        line={"width": 1, "dash": "dot"},
                        showlegend=False, hoverinfo="skip",
                    ), row=1, col=1,
                )

    if not positions.empty:
        open_positions = positions[positions["status"].astype(str).str.upper() == "OPEN"]
        for _, position in open_positions.iterrows():
            levels = (
                ("STOP", position.get("stop_price"), "dash"),
                ("TP1", position.get("target1"), "dot"),
                ("TP2", position.get("target2"), "dot"),
            )
            for label, value, dash in levels:
                if value is None or pd.isna(value) or float(value) <= 0:
                    continue
                figure.add_hline(
                    y=float(value), line_dash=dash, line_width=1.2,
                    annotation_text=f"{label} {float(value):,.4f}",
                    annotation_position="top right", row=1, col=1,
                )


def _build_figure(
    data: pd.DataFrame,
    symbol: str,
    trades: pd.DataFrame | None = None,
    positions: pd.DataFrame | None = None,
) -> go.Figure:
    visible = data.tail(500).copy()

    figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.78, 0.22],
    )

    figure.add_trace(
        go.Candlestick(
            x=visible.index,
            open=visible["Open"],
            high=visible["High"],
            low=visible["Low"],
            close=visible["Close"],
            name=symbol,
        ),
        row=1,
        col=1,
    )

    for column, label in (
        ("EMA20", "EMA 20"),
        ("EMA50", "EMA 50"),
        ("EMA200", "EMA 200"),
    ):
        if column in visible.columns:
            figure.add_trace(
                go.Scatter(
                    x=visible.index,
                    y=visible[column],
                    mode="lines",
                    name=label,
                    line={"width": 1.4},
                ),
                row=1,
                col=1,
            )

    figure.add_trace(
        go.Bar(
            x=visible.index,
            y=visible["Volume"],
            name="Hacim",
            opacity=0.65,
        ),
        row=2,
        col=1,
    )

    if "VOLUME_MA20" in visible.columns:
        figure.add_trace(
            go.Scatter(
                x=visible.index,
                y=visible["VOLUME_MA20"],
                mode="lines",
                name="Hacim Ort. 20",
                line={"width": 1.2},
            ),
            row=2,
            col=1,
        )

    figure.update_layout(
        height=760,
        margin={"l": 10, "r": 10, "t": 45, "b": 10},
        title=f"{symbol} • AlphaScan Gelişmiş Grafik",
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        legend={"orientation": "h", "y": 1.02, "x": 0},
        template="plotly_dark",
    )
    _add_robot_overlays(figure, trades if trades is not None else pd.DataFrame(), positions if positions is not None else pd.DataFrame())

    figure.update_yaxes(title_text="Fiyat", row=1, col=1)
    figure.update_yaxes(title_text="Hacim", row=2, col=1)
    figure.update_xaxes(showspikes=True, spikemode="across", spikesnap="cursor")
    figure.update_yaxes(showspikes=True, spikemode="across", spikesnap="cursor")

    return figure


def render_advanced_chart(data_engine, watchlists: dict | None = None, database=None) -> None:
    st.header("📊 Gelişmiş Grafik")
    st.caption(
        "TradingView benzeri mum grafik, EMA20/50/200 ve hacim görünümü. "
        "Bu ekran gerçek emir göndermez."
    )

    top1, top2, top3, top4 = st.columns([1.1, 1.5, 1.1, 0.8])

    with top1:
        market = st.selectbox("Piyasa", ["Kripto", "BIST", "Emtia"])

    with top2:
        if market == "Kripto":
            symbol = st.selectbox("Sembol", CRYPTO_SYMBOLS)
        elif market == "BIST":
            configured = []
            if watchlists:
                configured = [
                    str(item.get("kod", "")).upper()
                    for item in watchlists.get("arindirma_0", [])
                    if item.get("kod")
                ]
            choices = list(dict.fromkeys(BIST_SYMBOLS + configured))
            selected = st.selectbox("Hazır BIST sembolü", choices)
            custom = st.text_input(
                "Veya BIST kodu yaz",
                value="",
                placeholder="Örnek: ASELS",
            ).strip()
            symbol = custom.upper() if custom else selected
        else:
            commodity_name = st.selectbox("Emtia", list(COMMODITY_SYMBOLS))
            symbol = COMMODITY_SYMBOLS[commodity_name]

    with top3:
        timeframe_label = st.selectbox("Zaman Dilimi", list(TIMEFRAMES))
        timeframe = TIMEFRAMES[timeframe_label]

    with top4:
        st.write("")
        st.write("")
        force_refresh = st.button("🔄 Yenile", use_container_width=True)

    try:
        with st.spinner(f"{symbol} verisi hazırlanıyor..."):
            frame = _load_chart_frame(
                data_engine=data_engine,
                market=market,
                symbol=symbol,
                timeframe=timeframe,
                force_refresh=force_refresh,
            )
            result = prepare_chart_data(frame)
    except Exception as exc:
        st.error(f"Grafik verisi alınamadı: {exc}")
        return

    if not result.get("ok"):
        st.warning(result.get("error", "Grafik hazırlanamadı."))
        return

    chart_data = result["data"]
    latest = result.get("latest", {})
    signal = result.get("signal", {}) or {}

    metric1, metric2, metric3, metric4, metric5, metric6 = st.columns(6)
    metric1.metric("Son Fiyat", _format_value(latest.get("price"), 4))
    metric2.metric("EMA20", _format_value(latest.get("ema20"), 4))
    metric3.metric("EMA50", _format_value(latest.get("ema50"), 4))
    metric4.metric("EMA200", _format_value(latest.get("ema200"), 4))
    metric5.metric("RSI", _format_value(latest.get("rsi"), 1))
    metric6.metric("ADX", _format_value(latest.get("adx"), 1))

    show_robot = st.checkbox("Robot işlemlerini grafikte göster", value=True)
    trades, positions = _load_robot_overlay(database, market, symbol) if show_robot else (pd.DataFrame(), pd.DataFrame())

    st.plotly_chart(
        _build_figure(chart_data, symbol, trades, positions),
        use_container_width=True,
        config={
            "displaylogo": False,
            "scrollZoom": True,
            "modeBarButtonsToRemove": ["lasso2d", "select2d"],
        },
    )

    with st.expander("Son teknik sinyal özeti", expanded=False):
        if signal:
            st.json(signal)
        else:
            st.info("Son mum için teknik sinyal özeti üretilemedi.")

    if show_robot:
        open_count = 0 if positions.empty else int((positions["status"].astype(str).str.upper() == "OPEN").sum())
        closed_sells = pd.DataFrame() if trades.empty else trades[trades["side"].astype(str).str.upper() == "SELL"]
        realized_profit = 0.0 if closed_sells.empty else float(pd.to_numeric(closed_sells["profit"], errors="coerce").fillna(0).sum())
        c1, c2, c3 = st.columns(3)
        c1.metric("Grafikteki Robot Kaydı", int(len(trades)))
        c2.metric("Açık Pozisyon", open_count)
        c3.metric("Gerçekleşen Kâr/Zarar", f"{realized_profit:,.2f}")

        if not trades.empty:
            with st.expander("Robot işlem ayrıntıları", expanded=False):
                table = trades.sort_values("created_at", ascending=False).head(50).copy()
                table = table[["created_at", "side", "price", "quantity", "profit", "profit_pct", "reason"]]
                table.columns = ["Tarih", "İşlem", "Fiyat", "Miktar", "Kâr/Zarar", "Getiri %", "Neden"]
                st.dataframe(table, use_container_width=True, hide_index=True)
        else:
            st.caption("Seçili sembol için kayıtlı robot işlemi bulunamadı.")

    st.info(
        "Sprint 10.11B: robot BUY/SELL işaretleri, açık pozisyon STOP/TP1/TP2 seviyeleri, "
        "işlem bağlantıları ve açıklamalı hover bilgileri etkin."
    )
