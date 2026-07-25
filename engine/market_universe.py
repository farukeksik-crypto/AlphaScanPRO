from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Iterable


class MarketType(StrEnum):
    BIST = "BIST"
    CRYPTO = "CRYPTO"
    COMMODITY = "COMMODITY"
    FOREX = "FOREX"
    GLOBAL_INDEX = "GLOBAL_INDEX"
    US_EQUITY = "US_EQUITY"
    EUROPE_EQUITY = "EUROPE_EQUITY"
    ASIA_EQUITY = "ASIA_EQUITY"


class InstrumentType(StrEnum):
    EQUITY = "EQUITY"
    CRYPTO = "CRYPTO"
    COMMODITY = "COMMODITY"
    FOREX = "FOREX"
    INDEX = "INDEX"
    ETF = "ETF"


@dataclass(frozen=True, slots=True)
class MarketInstrument:
    symbol: str
    provider_symbol: str
    name: str
    market: MarketType
    instrument_type: InstrumentType

    currency: str = "TRY"
    country: str | None = None
    sector: str | None = None

    enabled: bool = True
    robot_enabled: bool = False

    scan_interval_minutes: int = 15
    history_period: str = "6mo"
    candle_interval: str = "1h"

    def __post_init__(self) -> None:
        symbol = self.symbol.strip().upper()
        provider_symbol = self.provider_symbol.strip()
        name = self.name.strip()
        currency = self.currency.strip().upper()

        if not symbol:
            raise ValueError("Sembol boş olamaz.")

        if not provider_symbol:
            raise ValueError(
                f"Veri sağlayıcı sembolü boş olamaz: {symbol}"
            )

        if not name:
            raise ValueError(f"Enstrüman adı boş olamaz: {symbol}")

        if self.scan_interval_minutes < 1:
            raise ValueError(
                "Tarama aralığı en az 1 dakika olmalıdır."
            )

        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(
            self,
            "provider_symbol",
            provider_symbol,
        )
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "currency", currency)

        if self.country:
            object.__setattr__(
                self,
                "country",
                self.country.strip().upper(),
            )

        if self.sector:
            object.__setattr__(
                self,
                "sector",
                self.sector.strip(),
            )

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["market"] = self.market.value
        result["instrument_type"] = self.instrument_type.value
        return result


class MarketUniverse:
    def __init__(
        self,
        instruments: Iterable[MarketInstrument] | None = None,
    ) -> None:
        self._instruments: dict[
            tuple[MarketType, str],
            MarketInstrument,
        ] = {}

        if instruments:
            for instrument in instruments:
                self.add(instrument)

    def add(self, instrument: MarketInstrument) -> None:
        key = (instrument.market, instrument.symbol)

        if key in self._instruments:
            raise ValueError(
                f"Enstrüman zaten kayıtlı: "
                f"{instrument.market.value}/{instrument.symbol}"
            )

        self._instruments[key] = instrument

    def upsert(self, instrument: MarketInstrument) -> None:
        key = (instrument.market, instrument.symbol)
        self._instruments[key] = instrument

    def get(
        self,
        market: MarketType,
        symbol: str,
    ) -> MarketInstrument | None:
        return self._instruments.get(
            (market, symbol.strip().upper())
        )

    def list(
        self,
        *,
        market: MarketType | None = None,
        enabled_only: bool = True,
        robot_only: bool = False,
    ) -> list[MarketInstrument]:
        instruments = list(self._instruments.values())

        if market is not None:
            instruments = [
                item
                for item in instruments
                if item.market == market
            ]

        if enabled_only:
            instruments = [
                item
                for item in instruments
                if item.enabled
            ]

        if robot_only:
            instruments = [
                item
                for item in instruments
                if item.robot_enabled
            ]

        return sorted(
            instruments,
            key=lambda item: (
                item.market.value,
                item.symbol,
            ),
        )

    def count_by_market(self) -> dict[str, int]:
        result: dict[str, int] = {}

        for instrument in self.list(enabled_only=False):
            market_name = instrument.market.value
            result[market_name] = result.get(market_name, 0) + 1

        return result

    def to_dict_list(
        self,
        *,
        market: MarketType | None = None,
        enabled_only: bool = True,
    ) -> list[dict[str, Any]]:
        return [
            item.to_dict()
            for item in self.list(
                market=market,
                enabled_only=enabled_only,
            )
        ]


def build_default_universe() -> MarketUniverse:
    instruments = [
        # BIST
        MarketInstrument(
            symbol="ASELS",
            provider_symbol="ASELS.IS",
            name="Aselsan",
            market=MarketType.BIST,
            instrument_type=InstrumentType.EQUITY,
            currency="TRY",
            country="TR",
            sector="Savunma",
            robot_enabled=False,
            scan_interval_minutes=15,
            candle_interval="1h",
        ),
        MarketInstrument(
            symbol="BIMAS",
            provider_symbol="BIMAS.IS",
            name="BİM Birleşik Mağazalar",
            market=MarketType.BIST,
            instrument_type=InstrumentType.EQUITY,
            currency="TRY",
            country="TR",
            sector="Perakende",
            robot_enabled=False,
            scan_interval_minutes=15,
            candle_interval="1h",
        ),
        MarketInstrument(
            symbol="THYAO",
            provider_symbol="THYAO.IS",
            name="Türk Hava Yolları",
            market=MarketType.BIST,
            instrument_type=InstrumentType.EQUITY,
            currency="TRY",
            country="TR",
            sector="Havacılık",
            robot_enabled=False,
            scan_interval_minutes=15,
            candle_interval="1h",
        ),

        # Kripto
        MarketInstrument(
            symbol="BTCUSDT",
            provider_symbol="BTC-USD",
            name="Bitcoin",
            market=MarketType.CRYPTO,
            instrument_type=InstrumentType.CRYPTO,
            currency="USD",
            robot_enabled=True,
            scan_interval_minutes=5,
            candle_interval="1h",
        ),
        MarketInstrument(
            symbol="ETHUSDT",
            provider_symbol="ETH-USD",
            name="Ethereum",
            market=MarketType.CRYPTO,
            instrument_type=InstrumentType.CRYPTO,
            currency="USD",
            robot_enabled=True,
            scan_interval_minutes=5,
            candle_interval="1h",
        ),

        # Emtia
        MarketInstrument(
            symbol="GOLD",
            provider_symbol="GC=F",
            name="Altın Vadeli İşlem",
            market=MarketType.COMMODITY,
            instrument_type=InstrumentType.COMMODITY,
            currency="USD",
            scan_interval_minutes=15,
            candle_interval="1h",
        ),
        MarketInstrument(
            symbol="SILVER",
            provider_symbol="SI=F",
            name="Gümüş Vadeli İşlem",
            market=MarketType.COMMODITY,
            instrument_type=InstrumentType.COMMODITY,
            currency="USD",
            scan_interval_minutes=15,
            candle_interval="1h",
        ),
        MarketInstrument(
            symbol="BRENT",
            provider_symbol="BZ=F",
            name="Brent Petrol",
            market=MarketType.COMMODITY,
            instrument_type=InstrumentType.COMMODITY,
            currency="USD",
            scan_interval_minutes=15,
            candle_interval="1h",
        ),

        # Döviz
        MarketInstrument(
            symbol="USDTRY",
            provider_symbol="TRY=X",
            name="Dolar/Türk Lirası",
            market=MarketType.FOREX,
            instrument_type=InstrumentType.FOREX,
            currency="TRY",
            scan_interval_minutes=15,
            candle_interval="1h",
        ),
        MarketInstrument(
            symbol="EURTRY",
            provider_symbol="EURTRY=X",
            name="Euro/Türk Lirası",
            market=MarketType.FOREX,
            instrument_type=InstrumentType.FOREX,
            currency="TRY",
            scan_interval_minutes=15,
            candle_interval="1h",
        ),

        # Dünya endeksleri
        MarketInstrument(
            symbol="SP500",
            provider_symbol="^GSPC",
            name="S&P 500",
            market=MarketType.GLOBAL_INDEX,
            instrument_type=InstrumentType.INDEX,
            currency="USD",
            country="US",
            scan_interval_minutes=15,
            candle_interval="1h",
        ),
        MarketInstrument(
            symbol="NASDAQ",
            provider_symbol="^IXIC",
            name="Nasdaq Composite",
            market=MarketType.GLOBAL_INDEX,
            instrument_type=InstrumentType.INDEX,
            currency="USD",
            country="US",
            scan_interval_minutes=15,
            candle_interval="1h",
        ),
        MarketInstrument(
            symbol="DAX",
            provider_symbol="^GDAXI",
            name="DAX",
            market=MarketType.GLOBAL_INDEX,
            instrument_type=InstrumentType.INDEX,
            currency="EUR",
            country="DE",
            scan_interval_minutes=15,
            candle_interval="1h",
        ),
        MarketInstrument(
            symbol="FTSE100",
            provider_symbol="^FTSE",
            name="FTSE 100",
            market=MarketType.GLOBAL_INDEX,
            instrument_type=InstrumentType.INDEX,
            currency="GBP",
            country="GB",
            scan_interval_minutes=15,
            candle_interval="1h",
        ),
        MarketInstrument(
            symbol="NIKKEI225",
            provider_symbol="^N225",
            name="Nikkei 225",
            market=MarketType.GLOBAL_INDEX,
            instrument_type=InstrumentType.INDEX,
            currency="JPY",
            country="JP",
            scan_interval_minutes=15,
            candle_interval="1h",
        ),
    ]

    return MarketUniverse(instruments)