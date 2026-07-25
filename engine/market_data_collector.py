from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from engine.market_history_repository import (
    MarketHistoryRepository,
)
from engine.market_universe import (
    MarketInstrument,
    MarketType,
    MarketUniverse,
    build_default_universe,
)
from engine.providers.base_provider import (
    MarketDataProvider,
)
from engine.providers.binance_provider import (
    BinanceProvider,
)
from engine.providers.yahoo_provider import (
    YahooFinanceProvider,
)


@dataclass(slots=True)
class InstrumentCollectionResult:
    market: str
    symbol: str
    provider_symbol: str

    status: str

    requested_period: str
    requested_interval: str

    received_rows: int = 0
    saved_rows: int = 0

    started_at: datetime = field(
        default_factory=datetime.now,
    )
    completed_at: datetime | None = None

    warnings: list[str] = field(
        default_factory=list,
    )

    error_type: str | None = None
    error_message: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.status == "SUCCESS"

    @property
    def failed(self) -> bool:
        return self.status == "FAILED"

    @property
    def empty(self) -> bool:
        return self.status == "EMPTY"


@dataclass(slots=True)
class CollectionBatchResult:
    started_at: datetime = field(
        default_factory=datetime.now,
    )
    completed_at: datetime | None = None

    results: list[InstrumentCollectionResult] = field(
        default_factory=list,
    )

    @property
    def instrument_count(self) -> int:
        return len(self.results)

    @property
    def success_count(self) -> int:
        return sum(
            result.succeeded
            for result in self.results
        )

    @property
    def failed_count(self) -> int:
        return sum(
            result.failed
            for result in self.results
        )

    @property
    def empty_count(self) -> int:
        return sum(
            result.empty
            for result in self.results
        )

    @property
    def received_rows(self) -> int:
        return sum(
            result.received_rows
            for result in self.results
        )

    @property
    def saved_rows(self) -> int:
        return sum(
            result.saved_rows
            for result in self.results
        )

    def summary(self) -> dict[str, int]:
        return {
            "instrument_count": self.instrument_count,
            "success_count": self.success_count,
            "empty_count": self.empty_count,
            "failed_count": self.failed_count,
            "received_rows": self.received_rows,
            "saved_rows": self.saved_rows,
        }


class MarketDataCollector:
    """
    AlphaScan çoklu piyasa veri toplama motoru.

    Akış:
        MarketInstrument
            ↓
        MarketDataProvider
            ↓
        ProviderDownloadResult
            ↓
        MarketHistoryRepository

    Bu sınıf mevcut tarama ve robot sisteminden
    bağımsız çalışır.
    """

    def __init__(
        self,
        *,
        provider: MarketDataProvider | None = None,
        repository: MarketHistoryRepository | None = None,
        universe: MarketUniverse | None = None,
    ) -> None:
        # A??k?a provider verilirse geriye d?n?k
        # uyumluluk i?in b?t?n enstr?manlarda o kullan?l?r.
        self.provider = provider

        self.yahoo_provider = (
            YahooFinanceProvider()
        )
        self.binance_provider = (
            BinanceProvider()
        )

        self.repository = (
            repository
            if repository is not None
            else MarketHistoryRepository()
        )

        self.universe = (
            universe
            if universe is not None
            else build_default_universe()
        )

    def _provider_for(
        self,
        instrument: MarketInstrument,
    ) -> MarketDataProvider:
        """
        Enstr?man?n piyasa t?r?ne g?re veri
        sa?lay?c?s?n? se?er.
        """
        if self.provider is not None:
            return self.provider

        if instrument.market == MarketType.CRYPTO:
            return self.binance_provider

        return self.yahoo_provider

    def collect_instrument(
        self,
        instrument: MarketInstrument,
        *,
        period: str | None = None,
        interval: str | None = None,
    ) -> InstrumentCollectionResult:
        requested_period = (
            period or instrument.history_period
        ).strip()

        requested_interval = (
            interval or instrument.candle_interval
        ).strip()

        started_at = datetime.now()

        collection_result = InstrumentCollectionResult(
            market=instrument.market.value,
            symbol=instrument.symbol,
            provider_symbol=instrument.provider_symbol,
            status="RUNNING",
            requested_period=requested_period,
            requested_interval=requested_interval,
            started_at=started_at,
        )

        run_id = self.repository.start_collector_run(
            instrument,
            requested_period=requested_period,
            requested_interval=requested_interval,
        )

        try:
            active_provider = self._provider_for(
                instrument
            )

            provider_result = active_provider.download(
                instrument,
                period=requested_period,
                interval=requested_interval,
            )

            received_rows = provider_result.row_count
            warnings = list(
                provider_result.warning_messages
            )

            if provider_result.is_empty:
                collection_result.status = "EMPTY"
                collection_result.received_rows = 0
                collection_result.saved_rows = 0
                collection_result.warnings = warnings
                collection_result.completed_at = datetime.now()

                self.repository.finish_collector_run(
                    run_id,
                    status="EMPTY",
                    received_rows=0,
                    saved_rows=0,
                )

                return collection_result

            saved_rows = self.repository.save_candles(
                instrument,
                provider_result.candle_dicts(),
                candle_interval=requested_interval,
                source=provider_result.provider_name,
            )

            collection_result.status = "SUCCESS"
            collection_result.received_rows = received_rows
            collection_result.saved_rows = saved_rows
            collection_result.warnings = warnings
            collection_result.completed_at = datetime.now()

            self.repository.finish_collector_run(
                run_id,
                status="SUCCESS",
                received_rows=received_rows,
                saved_rows=saved_rows,
            )

            return collection_result

        except Exception as exc:
            collection_result.status = "FAILED"
            collection_result.error_type = (
                type(exc).__name__
            )
            collection_result.error_message = str(exc)
            collection_result.completed_at = datetime.now()

            self.repository.finish_collector_run(
                run_id,
                status="FAILED",
                received_rows=0,
                saved_rows=0,
                error=exc,
            )

            return collection_result

    def collect_many(
        self,
        instruments: Iterable[MarketInstrument],
        *,
        period: str | None = None,
        interval: str | None = None,
    ) -> CollectionBatchResult:
        batch = CollectionBatchResult()

        for instrument in instruments:
            result = self.collect_instrument(
                instrument,
                period=period,
                interval=interval,
            )
            batch.results.append(result)

        batch.completed_at = datetime.now()
        return batch

    def collect_market(
        self,
        market: MarketType,
        *,
        robot_only: bool = False,
        period: str | None = None,
        interval: str | None = None,
    ) -> CollectionBatchResult:
        instruments = self.universe.list(
            market=market,
            enabled_only=True,
            robot_only=robot_only,
        )

        return self.collect_many(
            instruments,
            period=period,
            interval=interval,
        )

    def collect_all(
        self,
        *,
        robot_only: bool = False,
        period: str | None = None,
        interval: str | None = None,
    ) -> CollectionBatchResult:
        instruments = self.universe.list(
            enabled_only=True,
            robot_only=robot_only,
        )

        return self.collect_many(
            instruments,
            period=period,
            interval=interval,
        )