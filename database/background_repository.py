from __future__ import annotations

import json

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


def latest_robot_diagnostics(
    database,
    market: str | None = None,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Son robot i?lem-a?mama tan?lama kay?tlar?n? d?nd?r?r."""
    params: list[Any] = ["ROBOT_DIAGNOSTIC"]
    market_name = str(market or "").strip().upper()

    query = """
        SELECT id, created_at, message
        FROM system_events
        WHERE event_type = ?
        ORDER BY id DESC
        LIMIT ?
    """
    params.append(max(int(limit) * 5, int(limit)))

    with database.connect() as connection:
        records = connection.execute(query, params).fetchall()

    results: list[dict[str, Any]] = []

    for event_id, created_at, message in records:
        try:
            payload = json.loads(str(message or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue

        event_market = str(payload.get("market") or "").strip().upper()
        if market_name and event_market != market_name:
            continue

        diagnostics = payload.get("diagnostics") or []
        if not isinstance(diagnostics, list):
            diagnostics = [str(diagnostics)]

        results.append(
            {
                "ID": int(event_id),
                "Tarih": str(created_at or ""),
                "Piyasa": event_market,
                "Evren": str(payload.get("universe") or ""),
                "Taranan": int(payload.get("scanned") or 0),
                "Tan?lama": [str(item) for item in diagnostics],
            }
        )

        if len(results) >= int(limit):
            break

    return results



FILTER_REASON_LABELS = {
    "reject_robot_disabled": "Robot kapalı",
    "reject_decision": "Karar uygun değil",
    "reject_score": "Puan yetersiz",
    "reject_confidence": "Güven yetersiz",
    "reject_probability": "Olasılık yetersiz",
    "reject_risk": "Risk engeli",
    "reject_open_position": "Açık pozisyon var",
}


def _filter_decisions_table_exists(connection) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='filter_decisions'"
    ).fetchone()
    return row is not None


def latest_filter_decisions(
    database,
    market: str | None = None,
    *,
    limit: int = 500,
    latest_run_only: bool = True,
) -> pd.DataFrame:
    """DecisionTrace tabanlı son filtre kararlarını kullanıcı dostu biçimde döndürür."""
    market_name = str(market or "").strip().upper()
    with database.connect() as connection:
        if not _filter_decisions_table_exists(connection):
            return pd.DataFrame()

        params: list[Any] = []
        clauses: list[str] = []
        if market_name:
            clauses.append("market = ?")
            params.append(market_name)

        if latest_run_only:
            run_query = "SELECT MAX(run_id) FROM filter_decisions"
            if market_name:
                run_query += " WHERE market = ?"
                run_row = connection.execute(run_query, (market_name,)).fetchone()
            else:
                run_row = connection.execute(run_query).fetchone()
            latest_run_id = run_row[0] if run_row else None
            if latest_run_id is None:
                return pd.DataFrame()
            clauses.append("run_id = ?")
            params.append(int(latest_run_id))

        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        query = f"""
            SELECT *
            FROM filter_decisions
            {where}
            ORDER BY accepted DESC, score DESC, probability DESC, confidence DESC, id DESC
            LIMIT ?
        """
        params.append(max(int(limit), 1))
        return pd.read_sql_query(query, connection, params=params)


def filter_decision_dashboard_snapshot(
    database,
    market: str | None = None,
) -> dict[str, Any]:
    """Son taramanın kabul/red, karar, risk ve engel dağılımını üretir."""
    frame = latest_filter_decisions(database, market, limit=5000, latest_run_only=True)
    empty = {
        "run_id": None,
        "market": str(market or "").strip().upper(),
        "universe": "",
        "created_at": "",
        "scanned": 0,
        "accepted": 0,
        "rejected": 0,
        "acceptance_rate_pct": 0.0,
        "decision_counts": pd.DataFrame(columns=["Karar", "Adet"]),
        "risk_counts": pd.DataFrame(columns=["Risk", "Adet"]),
        "reason_counts": pd.DataFrame(columns=["Engel", "Adet"]),
        "details": pd.DataFrame(),
    }
    if frame.empty:
        return empty

    scanned = int(len(frame))
    accepted = int(frame["accepted"].fillna(0).astype(int).sum())
    rejected = scanned - accepted

    decision_counts = (
        frame["decision"].fillna("Belirsiz").replace("", "Belirsiz")
        .value_counts().rename_axis("Karar").reset_index(name="Adet")
    )
    risk_counts = (
        frame["risk_level"].fillna("Belirsiz").replace("", "Belirsiz")
        .value_counts().rename_axis("Risk").reset_index(name="Adet")
    )

    reason_rows = []
    for column, label in FILTER_REASON_LABELS.items():
        count = int(frame[column].fillna(0).astype(int).sum()) if column in frame else 0
        if count:
            reason_rows.append({"Engel": label, "Adet": count})
    reason_counts = pd.DataFrame(reason_rows, columns=["Engel", "Adet"])
    if not reason_counts.empty:
        reason_counts = reason_counts.sort_values("Adet", ascending=False, ignore_index=True)

    detail_columns = [
        "symbol", "name", "decision", "score", "confidence", "probability",
        "risk_level", "accepted", "reject_reasons", "price", "created_at",
    ]
    details = frame[[c for c in detail_columns if c in frame.columns]].copy()
    details["accepted"] = details["accepted"].fillna(0).astype(int).map({1: "Kabul", 0: "Reddedildi"})
    if "reject_reasons" in details:
        def translate_reasons(value: Any) -> str:
            try:
                codes = json.loads(str(value or "[]"))
            except (TypeError, ValueError, json.JSONDecodeError):
                codes = []
            reverse = {
                "robot_disabled": "Robot kapalı", "decision": "Karar uygun değil",
                "score": "Puan yetersiz", "confidence": "Güven yetersiz",
                "probability": "Olasılık yetersiz", "risk": "Risk engeli",
                "open_position": "Açık pozisyon var",
            }
            return " • ".join(reverse.get(str(code), str(code)) for code in codes) or "—"
        details["reject_reasons"] = details["reject_reasons"].map(translate_reasons)

    details = details.rename(columns={
        "symbol": "Kod", "name": "Ad", "decision": "Karar", "score": "Puan",
        "confidence": "Güven", "probability": "Olasılık %", "risk_level": "Risk",
        "accepted": "Sonuç", "reject_reasons": "İşlem Açılmama Nedenleri",
        "price": "Fiyat", "created_at": "Tarih",
    })

    first = frame.iloc[0]
    return {
        "run_id": int(first.get("run_id") or 0),
        "market": str(first.get("market") or ""),
        "universe": str(first.get("universe") or ""),
        "created_at": str(first.get("created_at") or ""),
        "scanned": scanned,
        "accepted": accepted,
        "rejected": rejected,
        "acceptance_rate_pct": accepted / scanned * 100 if scanned else 0.0,
        "decision_counts": decision_counts,
        "risk_counts": risk_counts,
        "reason_counts": reason_counts,
        "details": details,
    }
