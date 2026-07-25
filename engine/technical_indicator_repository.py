from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from engine.market_history_repository import (
    MarketHistoryRepository,
)


class TechnicalIndicatorRepository(
    MarketHistoryRepository
):
    """
    Teknik göstergeleri market_history.db içinde saklar.

    Mumlar:
        market_candles

    Göstergeler:
        technical_indicators

    Her gösterge kaydı şu üçlü için benzersizdir:
        instrument_id + candle_interval + candle_time
    """

    def __init__(
        self,
        database_path: str | Path = (
            "database/market_history.db"
        ),
    ) -> None:
        super().__init__(database_path)
        self.initialize_indicator_tables()

    def initialize_indicator_tables(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS
                    technical_indicators (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,

                        instrument_id INTEGER NOT NULL,

                        candle_interval TEXT NOT NULL,
                        candle_time TEXT NOT NULL,

                        close REAL,

                        ema_20 REAL,
                        ema_50 REAL,
                        ema_100 REAL,
                        ema_200 REAL,

                        rsi_14 REAL,

                        macd REAL,
                        macd_signal REAL,
                        macd_histogram REAL,

                        atr_14 REAL,

                        bollinger_middle REAL,
                        bollinger_upper REAL,
                        bollinger_lower REAL,
                        bollinger_width_pct REAL,

                        source TEXT NOT NULL
                            DEFAULT 'ALPHASCAN',

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

                CREATE INDEX IF NOT EXISTS
                    idx_technical_indicators_lookup
                ON technical_indicators (
                    instrument_id,
                    candle_interval,
                    candle_time DESC
                );

                CREATE INDEX IF NOT EXISTS
                    idx_technical_indicators_time
                ON technical_indicators (
                    candle_time DESC
                );
                """
            )

    @staticmethod
    def _safe_float(
        value: Any,
    ) -> float | None:
        if value is None:
            return None

        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None

        if numeric != numeric:
            return None

        if numeric in (
            float("inf"),
            float("-inf"),
        ):
            return None

        return numeric

    def get_candles_chronological(
        self,
        market: str,
        symbol: str,
        *,
        candle_interval: str,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """
        Mumları eskiden yeniye doğru döndürür.

        Gösterge hesaplamalarında zaman sırası
        kritik olduğu için ASC kullanılır.
        """
        market = market.strip().upper()
        symbol = symbol.strip().upper()
        candle_interval = candle_interval.strip()
        limit = max(1, int(limit))

        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM (
                    SELECT
                        mi.id AS instrument_id,
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
                        mc.is_complete

                    FROM market_candles mc

                    JOIN market_instruments mi
                      ON mi.id = mc.instrument_id

                    WHERE mi.market = ?
                      AND mi.symbol = ?
                      AND mc.candle_interval = ?

                    ORDER BY mc.candle_time DESC
                    LIMIT ?
                )
                ORDER BY candle_time ASC
                """,
                (
                    market,
                    symbol,
                    candle_interval,
                    limit,
                ),
            ).fetchall()

            return [dict(row) for row in rows]

    def save_indicator_rows(
        self,
        instrument_id: int,
        rows: Iterable[dict[str, Any]],
        *,
        candle_interval: str,
        source: str = "ALPHASCAN",
    ) -> int:
        now = datetime.now().isoformat(
            timespec="seconds"
        )

        interval = candle_interval.strip()

        if not interval:
            raise ValueError(
                "Gösterge mum aralığı boş olamaz."
            )

        prepared_rows = list(rows)

        with self._connection() as connection:
            for row in prepared_rows:
                candle_time = str(
                    row["candle_time"]
                ).strip()

                if not candle_time:
                    raise ValueError(
                        "Gösterge zamanı boş olamaz."
                    )

                connection.execute(
                    """
                    INSERT INTO technical_indicators (
                        instrument_id,
                        candle_interval,
                        candle_time,

                        close,

                        ema_20,
                        ema_50,
                        ema_100,
                        ema_200,

                        rsi_14,

                        macd,
                        macd_signal,
                        macd_histogram,

                        atr_14,

                        bollinger_middle,
                        bollinger_upper,
                        bollinger_lower,
                        bollinger_width_pct,

                        source,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        ?, ?, ?,
                        ?,
                        ?, ?, ?, ?,
                        ?,
                        ?, ?, ?,
                        ?,
                        ?, ?, ?, ?,
                        ?, ?, ?
                    )

                    ON CONFLICT (
                        instrument_id,
                        candle_interval,
                        candle_time
                    )
                    DO UPDATE SET
                        close = excluded.close,

                        ema_20 = excluded.ema_20,
                        ema_50 = excluded.ema_50,
                        ema_100 = excluded.ema_100,
                        ema_200 = excluded.ema_200,

                        rsi_14 = excluded.rsi_14,

                        macd = excluded.macd,
                        macd_signal =
                            excluded.macd_signal,
                        macd_histogram =
                            excluded.macd_histogram,

                        atr_14 = excluded.atr_14,

                        bollinger_middle =
                            excluded.bollinger_middle,
                        bollinger_upper =
                            excluded.bollinger_upper,
                        bollinger_lower =
                            excluded.bollinger_lower,
                        bollinger_width_pct =
                            excluded.bollinger_width_pct,

                        source = excluded.source,
                        updated_at = excluded.updated_at
                    """,
                    (
                        int(instrument_id),
                        interval,
                        candle_time,

                        self._safe_float(
                            row.get("close")
                        ),

                        self._safe_float(
                            row.get("ema_20")
                        ),
                        self._safe_float(
                            row.get("ema_50")
                        ),
                        self._safe_float(
                            row.get("ema_100")
                        ),
                        self._safe_float(
                            row.get("ema_200")
                        ),

                        self._safe_float(
                            row.get("rsi_14")
                        ),

                        self._safe_float(
                            row.get("macd")
                        ),
                        self._safe_float(
                            row.get("macd_signal")
                        ),
                        self._safe_float(
                            row.get("macd_histogram")
                        ),

                        self._safe_float(
                            row.get("atr_14")
                        ),

                        self._safe_float(
                            row.get(
                                "bollinger_middle"
                            )
                        ),
                        self._safe_float(
                            row.get(
                                "bollinger_upper"
                            )
                        ),
                        self._safe_float(
                            row.get(
                                "bollinger_lower"
                            )
                        ),
                        self._safe_float(
                            row.get(
                                "bollinger_width_pct"
                            )
                        ),

                        source.strip().upper(),
                        now,
                        now,
                    ),
                )

        return len(prepared_rows)

    def get_latest_indicators(
        self,
        market: str,
        symbol: str,
        *,
        candle_interval: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        market = market.strip().upper()
        symbol = symbol.strip().upper()
        candle_interval = candle_interval.strip()
        limit = max(1, int(limit))

        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    mi.market,
                    mi.symbol,
                    mi.provider_symbol,

                    ti.candle_interval,
                    ti.candle_time,
                    ti.close,

                    ti.ema_20,
                    ti.ema_50,
                    ti.ema_100,
                    ti.ema_200,

                    ti.rsi_14,

                    ti.macd,
                    ti.macd_signal,
                    ti.macd_histogram,

                    ti.atr_14,

                    ti.bollinger_middle,
                    ti.bollinger_upper,
                    ti.bollinger_lower,
                    ti.bollinger_width_pct,

                    ti.source

                FROM technical_indicators ti

                JOIN market_instruments mi
                  ON mi.id = ti.instrument_id

                WHERE mi.market = ?
                  AND mi.symbol = ?
                  AND ti.candle_interval = ?

                ORDER BY ti.candle_time DESC
                LIMIT ?
                """,
                (
                    market,
                    symbol,
                    candle_interval,
                    limit,
                ),
            ).fetchall()

            return [dict(row) for row in rows]

    def indicator_summary(self) -> dict[str, int]:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM technical_indicators
                """
            ).fetchone()

            market_rows = connection.execute(
                """
                SELECT
                    mi.market,
                    COUNT(ti.id) AS indicator_count

                FROM market_instruments mi

                LEFT JOIN technical_indicators ti
                  ON ti.instrument_id = mi.id

                GROUP BY mi.market
                ORDER BY mi.market
                """
            ).fetchall()

            result = {
                "technical_indicators":
                    int(row["count"])
            }

            for market_row in market_rows:
                result[
                    str(market_row["market"])
                ] = int(
                    market_row["indicator_count"]
                )

            return result