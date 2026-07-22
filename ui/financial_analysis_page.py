from __future__ import annotations

import math
from typing import Any

import pandas as pd
import streamlit as st
import yfinance as yf

from engine.fundamental_quality import build_financial_quality_report, metrics_frame


def _number(value: Any, suffix: str = "") -> str:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(value):
        return "—"
    if abs(value) >= 1_000_000_000:
        return f"{value / 1_000_000_000:,.2f} Mr {suffix}".strip()
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:,.2f} Mn {suffix}".strip()
    return f"{value:,.2f} {suffix}".strip()


def _percent(value: Any) -> str:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(value):
        return "—"
    return f"%{value * 100:,.2f}"


@st.cache_data(ttl=1800, show_spinner=False)
def _load_financials(symbol: str):
    ticker = yf.Ticker(symbol)
    info = ticker.info or {}
    return info, ticker.income_stmt, ticker.balance_sheet, ticker.cashflow


def _statement_table(frame: pd.DataFrame, limit: int = 30) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    shown = frame.copy().head(limit)
    shown.columns = [str(column.date()) if hasattr(column, "date") else str(column) for column in shown.columns]
    shown.index.name = "Kalem"
    return shown.reset_index()


def render_financial_analysis() -> None:
    st.title("📚 Bilanço Okuma")
    st.caption(
        "BIST şirketlerinin temel finansal verilerini ve finansal tablolarını inceler. "
        "Veriler Yahoo Finance üzerinden alınır; yatırım kararı vermeden önce KAP ile doğrulanmalıdır."
    )

    c1, c2 = st.columns([2, 1])
    raw_symbol = c1.text_input("Hisse kodu", value="BIMAS", help="Örnek: BIMAS, ASELS, THYAO")
    symbol = raw_symbol.strip().upper()
    if symbol and not symbol.endswith(".IS"):
        symbol += ".IS"

    load = c2.button("Bilançoyu Getir", type="primary", use_container_width=True)
    if not load and "financial_last_symbol" not in st.session_state:
        st.info("Bir BIST kodu yazıp **Bilançoyu Getir** düğmesine bas.")
        return
    if load:
        st.session_state["financial_last_symbol"] = symbol
    symbol = st.session_state.get("financial_last_symbol", symbol)

    try:
        with st.spinner(f"{symbol} finansal verileri alınıyor..."):
            info, income, balance, cashflow = _load_financials(symbol)
    except Exception as exc:
        st.error(f"Finansal veriler alınamadı: {exc}")
        return

    company = info.get("longName") or info.get("shortName") or symbol
    st.subheader(company)

    quality = build_financial_quality_report(
        symbol=symbol,
        company_name=company,
        info=info,
        income_statement=income,
        balance_sheet=balance,
        cashflow=cashflow,
    )

    st.markdown("### 🧠 Finansal Kalite Motoru — Sprint 10.21A")
    q1, q2, q3 = st.columns(3)
    q1.metric("Finansal Kalite", f"{quality.overall_score:.1f}/100" if quality.overall_score is not None else "—")
    q2.metric("Genel Not", quality.grade)
    q3.metric("Veri Kapsamı", f"%{quality.coverage_pct:.1f}")
    st.info(quality.summary)

    category_columns = st.columns(len(quality.categories))
    for column, category in zip(category_columns, quality.categories):
        value = f"{category.score:.1f}" if category.score is not None else "—"
        column.metric(category.label, value, help=f"{category.available_metrics}/{category.total_metrics} ölçüt mevcut")

    pos_col, caution_col = st.columns(2)
    with pos_col:
        st.markdown("#### Güçlü Alanlar")
        if quality.positives:
            for item in quality.positives:
                st.success(item)
        else:
            st.info("Yeterli güçlü gösterge belirlenemedi.")
    with caution_col:
        st.markdown("#### Dikkat Gerektiren Alanlar")
        if quality.cautions:
            for item in quality.cautions:
                st.warning(item)
        else:
            st.info("Belirgin zayıf gösterge belirlenemedi.")

    with st.expander("Finansal puanın ayrıntılı hesabı", expanded=False):
        st.dataframe(metrics_frame(quality), width="stretch", hide_index=True)
        st.caption(
            "Eksik veriler sıfır puan sayılmaz. Puan yalnızca mevcut ölçütlerden hesaplanır; "
            "veri kapsamı ayrıca gösterilir. Değerleme oranları sektör karşılaştırması olmadan tek başına karar ölçütü değildir."
        )

    metrics = [
        ("Fiyat", _number(info.get("currentPrice"), "TL")),
        ("Piyasa Değeri", _number(info.get("marketCap"), "TL")),
        ("F/K", _number(info.get("trailingPE"))),
        ("PD/DD", _number(info.get("priceToBook"))),
        ("ROE", _percent(info.get("returnOnEquity"))),
        ("Borç/Özsermaye", _number(info.get("debtToEquity"))),
        ("Kâr Marjı", _percent(info.get("profitMargins"))),
        ("Temettü Verimi", _percent(info.get("dividendYield"))),
    ]
    columns = st.columns(4)
    for index, (label, value) in enumerate(metrics):
        columns[index % 4].metric(label, value)

    positives: list[str] = []
    cautions: list[str] = []
    pe = info.get("trailingPE")
    pb = info.get("priceToBook")
    roe = info.get("returnOnEquity")
    debt = info.get("debtToEquity")
    margin = info.get("profitMargins")

    if isinstance(roe, (int, float)) and roe >= 0.20:
        positives.append("Özsermaye kârlılığı güçlü görünüyor.")
    elif isinstance(roe, (int, float)) and roe < 0.10:
        cautions.append("Özsermaye kârlılığı düşük görünüyor.")
    if isinstance(margin, (int, float)) and margin > 0:
        positives.append("Net kâr marjı pozitif.")
    elif isinstance(margin, (int, float)):
        cautions.append("Net kâr marjı negatif.")
    if isinstance(debt, (int, float)) and debt > 150:
        cautions.append("Borç/özsermaye oranı yüksek olabilir.")
    if isinstance(pe, (int, float)) and pe > 0:
        positives.append("Şirket pozitif kâr üzerinden fiyatlanıyor.")
    if isinstance(pb, (int, float)) and pb > 5:
        cautions.append("PD/DD oranı yüksek; büyüme beklentisi fiyatlanmış olabilir.")

    left, right = st.columns(2)
    with left:
        st.markdown("#### Olumlu Göstergeler")
        if positives:
            for item in positives:
                st.success(item)
        else:
            st.info("Otomatik yorum için yeterli olumlu gösterge bulunamadı.")
    with right:
        st.markdown("#### Dikkat Edilecek Noktalar")
        if cautions:
            for item in cautions:
                st.warning(item)
        else:
            st.info("Belirgin bir uyarı üretilemedi.")

    tabs = st.tabs(["Gelir Tablosu", "Bilanço", "Nakit Akışı", "Ham Şirket Verisi"])
    with tabs[0]:
        table = _statement_table(income)
        st.dataframe(table, width="stretch", hide_index=True) if not table.empty else st.info("Gelir tablosu bulunamadı.")
    with tabs[1]:
        table = _statement_table(balance)
        st.dataframe(table, width="stretch", hide_index=True) if not table.empty else st.info("Bilanço bulunamadı.")
    with tabs[2]:
        table = _statement_table(cashflow)
        st.dataframe(table, width="stretch", hide_index=True) if not table.empty else st.info("Nakit akış tablosu bulunamadı.")
    with tabs[3]:
        selected = {
            key: info.get(key)
            for key in [
                "sector", "industry", "website", "fullTimeEmployees", "totalRevenue",
                "revenueGrowth", "earningsGrowth", "grossMargins", "operatingMargins",
                "freeCashflow", "totalCash", "totalDebt", "bookValue", "beta",
            ]
        }
        st.json(selected)
