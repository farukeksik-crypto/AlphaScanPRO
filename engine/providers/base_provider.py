from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from engine.market_universe import MarketInstrument


@dataclass(slots=True)
class MarketCandle:
    candle_time: datetime | str

    open: float | None
    high: float | None
    low: float | None
    close: float | None

    adjusted_close: float | None = None
    volume: float | None = None
    is_complete: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ProviderDownloadResult:
    provider_name: str
    instrument: MarketInstrument
    requested_period: str
    requested_interval: str

    candles: list[MarketCandle] = field(
        default_factory=list,
    )

    started_at: datetime = field(
        default_factory=datetime.now,
    )
    completed_at: datetime | None = None

    warning_messages: list[str] = field(
        default_factory=list,
    )

    @property
    def row_count(self) -> int:
        return len(self.candles)

    @property
    def is_empty(self) -> bool:
        return not self.candles

    def candle_dicts(self) -> list[dict[str, Any]]:
        return [
            candle.to_dict()
            for candle in self.candles
        ]


class MarketDataProvider(ABC):
    """
    Tüm piyasa veri sağlayıcılarının uygulayacağı
    temel sözleşme.

    Collector sadece bu arayüzü kullanır.
    Yahoo, TradePlus veya başka bir sağlayıcının
    ayrıntılarını bilmez.
    """

    provider_name: str = "BASE"

    @abstractmethod
    def download(
        self,
        instrument: MarketInstrument,
        *,
        period: str | None = None,
        interval: str | None = None,
    ) -> ProviderDownloadResult:
        """
        Belirtilen enstrüman için OHLCV mumlarını indirir.
        """
        raise NotImplementedError

    def supports(
        self,
        instrument: MarketInstrument,
    ) -> bool:
        """
        Sağlayıcının enstrümanı destekleyip
        desteklemediğini belirtir.
        """
        return bool(instrument.provider_symbol.strip())