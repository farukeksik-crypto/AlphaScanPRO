from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from io import StringIO
import html as html_lib
import re
from typing import Iterable

import pandas as pd
import requests
from bs4 import BeautifulSoup

KAP_BASE = "https://kap.org.tr"
BIST_COMPANIES_URL = f"{KAP_BASE}/tr/bist-sirketler"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
)


@dataclass(frozen=True)
class KapFinancialResult:
    symbol: str
    company_name: str
    company_url: str
    financial_url: str
    fetched_at: datetime
    latest_period: str | None
    currency_scale: str | None
    tables: list[tuple[str, pd.DataFrame]]


def _get(url: str, timeout: int = 25) -> requests.Response:
    response = requests.get(
        url,
        timeout=timeout,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.7",
            "Cache-Control": "no-cache",
        },
    )
    response.raise_for_status()
    return response


def _normalise_symbol(value: str) -> str:
    return value.strip().upper().replace(".IS", "")


def _find_company_link(symbol: str) -> tuple[str, str]:
    wanted = _normalise_symbol(symbol)
    page = _get(BIST_COMPANIES_URL).text
    soup = BeautifulSoup(page, "html.parser")

    for anchor in soup.find_all("a", href=True):
        text = " ".join(anchor.get_text(" ", strip=True).split())
        href = anchor.get("href", "")
        if "/sirket-bilgileri/ozet/" not in href:
            continue
        first_token = text.split()[0].upper() if text else ""
        if first_token == wanted or re.search(rf"(^|\s){re.escape(wanted)}($|\s)", text.upper()):
            absolute = href if href.startswith("http") else f"{KAP_BASE}{href}"
            return text, absolute

    # Yeni Next.js sayfasında bağlantılar bazen yalnızca uçuş verisinde bulunur.
    link_pattern = re.compile(
        rf'href\\?"?:\\?"?(/tr/sirket-bilgileri/ozet/[^"\\]+).*?{re.escape(wanted)}',
        flags=re.IGNORECASE | re.DOTALL,
    )
    match = link_pattern.search(page)
    if match:
        href = match.group(1).replace("\\u0026", "&")
        return wanted, f"{KAP_BASE}{href}"

    raise LookupError(f"{wanted} kodu KAP BIST şirketleri listesinde bulunamadı.")


def _financial_url_from_company_url(company_url: str) -> str:
    marker = "/sirket-bilgileri/ozet/"
    if marker not in company_url:
        raise ValueError("KAP şirket bağlantısı beklenen biçimde değil.")
    suffix = company_url.split(marker, 1)[1]
    return f"{KAP_BASE}/tr/sirket-finansal-bilgileri/{suffix}"


def _flatten_columns(columns: Iterable[object]) -> list[str]:
    result: list[str] = []
    for column in columns:
        if isinstance(column, tuple):
            parts = [
                str(part).strip()
                for part in column
                if str(part).strip() and not str(part).startswith("Unnamed")
            ]
            value = " / ".join(dict.fromkeys(parts))
        else:
            value = str(column).strip()
        result.append(value or "Değer")
    return result


def _clean_table(frame: pd.DataFrame) -> pd.DataFrame:
    table = frame.copy()
    table.columns = _flatten_columns(table.columns)
    table = table.dropna(axis=0, how="all").dropna(axis=1, how="all")
    return table.reset_index(drop=True)


def _table_title(table: pd.DataFrame, index: int) -> str:
    sample = " ".join(str(value) for value in table.head(8).astype(str).values.ravel()).upper()
    if "FİNANSAL DURUM" in sample or "DÖNEN VARLIKLAR" in sample or "TOPLAM VARLIKLAR" in sample:
        return "Finansal Durum Tablosu"
    if "KAR VEYA ZARAR" in sample or "KÂR VEYA ZARAR" in sample or "HASILAT" in sample or "NET DÖNEM" in sample:
        return "Kâr veya Zarar Tablosu"
    if "NAKİT AKIŞ" in sample or "İŞLETME FAALİYETLERİNDEN" in sample:
        return "Nakit Akış Tablosu"
    if "ÖZKAYNAK" in sample:
        return "Özkaynak Değişim Tablosu"
    return f"KAP Finansal Tablo {index + 1}"


def _children_values(text: str) -> list[str]:
    values = re.findall(r'children\\?"?:\\?"([^"\\]*)', text)
    cleaned: list[str] = []
    for value in values:
        value = value.replace('\\"', '"').replace('\\n', ' ').replace('\\/', '/')
        value = html_lib.unescape(value).strip()
        if value:
            cleaned.append(value)
    return cleaned


def _parse_next_flight_tables(page: str) -> list[tuple[str, pd.DataFrame]]:
    """KAP'ın Next.js uçuş verisine gömülü özet finansal tablolarını ayrıştırır."""
    periods = sorted(
        set(re.findall(r'(20\d{2}/(?:03|06|09|12))_\d+', page)),
        key=lambda item: (int(item[:4]), int(item[-2:])),
    )
    if not periods:
        return []

    row_markers = list(re.finditer(r'tr\\",\\"(ifrs-[^\\"]+)', page))
    rows_by_table: dict[str, list[list[object]]] = {"bilanco": [], "gelir": []}

    for index, marker in enumerate(row_markers):
        start = marker.start()
        end = row_markers[index + 1].start() if index + 1 < len(row_markers) else min(len(page), start + 12000)
        segment = page[start:end]
        values = _children_values(segment)
        if not values:
            continue

        table_type = None
        for candidate in ("bilanco", "gelir"):
            if re.search(rf'{candidate}_20\d{{2}}/\d{{2}}_\d+', segment):
                table_type = candidate
                break
        if table_type is None:
            continue

        label = values[0]
        period_values: dict[str, str] = {}
        for period in periods:
            pattern = re.compile(
                rf'{table_type}_{re.escape(period)}_\d+.*?children\\?"?:\\?"([^"\\]*)',
                flags=re.DOTALL,
            )
            match = pattern.search(segment)
            if match:
                period_values[period] = html_lib.unescape(match.group(1).replace('\\/', '/')).strip()

        if period_values:
            rows_by_table[table_type].append([label] + [period_values.get(p, "—") for p in periods])

    result: list[tuple[str, pd.DataFrame]] = []
    for table_type, title in (("bilanco", "Finansal Durum Tablosu"), ("gelir", "Kâr veya Zarar Tablosu")):
        rows = rows_by_table[table_type]
        if rows:
            result.append((title, pd.DataFrame(rows, columns=["Finansal Kalem", *periods])))
    return result


def _parse_tables(page: str) -> list[tuple[str, pd.DataFrame]]:
    # Eski/klasik HTML tablo yapısı için.
    raw_tables: list[pd.DataFrame] = []
    try:
        raw_tables = pd.read_html(StringIO(page), displayed_only=False)
    except (ValueError, ImportError):
        raw_tables = []

    cleaned: list[tuple[str, pd.DataFrame]] = []
    seen_titles: dict[str, int] = {}
    for index, frame in enumerate(raw_tables):
        table = _clean_table(frame)
        if table.empty or table.shape[0] < 2 or table.shape[1] < 2:
            continue
        title = _table_title(table, index)
        seen_titles[title] = seen_titles.get(title, 0) + 1
        if seen_titles[title] > 1:
            title = f"{title} ({seen_titles[title]})"
        cleaned.append((title, table))

    flight_tables = _parse_next_flight_tables(page)
    if not cleaned:
        return flight_tables

    existing_titles = {title for title, _ in cleaned}
    cleaned.extend((title, table) for title, table in flight_tables if title not in existing_titles)
    return cleaned


def _extract_periods(tables: list[tuple[str, pd.DataFrame]]) -> list[str]:
    candidates: list[str] = []
    period_pattern = re.compile(r"\b(20\d{2})[/-](0?[1-9]|1[0-2])\b")
    for _, table in tables:
        for column in table.columns:
            for year, month in period_pattern.findall(str(column)):
                candidates.append(f"{year}/{int(month):02d}")
        for value in table.head(6).astype(str).values.ravel():
            for year, month in period_pattern.findall(str(value)):
                candidates.append(f"{year}/{int(month):02d}")
    return sorted(set(candidates), reverse=True)


def _extract_currency_scale(page: str, tables: list[tuple[str, pd.DataFrame]]) -> str | None:
    match = re.search(r'Sunum Para Birimi.*?children\\?"?:\\?"(1000\s*TL|TL|USD|EUR)', page, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).upper().replace(" ", "")
    for _, table in tables:
        text = " ".join(table.head(10).astype(str).values.ravel())
        match = re.search(r"\b(1000\s*TL|TL|USD|EUR)\b", text, flags=re.IGNORECASE)
        if match:
            return match.group(1).upper().replace(" ", "")
    return None


def load_kap_financials(symbol: str) -> KapFinancialResult:
    normalised = _normalise_symbol(symbol)
    company_name, company_url = _find_company_link(normalised)
    financial_url = _financial_url_from_company_url(company_url)
    page = _get(financial_url).text
    tables = _parse_tables(page)

    if not tables:
        raise LookupError(
            f"{normalised} için KAP özet finansal tablo bulunamadı. "
            "KAP sayfa yapısı değişmiş veya finansal veri henüz yayımlanmamış olabilir."
        )

    periods = _extract_periods(tables)
    return KapFinancialResult(
        symbol=normalised,
        company_name=company_name,
        company_url=company_url,
        financial_url=financial_url,
        fetched_at=datetime.now(timezone.utc),
        latest_period=periods[0] if periods else None,
        currency_scale=_extract_currency_scale(page, tables),
        tables=tables,
    )
