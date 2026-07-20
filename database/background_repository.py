from __future__ import annotations

from typing import Any

import pandas as pd

from database.background_migrations import ensure_background_schema


MARKET_LABELS = {
    "BIST": "BIST",
    "KRIPTO": "Kripto",
    "EMTIA": "Emtia",
}


def latest_successful_runs(database) -> pd.DataFrame:
    """Her piyasa için son başarılı background çalışmasını döndürür."""
    ensure_background_schema(database)
    query = """
        SELECT r.*
        FROM background_runs r
        INNER JOIN (
            SELECT market, MAX(id) AS max_id
            FROM background_runs
            WHERE status = 'SUCCESS'
            GROUP BY market
        ) latest ON latest.max_id = r.id
        ORDER BY r.id DESC
    """
    with database.connect() as connection:
        return pd.read_sql_query(query, connection)


def latest_scan_results(
    database,
    market: str | None = None,
    *,
    limit_per_market: int = 500,
) -> list[dict[str, Any]]:
    """
    Son başarılı çalışma(lar)a ait tarama sonuçlarını Robot/Panel sözlüğüne çevirir.

    Eski Streamlit session_state bağımlılığını kaldırmak için tek veri kaynağı SQLite'tır.
    """
    ensure_background_schema(database)
    params: list[Any] = []
    market_filter = ""
    if market:
        market_filter = "AND market = ?"
        params.append(str(market).upper())

    query = f"""
        WITH latest_runs AS (
            SELECT market, MAX(id) AS run_id
            FROM background_runs
            WHERE status = 'SUCCESS'
            {market_filter}
            GROUP BY market
        )
        SELECT
            s.run_id,
            s.market,
            s.universe,
            s.symbol,
            s.name,
            s.decision,
            s.score,
            s.price,
            s.stop_price,
            s.target1,
            s.target2,
            s.confidence,
            s.confidence_label,
            s.risk_level,
            s.probability,
            s.reason,
            s.created_at
        FROM background_scan_results s
        INNER JOIN latest_runs l ON l.run_id = s.run_id
        ORDER BY s.market, s.score DESC, s.id DESC
    """

    with database.connect() as connection:
        frame = pd.read_sql_query(query, connection, params=params)

    if frame.empty:
        return []

    if limit_per_market > 0:
        frame = frame.groupby("market", group_keys=False).head(int(limit_per_market))

    rows: list[dict[str, Any]] = []
    for record in frame.to_dict("records"):
        rows.append(
            {
                "Kod": str(record.get("symbol") or ""),
                "Hisse": str(record.get("name") or record.get("symbol") or ""),
                "Ad": str(record.get("name") or record.get("symbol") or ""),
                "Karar": str(record.get("decision") or ""),
                "Puan": float(record.get("score") or 0),
                "Fiyat": float(record.get("price") or 0),
                "Stop": float(record.get("stop_price") or 0),
                "Hedef 1": float(record.get("target1") or 0),
                "Hedef 2": float(record.get("target2") or 0),
                "Güven": float(record.get("confidence") or 0),
                "Güven Durumu": str(record.get("confidence_label") or ""),
                "Risk": str(record.get("risk_level") or ""),
                "Başarı Göstergesi %": float(record.get("probability") or 0),
                "Neden": str(record.get("reason") or ""),
                "AI Analizi": str(record.get("reason") or ""),
                "Piyasa": str(record.get("market") or ""),
                "Evren": str(record.get("universe") or ""),
                "Tarama Zamanı": str(record.get("created_at") or ""),
                "Run ID": int(record.get("run_id") or 0),
            }
        )
    return rows


def latest_results_by_source(database) -> dict[str, list[dict[str, Any]]]:
    rows = latest_scan_results(database)
    sources: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        market = str(row.get("Piyasa") or "")
        universe = str(row.get("Evren") or "")
        label = f"{MARKET_LABELS.get(market, market)} — {universe} (SQLite)"
        sources.setdefault(label, []).append(row)
    return sources


def dashboard_snapshot(database, bist_universe: str = "arindirma_0") -> dict[str, Any]:
    ensure_background_schema(database)
    rows = latest_scan_results(database, "BIST")
    if bist_universe:
        matching = [row for row in rows if str(row.get("Evren")) == bist_universe]
        if matching:
            rows = matching

    summary = {"NET AL": 0, "AL ADAY": 0, "İZLE": 0, "IZLE": 0, "BEKLE": 0}
    for row in rows:
        decision = str(row.get("Karar") or "")
        if decision in summary:
            summary[decision] += 1
        elif decision == "İZLE":
            summary["İZLE"] += 1

    runs = latest_successful_runs(database)
    last_bist = "Henüz arka plan taraması yok"
    if not runs.empty:
        bist_runs = runs[runs["market"] == "BIST"]
        if not bist_runs.empty:
            last_bist = str(bist_runs.iloc[0].get("finished_at") or bist_runs.iloc[0].get("started_at"))

    top = sorted(rows, key=lambda row: float(row.get("Puan", 0) or 0), reverse=True)[:10]
    return {"summary": summary, "last_scan": last_bist, "top": top}
