from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from engine.market_universe import MarketInstrument
from engine.technical_indicator_repository import (
    TechnicalIndicatorRepository,
)


@dataclass(slots=True)
class IndicatorCalculationResult:
    market: str
    symbol: str
    candle_interval: str

    candle_count: int
    calculated_rows: int
    saved_rows: int

    last_candle_time: str | None = None

    status: str = "SUCCESS"
    error_type: str | None = None
    error_message: str | None = None


class TechnicalIndicatorEngine:
    """
    AlphaScan teknik gösterge hesaplama motoru.

    Hesaplanan göstergeler:
    - EMA 20
    - EMA 50
    - EMA 100
    - EMA 200
    - RSI 14
    - MACD 12, 26, 9
    - ATR 14
    - Bollinger Bands 20, 2
    """

    def __init__(
        self,
        repository: (
            TechnicalIndicatorRepository | None
        ) = None,
    ) -> None:
        self.repository = (
            repository
            if repository is not None
            else TechnicalIndicatorRepository()
        )

    @staticmethod
    def _rsi(
        close: pd.Series,
        period: int = 14,
    ) -> pd.Series:
        delta = close.diff()

        gain = delta.clip(lower=0.0)
        loss = -delta.clip(upper=0.0)

        average_gain = gain.ewm(
            alpha=1 / period,
            adjust=False,
            min_periods=period,
        ).mean()

        average_loss = loss.ewm(
            alpha=1 / period,
            adjust=False,
            min_periods=period,
        ).mean()

        relative_strength = (
            average_gain
            / average_loss.replace(
                0.0,
                np.nan,
            )
        )

        rsi = 100.0 - (
            100.0
            / (
                1.0
                + relative_strength
            )
        )

        no_loss = (
            average_loss == 0.0
        ) & (
            average_gain > 0.0
        )

        no_gain = (
            average_gain == 0.0
        ) & (
            average_loss > 0.0
        )

        unchanged = (
            average_gain == 0.0
        ) & (
            average_loss == 0.0
        )

        rsi = rsi.mask(
            no_loss,
            100.0,
        )

        rsi = rsi.mask(
            no_gain,
            0.0,
        )

        rsi = rsi.mask(
            unchanged,
            50.0,
        )

        return rsi

    @staticmethod
    def _true_range(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
    ) -> pd.Series:
        previous_close = close.shift(1)

        ranges = pd.concat(
            [
                high - low,
                (
                    high
                    - previous_close
                ).abs(),
                (
                    low
                    - previous_close
                ).abs(),
            ],
            axis=1,
        )

        return ranges.max(axis=1)

    @classmethod
    def _atr(
        cls,
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 14,
    ) -> pd.Series:
        true_range = cls._true_range(
            high,
            low,
            close,
        )

        return true_range.ewm(
            alpha=1 / period,
            adjust=False,
            min_periods=period,
        ).mean()

    @staticmethod
    def _safe_value(
        value: Any,
    ) -> float | None:
        if value is None:
            return None

        try:
            numeric = float(value)

        except (
            TypeError,
            ValueError,
        ):
            return None

        if not np.isfinite(numeric):
            return None

        return numeric

    def process_instrument(
        self,
        instrument: MarketInstrument,
    ) -> IndicatorCalculationResult:
        """
        MarketIntelligencePipeline uyumluluk metodu.

        Pipeline tarafından verilen MarketInstrument
        bilgisini motorun mevcut calculate_and_save
        metoduna dönüştürür.
        """
        return self.calculate_and_save(
            market=instrument.market.value,
            symbol=instrument.symbol,
            candle_interval=(
                instrument.candle_interval
            ),
            limit=1000,
        )

    def calculate_frame(
        self,
        candles: list[
            dict[str, Any]
        ],
    ) -> pd.DataFrame:
        if not candles:
            return pd.DataFrame()

        frame = pd.DataFrame(
            candles
        ).copy()

        required_columns = {
            "candle_time",
            "open",
            "high",
            "low",
            "close",
        }

        missing = (
            required_columns
            - set(frame.columns)
        )

        if missing:
            raise ValueError(
                "Eksik mum kolonları: "
                + ", ".join(
                    sorted(missing)
                )
            )

        frame["candle_time"] = (
            pd.to_datetime(
                frame["candle_time"],
                errors="coerce",
            )
        )

        for column in (
            "open",
            "high",
            "low",
            "close",
            "volume",
        ):
            if column not in frame.columns:
                frame[column] = np.nan

            frame[column] = (
                pd.to_numeric(
                    frame[column],
                    errors="coerce",
                )
            )

        frame = frame.dropna(
            subset=[
                "candle_time",
                "close",
            ]
        )

        frame = frame.sort_values(
            "candle_time"
        )

        frame = frame.drop_duplicates(
            subset=[
                "candle_time"
            ],
            keep="last",
        )

        frame = frame.reset_index(
            drop=True
        )

        close = frame["close"]
        high = frame["high"]
        low = frame["low"]

        frame["ema_20"] = close.ewm(
            span=20,
            adjust=False,
            min_periods=20,
        ).mean()

        frame["ema_50"] = close.ewm(
            span=50,
            adjust=False,
            min_periods=50,
        ).mean()

        frame["ema_100"] = close.ewm(
            span=100,
            adjust=False,
            min_periods=100,
        ).mean()

        frame["ema_200"] = close.ewm(
            span=200,
            adjust=False,
            min_periods=200,
        ).mean()

        frame["rsi_14"] = self._rsi(
            close,
            period=14,
        )

        ema_12 = close.ewm(
            span=12,
            adjust=False,
            min_periods=12,
        ).mean()

        ema_26 = close.ewm(
            span=26,
            adjust=False,
            min_periods=26,
        ).mean()

        frame["macd"] = (
            ema_12
            - ema_26
        )

        frame["macd_signal"] = (
            frame["macd"].ewm(
                span=9,
                adjust=False,
                min_periods=9,
            ).mean()
        )

        frame["macd_histogram"] = (
            frame["macd"]
            - frame["macd_signal"]
        )

        frame["atr_14"] = self._atr(
            high,
            low,
            close,
            period=14,
        )

        rolling_close = close.rolling(
            window=20,
            min_periods=20,
        )

        frame["bollinger_middle"] = (
            rolling_close.mean()
        )

        bollinger_std = (
            rolling_close.std(
                ddof=0
            )
        )

        frame["bollinger_upper"] = (
            frame["bollinger_middle"]
            + (
                2.0
                * bollinger_std
            )
        )

        frame["bollinger_lower"] = (
            frame["bollinger_middle"]
            - (
                2.0
                * bollinger_std
            )
        )

        band_range = (
            frame["bollinger_upper"]
            - frame["bollinger_lower"]
        )

        frame[
            "bollinger_width_pct"
        ] = (
            band_range
            / frame[
                "bollinger_middle"
            ].replace(
                0.0,
                np.nan,
            )
            * 100.0
        )

        return frame

    def calculate_and_save(
        self,
        market: str,
        symbol: str,
        *,
        candle_interval: str = "1h",
        limit: int = 1000,
    ) -> IndicatorCalculationResult:
        market = (
            market
            .strip()
            .upper()
        )

        symbol = (
            symbol
            .strip()
            .upper()
        )

        candle_interval = (
            candle_interval.strip()
        )

        try:
            candles = (
                self.repository
                .get_candles_chronological(
                    market,
                    symbol,
                    candle_interval=(
                        candle_interval
                    ),
                    limit=limit,
                )
            )

            if not candles:
                return (
                    IndicatorCalculationResult(
                        market=market,
                        symbol=symbol,
                        candle_interval=(
                            candle_interval
                        ),
                        candle_count=0,
                        calculated_rows=0,
                        saved_rows=0,
                        status="EMPTY",
                    )
                )

            instrument_id = int(
                candles[0][
                    "instrument_id"
                ]
            )

            frame = (
                self.calculate_frame(
                    candles
                )
            )

            indicator_rows: list[
                dict[str, Any]
            ] = []

            indicator_columns = (
                "close",
                "ema_20",
                "ema_50",
                "ema_100",
                "ema_200",
                "rsi_14",
                "macd",
                "macd_signal",
                "macd_histogram",
                "atr_14",
                "bollinger_middle",
                "bollinger_upper",
                "bollinger_lower",
                "bollinger_width_pct",
            )

            for _, row in frame.iterrows():
                candle_time = row[
                    "candle_time"
                ]

                if isinstance(
                    candle_time,
                    pd.Timestamp,
                ):
                    candle_time_text = (
                        candle_time
                        .to_pydatetime()
                        .isoformat(
                            timespec=(
                                "seconds"
                            )
                        )
                    )

                else:
                    candle_time_text = str(
                        candle_time
                    )

                result_row: dict[
                    str,
                    Any,
                ] = {
                    "candle_time": (
                        candle_time_text
                    ),
                }

                for column in (
                    indicator_columns
                ):
                    result_row[
                        column
                    ] = self._safe_value(
                        row.get(column)
                    )

                indicator_rows.append(
                    result_row
                )

            saved_rows = (
                self.repository
                .save_indicator_rows(
                    instrument_id,
                    indicator_rows,
                    candle_interval=(
                        candle_interval
                    ),
                )
            )

            last_candle_time = None

            if indicator_rows:
                last_candle_time = str(
                    indicator_rows[-1][
                        "candle_time"
                    ]
                )

            return IndicatorCalculationResult(
                market=market,
                symbol=symbol,
                candle_interval=(
                    candle_interval
                ),
                candle_count=len(
                    candles
                ),
                calculated_rows=len(
                    indicator_rows
                ),
                saved_rows=saved_rows,
                last_candle_time=(
                    last_candle_time
                ),
                status="SUCCESS",
            )

        except Exception as exc:
            return IndicatorCalculationResult(
                market=market,
                symbol=symbol,
                candle_interval=(
                    candle_interval
                ),
                candle_count=0,
                calculated_rows=0,
                saved_rows=0,
                status="FAILED",
                error_type=(
                    type(exc).__name__
                ),
                error_message=str(exc),
            )