from __future__ import annotations

import pandas as pd
import yfinance as yf
import ccxt

from engine.cache_engine import CacheEngine


class DataEngine:
    def __init__(self, cache_engine: CacheEngine):
        self.cache = cache_engine
        self._binance = ccxt.binance(
            {
                "enableRateLimit": True,
                "timeout": 20000,
            }
        )

    @staticmethod
    def normalize(frame: pd.DataFrame | None) -> pd.DataFrame:
        if frame is None or frame.empty:
            return pd.DataFrame()

        result = frame.copy()

        if isinstance(result.columns, pd.MultiIndex):
            result.columns = result.columns.get_level_values(0)

        required = ["Open", "High", "Low", "Close", "Volume"]
        missing = [column for column in required if column not in result.columns]
        if missing:
            return pd.DataFrame()

        result = result[required].copy()
        for column in required:
            result[column] = pd.to_numeric(result[column], errors="coerce")

        result.index = pd.to_datetime(result.index)
        result = result[~result.index.duplicated(keep="last")].sort_index()
        result = result.dropna(subset=["Open", "High", "Low", "Close"])
        return result

    @staticmethod
    def merge(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
        if old.empty:
            return DataEngine.normalize(new)
        if new.empty:
            return DataEngine.normalize(old)

        merged = pd.concat([old, new])
        merged = merged[~merged.index.duplicated(keep="last")]
        return DataEngine.normalize(merged)

    def get_yahoo(
        self,
        symbol: str,
        period: str,
        interval: str,
        force_refresh: bool = False,
    ) -> pd.DataFrame:
        cached = self.cache.read("yahoo", symbol, interval)

        refresh_period = {
            "1d": "1y",
            "1h": "60d",
            "60m": "60d",
            "30m": "60d",
            "15m": "60d",
        }.get(interval, period)

        request_period = period if force_refresh or cached.empty else refresh_period

        fresh = yf.download(
            symbol,
            period=request_period,
            interval=interval,
            progress=False,
            auto_adjust=False,
            threads=False,
            timeout=20,
        )
        fresh = self.normalize(fresh)
        merged = self.merge(cached, fresh)

        if not merged.empty:
            self.cache.write("yahoo", symbol, interval, merged)

        return merged

    def get_binance(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 1000,
    ) -> pd.DataFrame:
        cached = self.cache.read("binance", symbol, timeframe)

        since = None
        if not cached.empty:
            last_time = pd.Timestamp(cached.index.max())
            if last_time.tzinfo is None:
                last_time = last_time.tz_localize("UTC")
            else:
                last_time = last_time.tz_convert("UTC")
            since = int(last_time.timestamp() * 1000)

        rows = self._binance.fetch_ohlcv(
            symbol,
            timeframe=timeframe,
            since=since,
            limit=limit,
        )

        if rows:
            fresh = pd.DataFrame(
                rows,
                columns=[
                    "timestamp",
                    "Open",
                    "High",
                    "Low",
                    "Close",
                    "Volume",
                ],
            )
            fresh["timestamp"] = pd.to_datetime(
                fresh["timestamp"],
                unit="ms",
                utc=True,
            )
            fresh = fresh.set_index("timestamp")
            fresh = self.normalize(fresh)
        else:
            fresh = pd.DataFrame()

        merged = self.merge(cached, fresh)
        if not merged.empty:
            self.cache.write("binance", symbol, timeframe, merged)

        return merged
