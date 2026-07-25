from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterator

from engine.intelligence.company_models import (
    CompanyEvent,
    CurrencyPosition,
    ExportProfile,
)


class IntelligenceRepository:
    """
    AlphaScan Intelligence verilerini ayrı SQLite veritabanında saklar.

    Bu repository:
    - Çalışan robot veritabanına dokunmaz.
    - Finansal dönem geçmişini korur.
    - Döviz pozisyonlarını para birimi bazında saklar.
    - İhracat profillerini dönem bazında saklar.
    - KAP/şirket olaylarında tekrar kaydı engeller.
    """

    def __init__(
        self,
        database_path: str | Path = "database/intelligence.db",
    ) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(
            self.database_path,
            timeout=30,
        )
        connection.row_factory = sqlite3.Row

        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA busy_timeout = 30000")

            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS companies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL UNIQUE,
                    name TEXT,
                    sector TEXT,
                    subsector TEXT,
                    country TEXT NOT NULL DEFAULT 'TR',
                    reporting_currency TEXT NOT NULL DEFAULT 'TRY',
                    website TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS financial_periods (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id INTEGER NOT NULL,
                    period_end TEXT NOT NULL,
                    fiscal_year INTEGER NOT NULL,
                    fiscal_quarter INTEGER,
                    report_type TEXT NOT NULL DEFAULT 'CONSOLIDATED',
                    approved INTEGER NOT NULL DEFAULT 0,
                    source TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,

                    FOREIGN KEY (company_id)
                        REFERENCES companies(id),

                    UNIQUE (
                        company_id,
                        period_end,
                        report_type
                    )
                );

                CREATE TABLE IF NOT EXISTS currency_positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    period_id INTEGER NOT NULL,
                    currency TEXT NOT NULL,

                    financial_assets REAL,
                    financial_liabilities REAL,
                    trade_receivables REAL,
                    trade_payables REAL,
                    cash REAL,
                    bank_loans REAL,
                    lease_liabilities REAL,
                    bond_liabilities REAL,
                    derivative_assets REAL,
                    derivative_liabilities REAL,

                    expected_export_revenue REAL,
                    expected_import_cost REAL,

                    total_assets REAL,
                    total_liabilities REAL,
                    net_position REAL,
                    natural_hedge_amount REAL,
                    adjusted_net_position REAL,

                    source TEXT,
                    quality TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,

                    FOREIGN KEY (period_id)
                        REFERENCES financial_periods(id),

                    UNIQUE (period_id, currency)
                );

                CREATE TABLE IF NOT EXISTS export_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    period_id INTEGER NOT NULL UNIQUE,

                    total_revenue REAL,
                    domestic_revenue REAL,
                    export_revenue REAL,

                    europe_revenue REAL,
                    middle_east_revenue REAL,
                    asia_revenue REAL,
                    america_revenue REAL,
                    africa_revenue REAL,
                    other_foreign_revenue REAL,

                    export_ratio_pct REAL,
                    imported_input_cost REAL,
                    import_dependency_pct REAL,
                    export_order_backlog REAL,

                    export_currencies_json TEXT NOT NULL DEFAULT '[]',
                    export_countries_json TEXT NOT NULL DEFAULT '[]',

                    source TEXT,
                    quality TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,

                    FOREIGN KEY (period_id)
                        REFERENCES financial_periods(id)
                );

                CREATE TABLE IF NOT EXISTS company_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id INTEGER NOT NULL,

                    event_time TEXT NOT NULL,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,

                    source_name TEXT NOT NULL,
                    source_id TEXT,
                    source_url TEXT,

                    summary TEXT,
                    raw_text TEXT,

                    impact TEXT NOT NULL,
                    importance_score REAL,
                    confidence_score REAL,

                    related_amount REAL,
                    related_currency TEXT,

                    process_key TEXT,
                    process_status TEXT,
                    supersedes_source_id TEXT,

                    quality TEXT NOT NULL,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    metadata_json TEXT NOT NULL DEFAULT '{}',

                    created_at TEXT NOT NULL,

                    FOREIGN KEY (company_id)
                        REFERENCES companies(id)
                );

                CREATE UNIQUE INDEX IF NOT EXISTS
                    idx_company_events_source
                ON company_events(source_name, source_id)
                WHERE source_id IS NOT NULL;

                CREATE INDEX IF NOT EXISTS
                    idx_financial_periods_company_date
                ON financial_periods(company_id, period_end DESC);

                CREATE INDEX IF NOT EXISTS
                    idx_currency_positions_period
                ON currency_positions(period_id);

                CREATE INDEX IF NOT EXISTS
                    idx_company_events_company_time
                ON company_events(company_id, event_time DESC);

                CREATE INDEX IF NOT EXISTS
                    idx_company_events_category
                ON company_events(category);
                """
            )

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        normalized = str(symbol).strip().upper()

        if not normalized:
            raise ValueError("Şirket sembolü boş olamaz.")

        return normalized

    @staticmethod
    def _quarter_from_date(period_end: date) -> int:
        month = period_end.month

        if month <= 3:
            return 1
        if month <= 6:
            return 2
        if month <= 9:
            return 3
        return 4

    def upsert_company(
        self,
        symbol: str,
        *,
        name: str | None = None,
        sector: str | None = None,
        subsector: str | None = None,
        country: str = "TR",
        reporting_currency: str = "TRY",
        website: str | None = None,
    ) -> int:
        symbol = self._normalize_symbol(symbol)
        now = self._now()

        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO companies (
                    symbol,
                    name,
                    sector,
                    subsector,
                    country,
                    reporting_currency,
                    website,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)

                ON CONFLICT(symbol) DO UPDATE SET
                    name = COALESCE(excluded.name, companies.name),
                    sector = COALESCE(
                        excluded.sector,
                        companies.sector
                    ),
                    subsector = COALESCE(
                        excluded.subsector,
                        companies.subsector
                    ),
                    country = excluded.country,
                    reporting_currency =
                        excluded.reporting_currency,
                    website = COALESCE(
                        excluded.website,
                        companies.website
                    ),
                    updated_at = excluded.updated_at
                """,
                (
                    symbol,
                    name,
                    sector,
                    subsector,
                    country.strip().upper(),
                    reporting_currency.strip().upper(),
                    website,
                    now,
                    now,
                ),
            )

            row = connection.execute(
                """
                SELECT id
                FROM companies
                WHERE symbol = ?
                """,
                (symbol,),
            ).fetchone()

            if row is None:
                raise RuntimeError(
                    f"Şirket kaydı oluşturulamadı: {symbol}"
                )

            return int(row["id"])

    def get_or_create_period(
        self,
        symbol: str,
        period_end: date,
        *,
        report_type: str = "CONSOLIDATED",
        approved: bool = False,
        source: str | None = None,
    ) -> int:
        company_id = self.upsert_company(symbol)
        report_type = report_type.strip().upper()
        now = self._now()

        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO financial_periods (
                    company_id,
                    period_end,
                    fiscal_year,
                    fiscal_quarter,
                    report_type,
                    approved,
                    source,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)

                ON CONFLICT(
                    company_id,
                    period_end,
                    report_type
                )
                DO UPDATE SET
                    approved = MAX(
                        financial_periods.approved,
                        excluded.approved
                    ),
                    source = COALESCE(
                        excluded.source,
                        financial_periods.source
                    ),
                    updated_at = excluded.updated_at
                """,
                (
                    company_id,
                    period_end.isoformat(),
                    period_end.year,
                    self._quarter_from_date(period_end),
                    report_type,
                    int(approved),
                    source,
                    now,
                    now,
                ),
            )

            row = connection.execute(
                """
                SELECT id
                FROM financial_periods
                WHERE company_id = ?
                  AND period_end = ?
                  AND report_type = ?
                """,
                (
                    company_id,
                    period_end.isoformat(),
                    report_type,
                ),
            ).fetchone()

            if row is None:
                raise RuntimeError(
                    "Finansal dönem kaydı oluşturulamadı."
                )

            return int(row["id"])

    def save_currency_position(
        self,
        symbol: str,
        period_end: date,
        position: CurrencyPosition,
        *,
        report_type: str = "CONSOLIDATED",
    ) -> int:
        period_id = self.get_or_create_period(
            symbol,
            period_end,
            report_type=report_type,
            source=position.source,
        )
        data = position.to_dict()
        now = self._now()

        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO currency_positions (
                    period_id,
                    currency,
                    financial_assets,
                    financial_liabilities,
                    trade_receivables,
                    trade_payables,
                    cash,
                    bank_loans,
                    lease_liabilities,
                    bond_liabilities,
                    derivative_assets,
                    derivative_liabilities,
                    expected_export_revenue,
                    expected_import_cost,
                    total_assets,
                    total_liabilities,
                    net_position,
                    natural_hedge_amount,
                    adjusted_net_position,
                    source,
                    quality,
                    created_at,
                    updated_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )

                ON CONFLICT(period_id, currency)
                DO UPDATE SET
                    financial_assets =
                        excluded.financial_assets,
                    financial_liabilities =
                        excluded.financial_liabilities,
                    trade_receivables =
                        excluded.trade_receivables,
                    trade_payables =
                        excluded.trade_payables,
                    cash = excluded.cash,
                    bank_loans = excluded.bank_loans,
                    lease_liabilities =
                        excluded.lease_liabilities,
                    bond_liabilities =
                        excluded.bond_liabilities,
                    derivative_assets =
                        excluded.derivative_assets,
                    derivative_liabilities =
                        excluded.derivative_liabilities,
                    expected_export_revenue =
                        excluded.expected_export_revenue,
                    expected_import_cost =
                        excluded.expected_import_cost,
                    total_assets = excluded.total_assets,
                    total_liabilities =
                        excluded.total_liabilities,
                    net_position = excluded.net_position,
                    natural_hedge_amount =
                        excluded.natural_hedge_amount,
                    adjusted_net_position =
                        excluded.adjusted_net_position,
                    source = excluded.source,
                    quality = excluded.quality,
                    updated_at = excluded.updated_at
                """,
                (
                    period_id,
                    data["currency"],
                    data["financial_assets"],
                    data["financial_liabilities"],
                    data["trade_receivables"],
                    data["trade_payables"],
                    data["cash"],
                    data["bank_loans"],
                    data["lease_liabilities"],
                    data["bond_liabilities"],
                    data["derivative_assets"],
                    data["derivative_liabilities"],
                    data["expected_export_revenue"],
                    data["expected_import_cost"],
                    data["total_assets"],
                    data["total_liabilities"],
                    data["net_position"],
                    data["natural_hedge_amount"],
                    data["adjusted_net_position"],
                    data["source"],
                    data["quality"],
                    now,
                    now,
                ),
            )

            row = connection.execute(
                """
                SELECT id
                FROM currency_positions
                WHERE period_id = ?
                  AND currency = ?
                """,
                (
                    period_id,
                    data["currency"],
                ),
            ).fetchone()

            if row is None:
                raise RuntimeError(
                    "Döviz pozisyonu kaydedilemedi."
                )

            return int(row["id"])

    def save_export_profile(
        self,
        profile: ExportProfile,
        *,
        report_type: str = "CONSOLIDATED",
    ) -> int:
        period_id = self.get_or_create_period(
            profile.symbol,
            profile.period_end,
            report_type=report_type,
            source=profile.source,
        )
        data = profile.to_dict()
        now = self._now()

        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO export_profiles (
                    period_id,
                    total_revenue,
                    domestic_revenue,
                    export_revenue,
                    europe_revenue,
                    middle_east_revenue,
                    asia_revenue,
                    america_revenue,
                    africa_revenue,
                    other_foreign_revenue,
                    export_ratio_pct,
                    imported_input_cost,
                    import_dependency_pct,
                    export_order_backlog,
                    export_currencies_json,
                    export_countries_json,
                    source,
                    quality,
                    created_at,
                    updated_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )

                ON CONFLICT(period_id)
                DO UPDATE SET
                    total_revenue = excluded.total_revenue,
                    domestic_revenue =
                        excluded.domestic_revenue,
                    export_revenue = excluded.export_revenue,
                    europe_revenue = excluded.europe_revenue,
                    middle_east_revenue =
                        excluded.middle_east_revenue,
                    asia_revenue = excluded.asia_revenue,
                    america_revenue =
                        excluded.america_revenue,
                    africa_revenue = excluded.africa_revenue,
                    other_foreign_revenue =
                        excluded.other_foreign_revenue,
                    export_ratio_pct =
                        excluded.export_ratio_pct,
                    imported_input_cost =
                        excluded.imported_input_cost,
                    import_dependency_pct =
                        excluded.import_dependency_pct,
                    export_order_backlog =
                        excluded.export_order_backlog,
                    export_currencies_json =
                        excluded.export_currencies_json,
                    export_countries_json =
                        excluded.export_countries_json,
                    source = excluded.source,
                    quality = excluded.quality,
                    updated_at = excluded.updated_at
                """,
                (
                    period_id,
                    data["total_revenue"],
                    data["domestic_revenue"],
                    data["export_revenue"],
                    data["europe_revenue"],
                    data["middle_east_revenue"],
                    data["asia_revenue"],
                    data["america_revenue"],
                    data["africa_revenue"],
                    data["other_foreign_revenue"],
                    data["export_ratio_pct"],
                    data["imported_input_cost"],
                    data["import_dependency_pct"],
                    data["export_order_backlog"],
                    json.dumps(
                        data["export_currencies"],
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        data["main_export_countries"],
                        ensure_ascii=False,
                    ),
                    data["source"],
                    data["quality"],
                    now,
                    now,
                ),
            )

            row = connection.execute(
                """
                SELECT id
                FROM export_profiles
                WHERE period_id = ?
                """,
                (period_id,),
            ).fetchone()

            if row is None:
                raise RuntimeError(
                    "İhracat profili kaydedilemedi."
                )

            return int(row["id"])

    def save_company_event(
        self,
        event: CompanyEvent,
    ) -> tuple[int, bool]:
        """
        Dönüş:
            (event_id, yeni_kayıt_mı)

        Aynı source_name + source_id daha önce kaydedilmişse
        ikinci kez eklenmez.
        """
        company_id = self.upsert_company(event.symbol)
        data = event.to_dict()

        with self._connection() as connection:
            if event.source_id:
                existing = connection.execute(
                    """
                    SELECT id
                    FROM company_events
                    WHERE source_name = ?
                      AND source_id = ?
                    """,
                    (
                        event.source_name,
                        event.source_id,
                    ),
                ).fetchone()

                if existing is not None:
                    return int(existing["id"]), False

            cursor = connection.execute(
                """
                INSERT INTO company_events (
                    company_id,
                    event_time,
                    category,
                    title,
                    source_name,
                    source_id,
                    source_url,
                    summary,
                    raw_text,
                    impact,
                    importance_score,
                    confidence_score,
                    related_amount,
                    related_currency,
                    process_key,
                    process_status,
                    supersedes_source_id,
                    quality,
                    tags_json,
                    metadata_json,
                    created_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    company_id,
                    data["event_time"],
                    data["category"],
                    data["title"],
                    data["source_name"],
                    data["source_id"],
                    data["source_url"],
                    data["summary"],
                    data["raw_text"],
                    data["impact"],
                    data["importance_score"],
                    data["confidence_score"],
                    data["related_amount"],
                    data["related_currency"],
                    data["process_key"],
                    data["process_status"],
                    data["supersedes_source_id"],
                    data["quality"],
                    json.dumps(
                        data["tags"],
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        data["metadata"],
                        ensure_ascii=False,
                    ),
                    data["created_at"],
                ),
            )

            return int(cursor.lastrowid), True

    def get_latest_currency_positions(
        self,
        symbol: str,
    ) -> list[dict[str, Any]]:
        symbol = self._normalize_symbol(symbol)

        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    fp.period_end,
                    cp.*
                FROM currency_positions cp
                JOIN financial_periods fp
                  ON fp.id = cp.period_id
                JOIN companies c
                  ON c.id = fp.company_id
                WHERE c.symbol = ?
                  AND fp.period_end = (
                      SELECT MAX(fp2.period_end)
                      FROM financial_periods fp2
                      WHERE fp2.company_id = c.id
                  )
                ORDER BY cp.currency
                """,
                (symbol,),
            ).fetchall()

            return [dict(row) for row in rows]

    def get_export_history(
        self,
        symbol: str,
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        symbol = self._normalize_symbol(symbol)
        limit = max(1, int(limit))

        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    fp.period_end,
                    ep.*
                FROM export_profiles ep
                JOIN financial_periods fp
                  ON fp.id = ep.period_id
                JOIN companies c
                  ON c.id = fp.company_id
                WHERE c.symbol = ?
                ORDER BY fp.period_end DESC
                LIMIT ?
                """,
                (
                    symbol,
                    limit,
                ),
            ).fetchall()

            result: list[dict[str, Any]] = []

            for row in rows:
                item = dict(row)
                item["export_currencies"] = json.loads(
                    item.pop("export_currencies_json") or "[]"
                )
                item["main_export_countries"] = json.loads(
                    item.pop("export_countries_json") or "[]"
                )
                result.append(item)

            return result

    def get_recent_events(
        self,
        symbol: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        symbol = self._normalize_symbol(symbol)
        limit = max(1, int(limit))

        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT ce.*
                FROM company_events ce
                JOIN companies c
                  ON c.id = ce.company_id
                WHERE c.symbol = ?
                ORDER BY ce.event_time DESC
                LIMIT ?
                """,
                (
                    symbol,
                    limit,
                ),
            ).fetchall()

            result: list[dict[str, Any]] = []

            for row in rows:
                item = dict(row)
                item["tags"] = json.loads(
                    item.pop("tags_json") or "[]"
                )
                item["metadata"] = json.loads(
                    item.pop("metadata_json") or "{}"
                )
                result.append(item)

            return result

    def database_summary(self) -> dict[str, int]:
        tables = (
            "companies",
            "financial_periods",
            "currency_positions",
            "export_profiles",
            "company_events",
        )

        with self._connection() as connection:
            summary: dict[str, int] = {}

            for table in tables:
                row = connection.execute(
                    f"SELECT COUNT(*) AS count FROM {table}"
                ).fetchone()
                summary[table] = int(row["count"])

            return summary