from __future__ import annotations

from datetime import datetime
from math import isfinite
from typing import Any

import pandas as pd

from engine.market_universe import MarketInstrument
from engine.providers.base_provider import (
    MarketCandle,
    MarketDataProvider,
    ProviderDownloadResult,
)


class YahooFinanceProvider(MarketDataProvider):
    provider_name = "YFINANCE"

    def __init__(
        self,
        *,
        timeout_seconds: float = 30.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError(
                "Timeout değeri sıfırdan büyük olmalıdır."
            )

        self.timeout_seconds = float(timeout_seconds)

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        if value is None:
            return None

        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None

        if not isfinite(numeric):
            return None

        return numeric

    @staticmethod
    def _normalize_timestamp(
        value: Any,
    ) -> datetime | str:
        if isinstance(value, pd.Timestamp):
            timestamp = value

            if timestamp.tzinfo is not None:
                timestamp = timestamp.tz_convert("UTC")
                timestamp = timestamp.tz_localize(None)

            return timestamp.to_pydatetime()

        if isinstance(value, datetime):
            return value

        return str(value)

    @staticmethod
    def _find_column(
        row: pd.Series,
        *possible_names: str,
    ) -> Any:
        normalized_columns = {
            str(column).strip().lower().replace("_", " "):
                column
            for column in row.index
        }

        for name in possible_names:
            normalized_name = (
                name.strip().lower().replace("_", " ")
            )

            actual_column = normalized_columns.get(
                normalized_name
            )

            if actual_column is not None:
                return row.get(actual_column)

        return None

    @staticmethod
    def _flatten_columns(
        frame: pd.DataFrame,
        provider_symbol: str,
    ) -> pd.DataFrame:
        """
        Bazı yfinance sürümleri tek sembolde bile
        MultiIndex kolon döndürebilir.

        Bu fonksiyon Open, High, Low, Close gibi
        standart tek seviyeli kolonlara dönüştürür.
        """
        if not isinstance(
            frame.columns,
            pd.MultiIndex,
        ):
            return frame

        result = frame.copy()

        level_zero = {
            str(value)
            for value in result.columns.get_level_values(0)
        }
        level_one = {
            str(value)
            for value in result.columns.get_level_values(1)
        }

        price_names = {
            "Open",
            "High",
            "Low",
            "Close",
            "Adj Close",
            "Volume",
        }

        if level_zero.intersection(price_names):
            result.columns = [
                str(column[0])
                for column in result.columns
            ]
            return result

        if provider_symbol in level_zero:
            result = result[provider_symbol]
            return result

        if provider_symbol in level_one:
            result.columns = [
                str(column[0])
                for column in result.columns
            ]
            return result

        result.columns = [
            " ".join(
                str(part)
                for part in column
                if str(part).strip()
            )
            for column in result.columns
        ]

        return result

    def download(
        self,
        instrument: MarketInstrument,
        *,
        period: str | None = None,
        interval: str | None = None,
    ) -> ProviderDownloadResult:
        if not self.supports(instrument):
            raise ValueError(
                "Yahoo Finance sembolü tanımlı değil: "
                f"{instrument.market.value}/"
                f"{instrument.symbol}"
            )

        requested_period = (
            period or instrument.history_period
        ).strip()

        requested_interval = (
            interval or instrument.candle_interval
        ).strip()

        if not requested_period:
            raise ValueError(
                "İndirme dönemi boş olamaz."
            )

        if not requested_interval:
            raise ValueError(
                "Mum aralığı boş olamaz."
            )

        started_at = datetime.now()

        result = ProviderDownloadResult(
            provider_name=self.provider_name,
            instrument=instrument,
            requested_period=requested_period,
            requested_interval=requested_interval,
            started_at=started_at,
        )

        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError(
                "yfinance kurulu değil. Kurmak için: "
                "py -3.13 -m pip install yfinance"
            ) from exc

        try:
            frame = yf.download(
                tickers=instrument.provider_symbol,
                period=requested_period,
                interval=requested_interval,
                auto_adjust=False,
                actions=False,
                progress=False,
                threads=False,
                timeout=self.timeout_seconds,
                group_by="column",
                multi_level_index=False,
            )
        except TypeError:
            # Eski yfinance sürümlerinde
            # multi_level_index parametresi bulunmayabilir.
            frame = yf.download(
                tickers=instrument.provider_symbol,
                period=requested_period,
                interval=requested_interval,
                auto_adjust=False,
                actions=False,
                progress=False,
                threads=False,
                timeout=self.timeout_seconds,
                group_by="column",
            )

        if frame is None or frame.empty:
            result.warning_messages.append(
                "Sağlayıcı boş veri döndürdü."
            )
            result.completed_at = datetime.now()
            return result

        frame = self._flatten_columns(
            frame,
            instrument.provider_symbol,
        )

        frame = frame.sort_index()

        candles: list[MarketCandle] = []

        for index, row in frame.iterrows():
            open_value = self._safe_float(
                self._find_column(row, "Open")
            )
            high_value = self._safe_float(
                self._find_column(row, "High")
            )
            low_value = self._safe_float(
                self._find_column(row, "Low")
            )
            close_value = self._safe_float(
                self._find_column(row, "Close")
            )
            adjusted_close = self._safe_float(
                self._find_column(
                    row,
                    "Adj Close",
                    "Adjusted Close",
                )
            )
            volume = self._safe_float(
                self._find_column(row, "Volume")
            )

            if close_value is None:
                continue

            if adjusted_close is None:
                adjusted_close = close_value

            candles.append(
                MarketCandle(
                    candle_time=self._normalize_timestamp(
                        index
                    ),
                    open=open_value,
                    high=high_value,
                    low=low_value,
                    close=close_value,
                    adjusted_close=adjusted_close,
                    volume=volume,
                    is_complete=True,
                )
            )

        result.candles = candles
        result.completed_at = datetime.now()

        if not candles:
            result.warning_messages.append(
                "DataFrame geldi ancak kullanılabilir "
                "mum oluşturulamadı."
            )

        return result