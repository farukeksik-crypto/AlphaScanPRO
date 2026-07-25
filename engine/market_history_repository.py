from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

from engine.market_universe import MarketInstrument


class MarketHistoryRepository:
    """
    AlphaScan piyasa geçmişi veritabanı.

    Görevleri:
    - Enstrüman bilgilerini kaydetmek
    - OHLCV mumlarını saklamak
    - Aynı mumu ikinci kez eklememek
    - Güncellenmiş mumları yenilemek
    - Collector çalışma geçmişini kaydetmek

    Çalışan robot veritabanına dokunmaz.

    Varsayılan veritabanı:
        database/market_history.db
    """

    def __init__(
        self,
        database_path: str | Path = "database/market_history.db",
    ) -> None:
        self.database_path = Path(database_path)

        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(
            self.database_path,
            timeout=30,
        )

        connection.row_factory = sqlite3.Row

        try:
            connection.execute(
                "PRAGMA foreign_keys = ON"
            )
            connection.execute(
                "PRAGMA journal_mode = WAL"
            )
            connection.execute(
                "PRAGMA synchronous = NORMAL"
            )
            connection.execute(
                "PRAGMA busy_timeout = 30000"
            )

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
                CREATE TABLE IF NOT EXISTS market_instruments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,

                    market TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    provider_symbol TEXT NOT NULL,
                    name TEXT NOT NULL,
                    instrument_type TEXT NOT NULL,

                    currency TEXT NOT NULL,
                    country TEXT,
                    sector TEXT,

                    enabled INTEGER NOT NULL DEFAULT 1,
                    robot_enabled INTEGER NOT NULL DEFAULT 0,

                    scan_interval_minutes INTEGER NOT NULL,
                    history_period TEXT NOT NULL,
                    candle_interval TEXT NOT NULL,

                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,

                    UNIQUE (market, symbol)
                );

                CREATE TABLE IF NOT EXISTS market_candles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,

                    instrument_id INTEGER NOT NULL,

                    candle_interval TEXT NOT NULL,
                    candle_time TEXT NOT NULL,

                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    adjusted_close REAL,
                    volume REAL,

                    source TEXT NOT NULL,
                    is_complete INTEGER NOT NULL DEFAULT 1,

                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,

                    FOREIGN KEY (instrument_id)
                        REFERENCES market_instruments(id),

                    UNIQUE (
                        instrument_id,
                        candle_interval,
                        candle_time
                    )
                );

                CREATE TABLE IF NOT EXISTS collector_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,

                    market TEXT,
                    symbol TEXT,
                    provider_symbol TEXT,

                    started_at TEXT NOT NULL,
                    completed_at TEXT,

                    status TEXT NOT NULL,

                    requested_period TEXT,
                    requested_interval TEXT,

                    received_rows INTEGER NOT NULL DEFAULT 0,
                    saved_rows INTEGER NOT NULL DEFAULT 0,

                    error_type TEXT,
                    error_message TEXT,

                    metadata_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS
                    idx_market_candles_instrument_time
                ON market_candles (
                    instrument_id,
                    candle_interval,
                    candle_time DESC
                );

                CREATE INDEX IF NOT EXISTS
                    idx_market_candles_time
                ON market_candles (
                    candle_time DESC
                );

                CREATE INDEX IF NOT EXISTS
                    idx_collector_runs_started
                ON collector_runs (
                    started_at DESC
                );

                CREATE INDEX IF NOT EXISTS
                    idx_collector_runs_symbol
                ON collector_runs (
                    market,
                    symbol,
                    started_at DESC
                );
                """
            )

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(
            timespec="seconds",
        )

    @staticmethod
    def _normalize_datetime(value: Any) -> str:
        if isinstance(value, datetime):
            return value.isoformat(
                timespec="seconds",
            )

        text = str(value).strip()

        if not text:
            raise ValueError(
                "Mum zamanı boş olamaz."
            )

        return text

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        if value is None:
            return None

        try:
            numeric = float(value)

        except (TypeError, ValueError):
            return None

        if numeric != numeric:
            return None

        return numeric

    def upsert_instrument(
        self,
        instrument: MarketInstrument,
    ) -> int:
        now = self._now()
        data = instrument.to_dict()

        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO market_instruments (
                    market,
                    symbol,
                    provider_symbol,
                    name,
                    instrument_type,
                    currency,
                    country,
                    sector,
                    enabled,
                    robot_enabled,
                    scan_interval_minutes,
                    history_period,
                    candle_interval,
                    created_at,
                    updated_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?
                )

                ON CONFLICT(market, symbol)
                DO UPDATE SET
                    provider_symbol =
                        excluded.provider_symbol,
                    name =
                        excluded.name,
                    instrument_type =
                        excluded.instrument_type,
                    currency =
                        excluded.currency,
                    country =
                        excluded.country,
                    sector =
                        excluded.sector,
                    enabled =
                        excluded.enabled,
                    robot_enabled =
                        excluded.robot_enabled,
                    scan_interval_minutes =
                        excluded.scan_interval_minutes,
                    history_period =
                        excluded.history_period,
                    candle_interval =
                        excluded.candle_interval,
                    updated_at =
                        excluded.updated_at
                """,
                (
                    data["market"],
                    data["symbol"],
                    data["provider_symbol"],
                    data["name"],
                    data["instrument_type"],
                    data["currency"],
                    data["country"],
                    data["sector"],
                    int(data["enabled"]),
                    int(data["robot_enabled"]),
                    data["scan_interval_minutes"],
                    data["history_period"],
                    data["candle_interval"],
                    now,
                    now,
                ),
            )

            row = connection.execute(
                """
                SELECT id
                FROM market_instruments
                WHERE market = ?
                  AND symbol = ?
                """,
                (
                    data["market"],
                    data["symbol"],
                ),
            ).fetchone()

            if row is None:
                raise RuntimeError(
                    "Enstrüman kaydı oluşturulamadı: "
                    f"{data['market']}/"
                    f"{data['symbol']}"
                )

            return int(row["id"])

    def sync_universe(
        self,
        instruments: Any,
    ) -> int:
        """
        MarketInstrument listesi veya MarketUniverse
        nesnesindeki tüm enstrümanları veritabanına
        kaydeder veya günceller.
        """

        if hasattr(instruments, "list"):
            instruments = instruments.list()

        if not isinstance(instruments, Iterable):
            raise TypeError(
                "sync_universe iterable bir değer bekler."
            )

        count = 0

        for instrument in instruments:
            if not isinstance(
                instrument,
                MarketInstrument,
            ):
                raise TypeError(
                    "sync_universe yalnızca "
                    "MarketInstrument nesneleri "
                    "kabul eder."
                )

            self.upsert_instrument(
                instrument,
            )

            count += 1

        return count

    def save_candles(
        self,
        instrument: MarketInstrument,
        candles: Iterable[dict[str, Any]],
        *,
        candle_interval: str | None = None,
        source: str = "YFINANCE",
    ) -> int:
        instrument_id = self.upsert_instrument(
            instrument,
        )

        interval = (
            candle_interval
            or instrument.candle_interval
        ).strip()

        if not interval:
            raise ValueError(
                "Mum zaman aralığı boş olamaz."
            )

        now = self._now()
        saved_rows = 0

        with self._connection() as connection:
            for candle in candles:
                candle_time = (
                    self._normalize_datetime(
                        candle.get("candle_time")
                        or candle.get("datetime")
                        or candle.get("date")
                        or candle.get("timestamp")
                    )
                )

                connection.execute(
                    """
                    INSERT INTO market_candles (
                        instrument_id,
                        candle_interval,
                        candle_time,
                        open,
                        high,
                        low,
                        close,
                        adjusted_close,
                        volume,
                        source,
                        is_complete,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?
                    )

                    ON CONFLICT(
                        instrument_id,
                        candle_interval,
                        candle_time
                    )
                    DO UPDATE SET
                        open =
                            excluded.open,
                        high =
                            excluded.high,
                        low =
                            excluded.low,
                        close =
                            excluded.close,
                        adjusted_close =
                            excluded.adjusted_close,
                        volume =
                            excluded.volume,
                        source =
                            excluded.source,
                        is_complete =
                            excluded.is_complete,
                        updated_at =
                            excluded.updated_at
                    """,
                    (
                        instrument_id,
                        interval,
                        candle_time,
                        self._safe_float(
                            candle.get("open")
                        ),
                        self._safe_float(
                            candle.get("high")
                        ),
                        self._safe_float(
                            candle.get("low")
                        ),
                        self._safe_float(
                            candle.get("close")
                        ),
                        self._safe_float(
                            candle.get(
                                "adjusted_close"
                            )
                        ),
                        self._safe_float(
                            candle.get("volume")
                        ),
                        source.strip().upper(),
                        int(
                            bool(
                                candle.get(
                                    "is_complete",
                                    True,
                                )
                            )
                        ),
                        now,
                        now,
                    ),
                )

                saved_rows += 1

        return saved_rows

    def get_latest_candles(
        self,
        market: str,
        symbol: str,
        *,
        candle_interval: str = "1h",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        market = market.strip().upper()
        symbol = symbol.strip().upper()
        candle_interval = candle_interval.strip()
        limit = max(
            1,
            int(limit),
        )

        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    mi.market,
                    mi.symbol,
                    mi.provider_symbol,
                    mc.candle_interval,
                    mc.candle_time,
                    mc.open,
                    mc.high,
                    mc.low,
                    mc.close,
                    mc.adjusted_close,
                    mc.volume,
                    mc.source,
                    mc.is_complete
                FROM market_candles mc
                JOIN market_instruments mi
                  ON mi.id = mc.instrument_id
                WHERE mi.market = ?
                  AND mi.symbol = ?
                  AND mc.candle_interval = ?
                ORDER BY mc.candle_time DESC
                LIMIT ?
                """,
                (
                    market,
                    symbol,
                    candle_interval,
                    limit,
                ),
            ).fetchall()

            return [
                dict(row)
                for row in rows
            ]

    def get_last_candle_time(
        self,
        market: str,
        symbol: str,
        *,
        candle_interval: str = "1h",
    ) -> str | None:
        market = market.strip().upper()
        symbol = symbol.strip().upper()
        candle_interval = (
            candle_interval.strip()
        )

        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT
                    MAX(mc.candle_time) AS last_time
                FROM market_candles mc
                JOIN market_instruments mi
                  ON mi.id = mc.instrument_id
                WHERE mi.market = ?
                  AND mi.symbol = ?
                  AND mc.candle_interval = ?
                """,
                (
                    market,
                    symbol,
                    candle_interval,
                ),
            ).fetchone()

            if row is None:
                return None

            return row["last_time"]

    def start_collector_run(
        self,
        instrument: MarketInstrument,
        *,
        requested_period: str,
        requested_interval: str,
    ) -> int:
        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO collector_runs (
                    market,
                    symbol,
                    provider_symbol,
                    started_at,
                    status,
                    requested_period,
                    requested_interval
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    instrument.market.value,
                    instrument.symbol,
                    instrument.provider_symbol,
                    self._now(),
                    "RUNNING",
                    requested_period,
                    requested_interval,
                ),
            )

            return int(
                cursor.lastrowid
            )

    def finish_collector_run(
        self,
        run_id: int,
        *,
        status: str,
        received_rows: int = 0,
        saved_rows: int = 0,
        error: Exception | None = None,
    ) -> None:
        status = status.strip().upper()

        error_type: str | None = None
        error_message: str | None = None

        if error is not None:
            error_type = (
                type(error).__name__
            )
            error_message = str(error)

        with self._connection() as connection:
            connection.execute(
                """
                UPDATE collector_runs
                SET completed_at = ?,
                    status = ?,
                    received_rows = ?,
                    saved_rows = ?,
                    error_type = ?,
                    error_message = ?
                WHERE id = ?
                """,
                (
                    self._now(),
                    status,
                    max(
                        0,
                        int(received_rows),
                    ),
                    max(
                        0,
                        int(saved_rows),
                    ),
                    error_type,
                    error_message,
                    int(run_id),
                ),
            )

    def database_summary(
        self,
    ) -> dict[str, int]:
        tables = (
            "market_instruments",
            "market_candles",
            "collector_runs",
        )

        with self._connection() as connection:
            summary: dict[str, int] = {}

            for table in tables:
                row = connection.execute(
                    f"""
                    SELECT COUNT(*) AS count
                    FROM {table}
                    """
                ).fetchone()

                if row is None:
                    summary[table] = 0

                else:
                    summary[table] = int(
                        row["count"]
                    )

            return summary

    def count_candles_by_market(
        self,
    ) -> dict[str, int]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    mi.market,
                    COUNT(mc.id) AS candle_count
                FROM market_instruments mi
                LEFT JOIN market_candles mc
                  ON mc.instrument_id = mi.id
                GROUP BY mi.market
                ORDER BY mi.market
                """
            ).fetchall()

            return {
                str(row["market"]): int(
                    row["candle_count"]
                )
                for row in rows
            }