from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping


class LifecycleEventType(StrEnum):
    SIGNAL = "SIGNAL"
    POSITION_OPENED = "POSITION_OPENED"
    INITIAL_STOP_SET = "INITIAL_STOP_SET"
    TARGET_SET = "TARGET_SET"
    PRICE_UPDATED = "PRICE_UPDATED"
    HIGHEST_PRICE_UPDATED = "HIGHEST_PRICE_UPDATED"
    LOWEST_PRICE_UPDATED = "LOWEST_PRICE_UPDATED"
    BREAK_EVEN_ACTIVATED = "BREAK_EVEN_ACTIVATED"
    ATR_TRAILING_UPDATED = "ATR_TRAILING_UPDATED"
    TRAILING_STOP_UPDATED = "TRAILING_STOP_UPDATED"
    SMART_EXIT_TRIGGERED = "SMART_EXIT_TRIGGERED"
    PARTIAL_EXIT = "PARTIAL_EXIT"
    POSITION_CLOSED = "POSITION_CLOSED"
    ERROR = "ERROR"
    INFO = "INFO"


@dataclass(frozen=True)
class LifecycleEvent:
    position_id: str
    symbol: str
    event_type: str
    market: str | None = None
    universe: str | None = None
    account_id: str | None = None
    event_time: str | None = None

    price: float | None = None
    previous_price: float | None = None
    entry_price: float | None = None
    stop_price: float | None = None
    previous_stop_price: float | None = None
    target_price: float | None = None
    quantity: float | None = None

    profit: float | None = None
    profit_pct: float | None = None
    technical_score: float | None = None
    confidence_score: float | None = None
    probability: float | None = None

    reason: str | None = None
    message: str | None = None
    metadata: Mapping[str, Any] | None = None

    def normalised(self) -> "LifecycleEvent":
        return LifecycleEvent(
            position_id=str(self.position_id),
            symbol=str(self.symbol).upper(),
            event_type=str(self.event_type),
            market=_normalise_text(self.market, upper=True),
            universe=_normalise_text(self.universe),
            account_id=_normalise_text(self.account_id),
            event_time=self.event_time or _now_iso(),
            price=_to_float(self.price),
            previous_price=_to_float(self.previous_price),
            entry_price=_to_float(self.entry_price),
            stop_price=_to_float(self.stop_price),
            previous_stop_price=_to_float(self.previous_stop_price),
            target_price=_to_float(self.target_price),
            quantity=_to_float(self.quantity),
            profit=_to_float(self.profit),
            profit_pct=_to_float(self.profit_pct),
            technical_score=_to_float(self.technical_score),
            confidence_score=_to_float(self.confidence_score),
            probability=_to_float(self.probability),
            reason=_normalise_text(self.reason),
            message=_normalise_text(self.message),
            metadata=dict(self.metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self.normalised())


class PositionLifecycleRepository:
    """
    Pozisyon yaşam döngüsü olaylarını SQLite veritabanına kaydeder.

    Beklenen database nesnesi:
        with database.connect() as connection:
            ...

    database verilmezse db_path ile doğrudan sqlite3 bağlantısı açılır.
    """

    TABLE_NAME = "position_lifecycle_events"

    def __init__(
        self,
        database: Any | None = None,
        *,
        db_path: str | None = None,
    ) -> None:
        if database is None and not db_path:
            raise ValueError("database veya db_path verilmelidir.")

        self.database = database
        self.db_path = db_path
        self.ensure_schema()

    def ensure_schema(self) -> None:
        sql = f"""
        CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            position_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            market TEXT,
            universe TEXT,
            account_id TEXT,
            event_type TEXT NOT NULL,
            event_time TEXT NOT NULL,

            price REAL,
            previous_price REAL,
            entry_price REAL,
            stop_price REAL,
            previous_stop_price REAL,
            target_price REAL,
            quantity REAL,

            profit REAL,
            profit_pct REAL,
            technical_score REAL,
            confidence_score REAL,
            probability REAL,

            reason TEXT,
            message TEXT,
            metadata_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """

        indexes = [
            f"""
            CREATE INDEX IF NOT EXISTS idx_{self.TABLE_NAME}_position
            ON {self.TABLE_NAME}(position_id, id)
            """,
            f"""
            CREATE INDEX IF NOT EXISTS idx_{self.TABLE_NAME}_symbol
            ON {self.TABLE_NAME}(symbol, id)
            """,
            f"""
            CREATE INDEX IF NOT EXISTS idx_{self.TABLE_NAME}_event_type
            ON {self.TABLE_NAME}(event_type, id)
            """,
            f"""
            CREATE INDEX IF NOT EXISTS idx_{self.TABLE_NAME}_event_time
            ON {self.TABLE_NAME}(event_time)
            """,
        ]

        with self._connect() as connection:
            connection.execute(sql)
            for index_sql in indexes:
                connection.execute(index_sql)
            connection.commit()

    def record(self, event: LifecycleEvent) -> int:
        item = event.normalised()

        sql = f"""
        INSERT INTO {self.TABLE_NAME} (
            position_id,
            symbol,
            market,
            universe,
            account_id,
            event_type,
            event_time,
            price,
            previous_price,
            entry_price,
            stop_price,
            previous_stop_price,
            target_price,
            quantity,
            profit,
            profit_pct,
            technical_score,
            confidence_score,
            probability,
            reason,
            message,
            metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        values = (
            item.position_id,
            item.symbol,
            item.market,
            item.universe,
            item.account_id,
            item.event_type,
            item.event_time,
            item.price,
            item.previous_price,
            item.entry_price,
            item.stop_price,
            item.previous_stop_price,
            item.target_price,
            item.quantity,
            item.profit,
            item.profit_pct,
            item.technical_score,
            item.confidence_score,
            item.probability,
            item.reason,
            item.message,
            json.dumps(
                dict(item.metadata or {}),
                ensure_ascii=False,
                default=str,
            ),
        )

        with self._connect() as connection:
            cursor = connection.execute(sql, values)
            connection.commit()
            return int(cursor.lastrowid)

    def record_event(
        self,
        *,
        position_id: str,
        symbol: str,
        event_type: LifecycleEventType | str,
        market: str | None = None,
        universe: str | None = None,
        account_id: str | None = None,
        event_time: str | datetime | None = None,
        price: float | None = None,
        previous_price: float | None = None,
        entry_price: float | None = None,
        stop_price: float | None = None,
        previous_stop_price: float | None = None,
        target_price: float | None = None,
        quantity: float | None = None,
        profit: float | None = None,
        profit_pct: float | None = None,
        technical_score: float | None = None,
        confidence_score: float | None = None,
        probability: float | None = None,
        reason: str | None = None,
        message: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> int:
        event = LifecycleEvent(
            position_id=position_id,
            symbol=symbol,
            event_type=str(event_type),
            market=market,
            universe=universe,
            account_id=account_id,
            event_time=_normalise_datetime(event_time),
            price=price,
            previous_price=previous_price,
            entry_price=entry_price,
            stop_price=stop_price,
            previous_stop_price=previous_stop_price,
            target_price=target_price,
            quantity=quantity,
            profit=profit,
            profit_pct=profit_pct,
            technical_score=technical_score,
            confidence_score=confidence_score,
            probability=probability,
            reason=reason,
            message=message,
            metadata=metadata,
        )
        return self.record(event)

    def events_for_position(
        self,
        position_id: str,
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        sql = f"""
        SELECT *
        FROM {self.TABLE_NAME}
        WHERE position_id = ?
        ORDER BY id ASC
        """
        params: list[Any] = [str(position_id)]

        if limit is not None:
            sql += "\nLIMIT ?"
            params.append(max(1, int(limit)))

        return self._fetch_all(sql, params)

    def latest_events(
        self,
        *,
        limit: int = 100,
        symbol: str | None = None,
        market: str | None = None,
        event_type: LifecycleEventType | str | None = None,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []

        if symbol:
            where.append("symbol = ?")
            params.append(str(symbol).upper())

        if market:
            where.append("UPPER(COALESCE(market, '')) = ?")
            params.append(str(market).upper())

        if event_type:
            where.append("event_type = ?")
            params.append(str(event_type))

        sql = f"SELECT * FROM {self.TABLE_NAME}"

        if where:
            sql += "\nWHERE " + " AND ".join(where)

        sql += "\nORDER BY id DESC\nLIMIT ?"
        params.append(max(1, int(limit)))

        return self._fetch_all(sql, params)

    def latest_event_for_position(
        self,
        position_id: str,
    ) -> dict[str, Any] | None:
        sql = f"""
        SELECT *
        FROM {self.TABLE_NAME}
        WHERE position_id = ?
        ORDER BY id DESC
        LIMIT 1
        """
        rows = self._fetch_all(sql, [str(position_id)])
        return rows[0] if rows else None

    def delete_position_events(self, position_id: str) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                f"""
                DELETE FROM {self.TABLE_NAME}
                WHERE position_id = ?
                """,
                (str(position_id),),
            )
            connection.commit()
            return int(cursor.rowcount or 0)

    def _fetch_all(
        self,
        sql: str,
        params: list[Any] | tuple[Any, ...],
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(sql, params).fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            raw_metadata = item.pop("metadata_json", None)
            try:
                item["metadata"] = (
                    json.loads(raw_metadata)
                    if raw_metadata
                    else {}
                )
            except (TypeError, json.JSONDecodeError):
                item["metadata"] = {"raw": raw_metadata}
            results.append(item)

        return results

    def _connect(self):
        if self.database is not None:
            return self.database.connect()

        connection = sqlite3.connect(
            str(self.db_path),
            timeout=30,
        )
        return connection


class SafePositionLifecycle:
    """
    Lifecycle kayıt hatalarının çalışan robotu durdurmasını engelleyen katman.

    Kayıt başarılıysa event id, başarısızsa None döndürür.
    """

    def __init__(
        self,
        repository: PositionLifecycleRepository,
        *,
        logger: Any | None = None,
    ) -> None:
        self.repository = repository
        self.logger = logger

    def record(self, **kwargs: Any) -> int | None:
        try:
            return self.repository.record_event(**kwargs)
        except Exception:
            if self.logger is not None:
                self.logger.exception(
                    "Pozisyon yaşam döngüsü olayı kaydedilemedi: %s",
                    kwargs,
                )
            return None


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _normalise_datetime(
    value: str | datetime | None,
) -> str:
    if value is None:
        return _now_iso()

    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.astimezone()
        return value.isoformat(timespec="seconds")

    text = str(value).strip()
    return text or _now_iso()


def _normalise_text(
    value: Any,
    *,
    upper: bool = False,
) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    return text.upper() if upper else text


def _to_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None
