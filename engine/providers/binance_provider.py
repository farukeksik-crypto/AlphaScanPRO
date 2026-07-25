from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import ccxt

from engine.market_universe import (
    MarketInstrument,
    MarketType,
)
from engine.providers.base_provider import (
    MarketCandle,
    MarketDataProvider,
    ProviderDownloadResult,
)


class BinanceProvider(MarketDataProvider):
    """
    Binance Spot OHLCV veri sağlayıcısı.

    Market Intelligence tarafındaki kripto verilerini
    Yahoo Finance yerine doğrudan Binance üzerinden alır.
    """

    provider_name = "BINANCE"

    PERIOD_DAYS: dict[str, int] = {
        "1d": 1,
        "5d": 5,
        "7d": 7,
        "1mo": 30,
        "3mo": 90,
        "6mo": 180,
        "1y": 365,
        "2y": 730,
        "5y": 1825,
    }

    def __init__(
        self,
        *,
        timeout_ms: int = 20_000,
        max_candles: int = 5_000,
    ) -> None:
        if timeout_ms <= 0:
            raise ValueError(
                "Binance timeout değeri pozitif olmalıdır."
            )

        if max_candles <= 0:
            raise ValueError(
                "Binance maksimum mum sayısı pozitif olmalıdır."
            )

        self.max_candles = int(max_candles)

        self.exchange = ccxt.binance(
            {
                "enableRateLimit": True,
                "timeout": int(timeout_ms),
                "options": {
                    "defaultType": "spot",
                },
            }
        )

    def supports(
        self,
        instrument: MarketInstrument,
    ) -> bool:
        return (
            instrument.market == MarketType.CRYPTO
            and bool(
                str(
                    instrument.provider_symbol
                ).strip()
            )
        )

    @staticmethod
    def _normalize_symbol(
        symbol: str,
    ) -> str:
        value = str(symbol or "").strip().upper()

        value = (
            value
            .replace("-", "/")
            .replace("_", "/")
        )

        if "/" in value:
            base, quote = value.split("/", 1)

            if quote in {
                "USD",
                "USDC",
                "BUSD",
                "FDUSD",
            }:
                quote = "USDT"

            return f"{base}/{quote}"

        for suffix in (
            "USDT",
            "USDC",
            "BUSD",
            "FDUSD",
            "USD",
        ):
            if (
                value.endswith(suffix)
                and len(value) > len(suffix)
            ):
                base = value[:-len(suffix)]
                return f"{base}/USDT"

        return f"{value}/USDT"

    @classmethod
    def _period_days(
        cls,
        period: str,
    ) -> int:
        normalized = str(
            period or "6mo"
        ).strip().lower()

        if normalized == "max":
            return 1825

        return cls.PERIOD_DAYS.get(
            normalized,
            180,
        )

    @staticmethod
    def _timeframe_ms(
        exchange: Any,
        interval: str,
    ) -> int:
        return int(
            exchange.parse_timeframe(
                interval
            )
            * 1000
        )

    def download(
        self,
        instrument: MarketInstrument,
        *,
        period: str | None = None,
        interval: str | None = None,
    ) -> ProviderDownloadResult:
        if not self.supports(instrument):
            raise ValueError(
                "Binance kripto enstrümanı desteklemiyor: "
                f"{instrument.market.value}/"
                f"{instrument.symbol}"
            )

        requested_period = str(
            period
            or instrument.history_period
            or "6mo"
        ).strip()

        requested_interval = str(
            interval
            or instrument.candle_interval
            or "1h"
        ).strip()

        started_at = datetime.now(
            timezone.utc
        )

        result = ProviderDownloadResult(
            provider_name=self.provider_name,
            instrument=instrument,
            requested_period=requested_period,
            requested_interval=requested_interval,
            started_at=started_at,
        )

        symbol = self._normalize_symbol(
            instrument.provider_symbol
        )

        period_days = self._period_days(
            requested_period
        )

        since_time = (
            datetime.now(timezone.utc)
            - timedelta(days=period_days)
        )

        since_ms = int(
            since_time.timestamp()
            * 1000
        )

        timeframe_ms = self._timeframe_ms(
            self.exchange,
            requested_interval,
        )

        rows: list[list[Any]] = []
        seen_timestamps: set[int] = set()

        while len(rows) < self.max_candles:
            batch_limit = min(
                1000,
                self.max_candles - len(rows),
            )

            batch = self.exchange.fetch_ohlcv(
                symbol,
                timeframe=requested_interval,
                since=since_ms,
                limit=batch_limit,
            )

            if not batch:
                break

            added = 0

            for row in batch:
                timestamp = int(row[0])

                if timestamp in seen_timestamps:
                    continue

                seen_timestamps.add(timestamp)
                rows.append(row)
                added += 1

            if added == 0:
                break

            last_timestamp = int(
                batch[-1][0]
            )

            next_since = (
                last_timestamp
                + timeframe_ms
            )

            if next_since <= since_ms:
                break

            since_ms = next_since

            if len(batch) < batch_limit:
                break

        rows.sort(
            key=lambda row: int(row[0])
        )

        now_ms = int(
            datetime.now(
                timezone.utc
            ).timestamp()
            * 1000
        )

        candles: list[MarketCandle] = []

        for row in rows:
            if len(row) < 6:
                continue

            timestamp = int(row[0])

            candle_time = datetime.fromtimestamp(
                timestamp / 1000,
                tz=timezone.utc,
            )

            is_complete = (
                timestamp + timeframe_ms
                <= now_ms
            )

            candles.append(
                MarketCandle(
                    candle_time=candle_time,
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    adjusted_close=float(row[4]),
                    volume=float(row[5]),
                    is_complete=is_complete,
                )
            )

        result.candles = candles
        result.completed_at = datetime.now(
            timezone.utc
        )

        if not candles:
            result.warning_messages.append(
                f"Binance veri döndürmedi: {symbol}"
            )

        return result
