from __future__ import annotations

import pandas as pd
import streamlit as st

from engine.market_regime_engine import MarketRegimeEngine
from engine.adaptive_strategy_engine import AdaptiveStrategyEngine
from engine.multi_timeframe_intelligence import MultiTimeframeIntelligence


MARKETS = {
    "Kripto": {"symbols": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"], "default": "BTC/USDT"},
    "BIST": {"symbols": ["XU100", "THYAO", "BIMAS", "ASELS", "TUPRS"], "default": "XU100"},
    "Emtia": {"symbols": ["GC=F", "SI=F", "BZ=F", "CL=F", "HG=F"], "default": "GC=F"},
}


def _load(data_engine, market: str, symbol: str, timeframe: str) -> pd.DataFrame:
    if market == "Kripto":
        return data_engine.get_binance(symbol, timeframe=timeframe, limit=1000)
    yahoo_symbol = symbol
    if market == "BIST":
        yahoo_symbol = "XU100.IS" if symbol == "XU100" else f"{symbol}.IS"
    interval = "1d" if timeframe == "1d" else "1h"
    period = "2y" if interval == "1d" else "60d"
    return data_engine.get_yahoo(yahoo_symbol, period=period, interval=interval)


def _resample_4h(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty or not isinstance(frame.index, pd.DatetimeIndex):
        return frame
    mapping = {
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum",
    }
    usable = {key: value for key, value in mapping.items() if key in frame.columns}
    return frame.resample("4h").agg(usable).dropna() if usable else frame


def _load_timeframes(data_engine, market: str, symbol: str) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for timeframe in ("15m", "1h", "1d"):
        try:
            if market == "Kripto":
                frames[timeframe] = data_engine.get_binance(symbol, timeframe=timeframe, limit=1000)
            else:
                yahoo_symbol = "XU100.IS" if market == "BIST" and symbol == "XU100" else (f"{symbol}.IS" if market == "BIST" else symbol)
                interval = timeframe
                period = "60d" if timeframe in {"15m", "1h"} else "2y"
                frames[timeframe] = data_engine.get_yahoo(yahoo_symbol, period=period, interval=interval)
        except Exception:
            continue
    if market == "Kripto":
        try:
            frames["4h"] = data_engine.get_binance(symbol, timeframe="4h", limit=1000)
        except Exception:
            pass
    elif "1h" in frames:
        frames["4h"] = _resample_4h(frames["1h"])
    return {key: value for key, value in frames.items() if value is not None and not value.empty}


def render_market_intelligence(data_engine) -> None:
    st.title("🧠 Market Intelligence")
    st.caption("Piyasa rejimi, volatilite, trend gücü ve robot risk politikasını tek ekranda izler.")

    c1, c2, c3 = st.columns(3)
    market = c1.selectbox("Piyasa", list(MARKETS))
    symbols = MARKETS[market]["symbols"]
    symbol = c2.selectbox("Referans varlık", symbols, index=symbols.index(MARKETS[market]["default"]))
    timeframe = c3.selectbox("Zaman dilimi", ["1h", "1d"], index=0 if market == "Kripto" else 1)

    try:
        frame = _load(data_engine, market, symbol, timeframe)
    except Exception as exc:
        st.error(f"Piyasa verisi alınamadı: {exc}")
        return

    result = MarketRegimeEngine().analyze_market_data(frame)
    adaptive = AdaptiveStrategyEngine().build_policy(result)
    cols = st.columns(6)
    cols[0].metric("Rejim", result.regime)
    cols[1].metric("Rejim Skoru", f"{result.score:.1f}/100")
    cols[2].metric("Güven", f"%{result.confidence:.1f}")
    cols[3].metric("Volatilite", result.volatility_level, f"ATR %{result.volatility_pct:.2f}")
    cols[4].metric("Risk Çarpanı", f"x{result.risk_multiplier:.2f}")
    cols[5].metric("Robot Modu", result.recommendation)

    if result.allow_new_positions:
        st.success(f"Yeni pozisyona izin var. Hedef nakit: %{result.cash_target_pct:.0f}")
    else:
        st.error(f"Yeni pozisyon kilitli. Hedef nakit: %{result.cash_target_pct:.0f}")

    c1, c2, c3 = st.columns(3)
    c1.metric("Trend Gücü", f"{result.trend_strength:.1f}/100")
    c2.metric("Momentum", f"{result.momentum_score:.1f}/100")
    c3.metric("Likidite", f"{result.liquidity_score:.1f}/100")

    st.subheader("Karar Gerekçeleri")
    for reason in result.reasons:
        st.write(f"• {reason}")

    st.subheader("Robot Politika Özeti")
    policy = pd.DataFrame([
        {"Kural": "Yeni pozisyon", "Değer": "İzin" if result.allow_new_positions else "Kilitli"},
        {"Kural": "İşlem risk çarpanı", "Değer": f"x{result.risk_multiplier:.2f}"},
        {"Kural": "Maksimum pozisyon çarpanı", "Değer": f"x{result.max_positions_multiplier:.2f}"},
        {"Kural": "Hedef nakit", "Değer": f"%{result.cash_target_pct:.0f}"},
    ])
    st.dataframe(policy, use_container_width=True, hide_index=True)

    st.subheader("Adaptif Strateji Politikası")
    adaptive_table = pd.DataFrame([
        {"Ayar": "Profil", "Değer": adaptive.profile},
        {"Ayar": "Minimum giriş puanı", "Değer": f"{adaptive.minimum_entry_score:.1f}"},
        {"Ayar": "Pozisyon çarpanı", "Değer": f"x{adaptive.position_size_multiplier:.2f}"},
        {"Ayar": "Hedef 1 çarpanı", "Değer": f"x{adaptive.target1_multiplier:.2f}"},
        {"Ayar": "Hedef 2 çarpanı", "Değer": f"x{adaptive.target2_multiplier:.2f}"},
        {"Ayar": "ATR trailing", "Değer": f"x{adaptive.trailing_atr_multiplier:.2f}"},
        {"Ayar": "Smart Exit farkı", "Değer": f"{adaptive.smart_exit_score_delta:+d}"},
    ])
    st.dataframe(adaptive_table, use_container_width=True, hide_index=True)
    for item in adaptive.reasons:
        st.caption(f"• {item}")

    st.subheader("Çoklu Zaman Dilimi Matrisi")
    try:
        mtf_frames = _load_timeframes(data_engine, market, symbol)
        mtf = MultiTimeframeIntelligence().analyze_frames(mtf_frames)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Baskın Rejim", mtf.dominant_regime)
        m2.metric("Uyum", f"%{mtf.alignment_score:.1f}")
        m3.metric("Çatışma", mtf.conflict_level)
        m4.metric("MTF Modu", mtf.recommendation)
        matrix = pd.DataFrame([item.to_dict() for item in mtf.timeframes])
        if not matrix.empty:
            matrix = matrix.rename(columns={
                "timeframe": "Zaman Dilimi", "weight": "Ağırlık", "regime": "Rejim",
                "score": "Skor", "confidence": "Güven", "direction": "Yön",
                "allow_new_positions": "Yeni Pozisyon",
            })
            st.dataframe(matrix, use_container_width=True, hide_index=True)
        for item in mtf.reasons:
            st.caption(f"• {item}")
    except Exception as exc:
        st.warning(f"Çoklu zaman dilimi analizi üretilemedi: {exc}")

