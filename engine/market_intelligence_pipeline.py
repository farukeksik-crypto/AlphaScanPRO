from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable

from engine.market_data_collector import MarketDataCollector
from engine.market_universe import (
    InstrumentType,
    MarketInstrument,
    MarketType,
    MarketUniverse,
    build_default_universe,
)
from engine.technical_indicator_engine import (
    TechnicalIndicatorEngine,
)


@dataclass
class InstrumentPipelineResult:
    market: str
    symbol: str
    provider_symbol: str
    status: str

    received_candles: int = 0
    saved_candles: int = 0
    calculated_indicators: int = 0
    saved_indicators: int = 0

    error_type: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "symbol": self.symbol,
            "provider_symbol": self.provider_symbol,
            "status": self.status,
            "received_candles": self.received_candles,
            "saved_candles": self.saved_candles,
            "calculated_indicators": (
                self.calculated_indicators
            ),
            "saved_indicators": self.saved_indicators,
            "error_type": self.error_type,
            "error_message": self.error_message,
        }


@dataclass
class PipelineBatchResult:
    results: list[InstrumentPipelineResult] = field(
        default_factory=list
    )

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def successful(self) -> int:
        return sum(
            1
            for result in self.results
            if result.status == "SUCCESS"
        )

    @property
    def failed(self) -> int:
        return sum(
            1
            for result in self.results
            if result.status == "FAILED"
        )

    @property
    def empty_data(self) -> int:
        return sum(
            1
            for result in self.results
            if result.error_type in {
                "EmptyMarketData",
                "NoReceivedCandles",
            }
        )

    @property
    def received_candles(self) -> int:
        return sum(
            result.received_candles
            for result in self.results
        )

    @property
    def saved_candles(self) -> int:
        return sum(
            result.saved_candles
            for result in self.results
        )

    @property
    def calculated_indicators(self) -> int:
        return sum(
            result.calculated_indicators
            for result in self.results
        )

    @property
    def saved_indicators(self) -> int:
        return sum(
            result.saved_indicators
            for result in self.results
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "successful": self.successful,
            "failed": self.failed,
            "empty_data": self.empty_data,
            "received_candles": self.received_candles,
            "saved_candles": self.saved_candles,
            "calculated_indicators": (
                self.calculated_indicators
            ),
            "saved_indicators": (
                self.saved_indicators
            ),
            "results": [
                result.to_dict()
                for result in self.results
            ],
        }


class MarketIntelligencePipeline:
    """
    AlphaScan piyasa verisi ve teknik gÃ¶sterge pipeline'Ä±.

    Tarama sonuÃ§larÄ±ndan gelen semboller dinamik olarak
    MarketInstrument nesnesine dÃ¶nÃ¼ÅŸtÃ¼rÃ¼lÃ¼r.

    Veri saÄŸlayÄ±cÄ± bir sembol iÃ§in yeni mum dÃ¶ndÃ¼rmezse
    eski veriler Ã¼zerinden gÃ¶sterge hesaplanmaz.
    """

    COMMODITY_ALIASES: dict[
        str,
        tuple[str, str, str],
    ] = {
        "ALTIN": (
            "GOLD",
            "GC=F",
            "AltÄ±n",
        ),
        "GOLD": (
            "GOLD",
            "GC=F",
            "AltÄ±n",
        ),
        "GUMUS": (
            "SILVER",
            "SI=F",
            "GÃ¼mÃ¼ÅŸ",
        ),
        "SILVER": (
            "SILVER",
            "SI=F",
            "GÃ¼mÃ¼ÅŸ",
        ),
        "BAKIR": (
            "COPPER",
            "HG=F",
            "BakÄ±r",
        ),
        "COPPER": (
            "COPPER",
            "HG=F",
            "BakÄ±r",
        ),
        "BRENT": (
            "BRENT",
            "BZ=F",
            "Brent Petrol",
        ),
        "BRENTPETROL": (
            "BRENT",
            "BZ=F",
            "Brent Petrol",
        ),
        "WTI": (
            "WTI",
            "CL=F",
            "WTI Petrol",
        ),
        "WTIPETROL": (
            "WTI",
            "CL=F",
            "WTI Petrol",
        ),
        "HAMPETROL": (
            "WTI",
            "CL=F",
            "WTI Petrol",
        ),
        "DOGALGAZ": (
            "NATGAS",
            "NG=F",
            "DoÄŸalgaz",
        ),
        "NATGAS": (
            "NATGAS",
            "NG=F",
            "DoÄŸalgaz",
        ),
        "PLATIN": (
            "PLATINUM",
            "PL=F",
            "Platin",
        ),
        "PLATINUM": (
            "PLATINUM",
            "PL=F",
            "Platin",
        ),
        "PALADYUM": (
            "PALLADIUM",
            "PA=F",
            "Paladyum",
        ),
        "PALLADIUM": (
            "PALLADIUM",
            "PA=F",
            "Paladyum",
        ),
    }

    # Geniş emtia evreni.
    COMMODITY_ALIASES.update({
        "PLATIN": ("PLATINUM", "PL=F", "Platin"),
        "PLATINUM": ("PLATINUM", "PL=F", "Platin"),
        "PL=F": ("PLATINUM", "PL=F", "Platin"),
        "PALADYUM": ("PALLADIUM", "PA=F", "Paladyum"),
        "PALLADIUM": ("PALLADIUM", "PA=F", "Paladyum"),
        "PA=F": ("PALLADIUM", "PA=F", "Paladyum"),
        "WTI": ("WTI", "CL=F", "WTI Petrol"),
        "WTIPETROL": ("WTI", "CL=F", "WTI Petrol"),
        "CL=F": ("WTI", "CL=F", "WTI Petrol"),
        "BRENT": ("BRENT", "BZ=F", "Brent Petrol"),
        "BRENTPETROL": ("BRENT", "BZ=F", "Brent Petrol"),
        "BZ=F": ("BRENT", "BZ=F", "Brent Petrol"),
        "DOGALGAZ": ("NATGAS", "NG=F", "Doğalgaz"),
        "NATGAS": ("NATGAS", "NG=F", "Doğalgaz"),
        "NG=F": ("NATGAS", "NG=F", "Doğalgaz"),
        "KALORIFERYAKITI": ("HEATING_OIL", "HO=F", "Kalorifer Yakıtı"),
        "HEATINGOIL": ("HEATING_OIL", "HO=F", "Kalorifer Yakıtı"),
        "HO=F": ("HEATING_OIL", "HO=F", "Kalorifer Yakıtı"),
        "RBOBBENZIN": ("RBOB_GASOLINE", "RB=F", "RBOB Benzin"),
        "RBOBGASOLINE": ("RBOB_GASOLINE", "RB=F", "RBOB Benzin"),
        "RB=F": ("RBOB_GASOLINE", "RB=F", "RBOB Benzin"),
        "MISIR": ("CORN", "ZC=F", "Mısır"),
        "CORN": ("CORN", "ZC=F", "Mısır"),
        "ZC=F": ("CORN", "ZC=F", "Mısır"),
        "BUGDAY": ("WHEAT", "ZW=F", "Buğday"),
        "WHEAT": ("WHEAT", "ZW=F", "Buğday"),
        "ZW=F": ("WHEAT", "ZW=F", "Buğday"),
        "SOYAFASULYESI": ("SOYBEAN", "ZS=F", "Soya Fasulyesi"),
        "SOYBEAN": ("SOYBEAN", "ZS=F", "Soya Fasulyesi"),
        "ZS=F": ("SOYBEAN", "ZS=F", "Soya Fasulyesi"),
        "SOYAKUSPESI": ("SOYBEAN_MEAL", "ZM=F", "Soya Küspesi"),
        "SOYBEANMEAL": ("SOYBEAN_MEAL", "ZM=F", "Soya Küspesi"),
        "ZM=F": ("SOYBEAN_MEAL", "ZM=F", "Soya Küspesi"),
        "SOYAYAGI": ("SOYBEAN_OIL", "ZL=F", "Soya Yağı"),
        "SOYBEANOIL": ("SOYBEAN_OIL", "ZL=F", "Soya Yağı"),
        "ZL=F": ("SOYBEAN_OIL", "ZL=F", "Soya Yağı"),
        "PIRINC": ("RICE", "ZR=F", "Pirinç"),
        "RICE": ("RICE", "ZR=F", "Pirinç"),
        "ZR=F": ("RICE", "ZR=F", "Pirinç"),
        "KAHVE": ("COFFEE", "KC=F", "Kahve"),
        "COFFEE": ("COFFEE", "KC=F", "Kahve"),
        "KC=F": ("COFFEE", "KC=F", "Kahve"),
        "SEKER": ("SUGAR", "SB=F", "Şeker"),
        "SUGAR": ("SUGAR", "SB=F", "Şeker"),
        "SB=F": ("SUGAR", "SB=F", "Şeker"),
        "PAMUK": ("COTTON", "CT=F", "Pamuk"),
        "COTTON": ("COTTON", "CT=F", "Pamuk"),
        "CT=F": ("COTTON", "CT=F", "Pamuk"),
        "KAKAO": ("COCOA", "CC=F", "Kakao"),
        "COCOA": ("COCOA", "CC=F", "Kakao"),
        "CC=F": ("COCOA", "CC=F", "Kakao"),
        "PORTAKALSUYU": ("ORANGE_JUICE", "OJ=F", "Portakal Suyu"),
        "ORANGEJUICE": ("ORANGE_JUICE", "OJ=F", "Portakal Suyu"),
        "OJ=F": ("ORANGE_JUICE", "OJ=F", "Portakal Suyu"),
        "CANLISIGIR": ("LIVE_CATTLE", "LE=F", "Canlı Sığır"),
        "LIVECATTLE": ("LIVE_CATTLE", "LE=F", "Canlı Sığır"),
        "LE=F": ("LIVE_CATTLE", "LE=F", "Canlı Sığır"),
        "YAGSIZDOMUZ": ("LEAN_HOGS", "HE=F", "Yağsız Domuz"),
        "LEANHOGS": ("LEAN_HOGS", "HE=F", "Yağsız Domuz"),
        "HE=F": ("LEAN_HOGS", "HE=F", "Yağsız Domuz"),
        "BESISIGIRI": ("FEEDER_CATTLE", "GF=F", "Besi Sığırı"),
        "FEEDERCATTLE": ("FEEDER_CATTLE", "GF=F", "Besi Sığırı"),
        "GF=F": ("FEEDER_CATTLE", "GF=F", "Besi Sığırı"),
        "KERESTE": ("LUMBER", "LBS=F", "Kereste"),
        "LUMBER": ("LUMBER", "LBS=F", "Kereste"),
        "LBS=F": ("LUMBER", "LBS=F", "Kereste"),
        "YULAF": ("OATS", "ZO=F", "Yulaf"),
        "OATS": ("OATS", "ZO=F", "Yulaf"),
        "ZO=F": ("OATS", "ZO=F", "Yulaf"),
        "DEMIRCEVHERI": ("IRON_ORE", "TIO=F", "Demir Cevheri"),
        "IRONORE": ("IRON_ORE", "TIO=F", "Demir Cevheri"),
        "TIO=F": ("IRON_ORE", "TIO=F", "Demir Cevheri"),
    })


    FOREX_ALIASES: dict[
        str,
        tuple[str, str, str, str],
    ] = {
        "USDTRY": (
            "USDTRY",
            "TRY=X",
            "Dolar/TÃ¼rk LirasÄ±",
            "TRY",
        ),
        "DOLAR": (
            "USDTRY",
            "TRY=X",
            "Dolar/TÃ¼rk LirasÄ±",
            "TRY",
        ),
        "EURTRY": (
            "EURTRY",
            "EURTRY=X",
            "Euro/TÃ¼rk LirasÄ±",
            "TRY",
        ),
        "EURO": (
            "EURTRY",
            "EURTRY=X",
            "Euro/TÃ¼rk LirasÄ±",
            "TRY",
        ),
        "GBPTRY": (
            "GBPTRY",
            "GBPTRY=X",
            "Sterlin/TÃ¼rk LirasÄ±",
            "TRY",
        ),
        "STERLIN": (
            "GBPTRY",
            "GBPTRY=X",
            "Sterlin/TÃ¼rk LirasÄ±",
            "TRY",
        ),
    }

    def __init__(
        self,
        universe: MarketUniverse | None = None,
        collector: MarketDataCollector | None = None,
        indicator_engine: (
            TechnicalIndicatorEngine | None
        ) = None,
    ) -> None:
        self.universe = (
            universe
            or build_default_universe()
        )

        self.collector = (
            collector
            or MarketDataCollector(
                universe=self.universe,
            )
        )

        self.indicator_engine = (
            indicator_engine
            or TechnicalIndicatorEngine()
        )

        self.collector.repository.sync_universe(
            self.universe
        )

    @staticmethod
    def _text_key(
        value: Any,
    ) -> str:
        text = str(
            value or ""
        ).strip().upper()

        replacements = {
            "Ä°": "I",
            "IÌ‡": "I",
            "Å": "S",
            "Ä": "G",
            "Ãœ": "U",
            "Ã–": "O",
            "Ã‡": "C",
        }

        for source, target in replacements.items():
            text = text.replace(
                source,
                target,
            )

        text = unicodedata.normalize(
            "NFKD",
            text,
        )

        text = "".join(
            character
            for character in text
            if not unicodedata.combining(
                character
            )
        )

        return text.strip().upper()

    @classmethod
    def _compact_key(
        cls,
        value: Any,
    ) -> str:
        return re.sub(
            r"[^A-Z0-9=^]+",
            "",
            cls._text_key(value),
        )

    @classmethod
    def _normalize_market(
        cls,
        market: str | MarketType,
    ) -> MarketType:
        if isinstance(
            market,
            MarketType,
        ):
            return market

        key = cls._compact_key(
            market
        )

        aliases = {
            "BIST": MarketType.BIST,
            "BORSAISTANBUL": MarketType.BIST,
            "KRIPTO": MarketType.CRYPTO,
            "CRYPTO": MarketType.CRYPTO,
            "EMTIA": MarketType.COMMODITY,
            "COMMODITY": MarketType.COMMODITY,
            "DOVIZ": MarketType.FOREX,
            "FOREX": MarketType.FOREX,
            "GLOBALINDEX": MarketType.GLOBAL_INDEX,
            "ENDEKS": MarketType.GLOBAL_INDEX,
            "USEQUITY": MarketType.US_EQUITY,
            "ABDHISSE": MarketType.US_EQUITY,
            "EUROPEEQUITY": (
                MarketType.EUROPE_EQUITY
            ),
            "ASIAEQUITY": (
                MarketType.ASIA_EQUITY
            ),
        }

        resolved = aliases.get(key)

        if resolved is not None:
            return resolved

        try:
            return MarketType(
                cls._text_key(market)
            )

        except ValueError as error:
            raise ValueError(
                "Desteklenmeyen piyasa: "
                f"{market}"
            ) from error

    @staticmethod
    def _result_value(
        result: Any,
        *names: str,
        default: int = 0,
    ) -> int:
        for name in names:
            if hasattr(
                result,
                name,
            ):
                value = getattr(
                    result,
                    name,
                )

                if value is None:
                    continue

                try:
                    return int(value)

                except (
                    TypeError,
                    ValueError,
                ):
                    continue

            if isinstance(
                result,
                dict,
            ):
                if name not in result:
                    continue

                value = result.get(name)

                try:
                    return int(
                        value or 0
                    )

                except (
                    TypeError,
                    ValueError,
                ):
                    continue

        return default

    @staticmethod
    def _status_value(
        result: Any,
    ) -> str:
        if isinstance(
            result,
            dict,
        ):
            status = result.get(
                "status",
                "SUCCESS",
            )

        else:
            status = getattr(
                result,
                "status",
                "SUCCESS",
            )

        return str(
            status
        ).strip().upper()

    @classmethod
    def _crypto_base_symbol(
        cls,
        symbol: str,
    ) -> str:
        compact = cls._compact_key(
            symbol
        )

        for suffix in (
            "USDT",
            "USDC",
            "BUSD",
            "USD",
            "TRY",
            "EUR",
        ):
            if (
                compact.endswith(suffix)
                and len(compact) > len(suffix)
            ):
                compact = compact[
                    :-len(suffix)
                ]
                break

        return compact

    @classmethod
    def _build_bist_instrument(
        cls,
        symbol: str,
    ) -> MarketInstrument:
        normalized = cls._compact_key(
            symbol
        )

        if normalized.endswith("IS"):
            normalized = normalized[:-2]

        if not normalized:
            raise ValueError(
                "BIST sembolÃ¼ boÅŸ."
            )

        return MarketInstrument(
            symbol=normalized,
            provider_symbol=(
                f"{normalized}.IS"
            ),
            name=normalized,
            market=MarketType.BIST,
            instrument_type=(
                InstrumentType.EQUITY
            ),
            currency="TRY",
            country="TR",
            enabled=True,
            robot_enabled=False,
            scan_interval_minutes=15,
            history_period="6mo",
            candle_interval="1h",
        )

    @classmethod
    def _build_crypto_instrument(
        cls,
        symbol: str,
    ) -> MarketInstrument:
        base_symbol = (
            cls._crypto_base_symbol(
                symbol
            )
        )

        if not base_symbol:
            raise ValueError(
                "Kripto sembolÃ¼ boÅŸ."
            )

        return MarketInstrument(
            symbol=base_symbol,
            provider_symbol=(
                f"{base_symbol}/USDT"
            ),
            name=base_symbol,
            market=MarketType.CRYPTO,
            instrument_type=(
                InstrumentType.CRYPTO
            ),
            currency="USDT",
            enabled=True,
            robot_enabled=True,
            scan_interval_minutes=5,
            history_period="6mo",
            candle_interval="1h",
        )

    @classmethod
    def _build_commodity_instrument(
        cls,
        symbol: str,
    ) -> MarketInstrument:
        original = str(
            symbol or ""
        ).strip()

        text_key = cls._text_key(
            original
        )

        compact_key = cls._compact_key(
            original
        )

        alias = (
            cls.COMMODITY_ALIASES.get(
                text_key
            )
            or cls.COMMODITY_ALIASES.get(
                compact_key
            )
        )

        if alias is None:
            raise ValueError(
                "TanÄ±nmayan emtia sembolÃ¼: "
                f"{symbol}"
            )

        internal_symbol = alias[0]
        provider_symbol = alias[1]
        name = alias[2]

        return MarketInstrument(
            symbol=internal_symbol,
            provider_symbol=provider_symbol,
            name=name,
            market=MarketType.COMMODITY,
            instrument_type=(
                InstrumentType.COMMODITY
            ),
            currency="USD",
            enabled=True,
            robot_enabled=True,
            scan_interval_minutes=15,
            history_period="6mo",
            candle_interval="1h",
        )

    @classmethod
    def _build_forex_instrument(
        cls,
        symbol: str,
    ) -> MarketInstrument:
        text_key = cls._text_key(
            symbol
        )

        compact_key = cls._compact_key(
            symbol
        )

        alias = (
            cls.FOREX_ALIASES.get(
                text_key
            )
            or cls.FOREX_ALIASES.get(
                compact_key
            )
        )

        if alias is None:
            raise ValueError(
                "TanÄ±nmayan dÃ¶viz sembolÃ¼: "
                f"{symbol}"
            )

        return MarketInstrument(
            symbol=alias[0],
            provider_symbol=alias[1],
            name=alias[2],
            market=MarketType.FOREX,
            instrument_type=(
                InstrumentType.FOREX
            ),
            currency=alias[3],
            enabled=True,
            robot_enabled=False,
            scan_interval_minutes=15,
            history_period="6mo",
            candle_interval="1h",
        )

    @classmethod
    def _build_generic_instrument(
        cls,
        symbol: str,
        market: MarketType,
    ) -> MarketInstrument:
        normalized = cls._compact_key(
            symbol
        )

        if not normalized:
            raise ValueError(
                "Sembol boÅŸ."
            )

        instrument_type = (
            InstrumentType.INDEX
            if market
            == MarketType.GLOBAL_INDEX
            else InstrumentType.EQUITY
        )

        currency = (
            "EUR"
            if market
            == MarketType.EUROPE_EQUITY
            else "USD"
        )

        return MarketInstrument(
            symbol=normalized,
            provider_symbol=str(
                symbol
            ).strip(),
            name=normalized,
            market=market,
            instrument_type=instrument_type,
            currency=currency,
            enabled=True,
            robot_enabled=False,
            scan_interval_minutes=15,
            history_period="6mo",
            candle_interval="1h",
        )

    @classmethod
    def build_instrument(
        cls,
        symbol: str,
        market: str | MarketType,
    ) -> MarketInstrument:
        market_type = (
            cls._normalize_market(
                market
            )
        )

        if market_type == MarketType.BIST:
            return (
                cls._build_bist_instrument(
                    symbol
                )
            )

        if (
            market_type
            == MarketType.CRYPTO
        ):
            return (
                cls._build_crypto_instrument(
                    symbol
                )
            )

        if (
            market_type
            == MarketType.COMMODITY
        ):
            return (
                cls._build_commodity_instrument(
                    symbol
                )
            )

        if (
            market_type
            == MarketType.FOREX
        ):
            return (
                cls._build_forex_instrument(
                    symbol
                )
            )

        return cls._build_generic_instrument(
            symbol,
            market_type,
        )

    def _find_existing_instrument(
        self,
        symbol: str,
        market: MarketType,
    ) -> MarketInstrument | None:
        requested_compact = (
            self._compact_key(
                symbol
            )
        )

        requested_crypto_base = (
            self._crypto_base_symbol(
                symbol
            )
            if market
            == MarketType.CRYPTO
            else ""
        )

        for instrument in self.universe.list(
            market=market,
            enabled_only=False,
        ):
            instrument_symbol = (
                self._compact_key(
                    instrument.symbol
                )
            )

            provider_symbol = (
                self._compact_key(
                    instrument.provider_symbol
                )
            )

            if requested_compact in {
                instrument_symbol,
                provider_symbol,
            }:
                return instrument

            if (
                market
                == MarketType.CRYPTO
            ):
                existing_base = (
                    self._crypto_base_symbol(
                        instrument.symbol
                    )
                )

                provider_base = (
                    self._crypto_base_symbol(
                        instrument.provider_symbol
                    )
                )

                if requested_crypto_base in {
                    existing_base,
                    provider_base,
                }:
                    return instrument

        return None

    def _resolve_instrument(
        self,
        symbol: str,
        market: MarketType,
    ) -> MarketInstrument:
        existing = (
            self._find_existing_instrument(
                symbol,
                market,
            )
        )

        if existing is not None:
            return existing

        instrument = self.build_instrument(
            symbol,
            market,
        )

        self.universe.upsert(
            instrument
        )

        return instrument

    def _sync_instruments(
        self,
        instruments: Iterable[
            MarketInstrument
        ],
    ) -> None:
        dynamic_universe = MarketUniverse()

        for instrument in instruments:
            dynamic_universe.upsert(
                instrument
            )

        if dynamic_universe.list(
            enabled_only=False
        ):
            self.collector.repository.sync_universe(
                dynamic_universe
            )

    def _collect_instrument(
        self,
        instrument: MarketInstrument,
    ) -> Any:
        if hasattr(
            self.collector,
            "collect_instrument",
        ):
            return (
                self.collector
                .collect_instrument(
                    instrument
                )
            )

        if hasattr(
            self.collector,
            "collect",
        ):
            return self.collector.collect(
                instrument
            )

        raise AttributeError(
            "MarketDataCollector iÃ§inde "
            "collect_instrument veya collect "
            "metodu yok."
        )

    def _calculate_indicators(
        self,
        instrument: MarketInstrument,
    ) -> Any:
        if hasattr(
            self.indicator_engine,
            "process_instrument",
        ):
            return (
                self.indicator_engine
                .process_instrument(
                    instrument
                )
            )

        if hasattr(
            self.indicator_engine,
            "calculate_for_instrument",
        ):
            return (
                self.indicator_engine
                .calculate_for_instrument(
                    instrument
                )
            )

        if hasattr(
            self.indicator_engine,
            "run",
        ):
            return (
                self.indicator_engine.run(
                    instrument
                )
            )

        raise AttributeError(
            "TechnicalIndicatorEngine iÃ§inde "
            "process_instrument, "
            "calculate_for_instrument veya "
            "run metodu yok."
        )

    def run_instrument(
        self,
        instrument: MarketInstrument,
    ) -> InstrumentPipelineResult:
        result = InstrumentPipelineResult(
            market=instrument.market.value,
            symbol=instrument.symbol,
            provider_symbol=(
                instrument.provider_symbol
            ),
            status="RUNNING",
        )

        try:
            collector_result = (
                self._collect_instrument(
                    instrument
                )
            )

            collector_status = (
                self._status_value(
                    collector_result
                )
            )

            result.received_candles = (
                self._result_value(
                    collector_result,
                    "received_rows",
                    "received_candles",
                    "row_count",
                )
            )

            result.saved_candles = (
                self._result_value(
                    collector_result,
                    "saved_rows",
                    "saved_candles",
                )
            )

            if collector_status in {
                "FAILED",
                "ERROR",
            }:
                collector_error = getattr(
                    collector_result,
                    "error_message",
                    None,
                )

                raise RuntimeError(
                    collector_error
                    or (
                        "Mum toplama iÅŸlemi "
                        "baÅŸarÄ±sÄ±z."
                    )
                )

            # Veri saÄŸlayÄ±cÄ± hiÃ§ yeni mum dÃ¶ndÃ¼rmediyse
            # eski verilerle gÃ¶sterge hesaplama.
            if collector_status == "EMPTY":
                warnings = getattr(
                    collector_result,
                    "warnings",
                    [],
                )

                warning_text = " | ".join(
                    str(warning)
                    for warning in warnings
                    if str(warning).strip()
                )

                result.status = "FAILED"
                result.error_type = (
                    "EmptyMarketData"
                )
                result.error_message = (
                    warning_text
                    or (
                        "Veri saÄŸlayÄ±cÄ± bu sembol "
                        "iÃ§in mum verisi dÃ¶ndÃ¼rmedi."
                    )
                )

                return result

            # SUCCESS durumu geldiÄŸi hÃ¢lde hiÃ§ mum
            # alÄ±nmamÄ±ÅŸsa eski verileri kullanma.
            if result.received_candles <= 0:
                result.status = "FAILED"
                result.error_type = (
                    "NoReceivedCandles"
                )
                result.error_message = (
                    "Veri toplama baÅŸarÄ±lÄ± gÃ¶rÃ¼ndÃ¼ "
                    "ancak hiÃ§ mum alÄ±nmadÄ±."
                )

                return result

            indicator_result = (
                self._calculate_indicators(
                    instrument
                )
            )

            indicator_status = (
                self._status_value(
                    indicator_result
                )
            )

            result.calculated_indicators = (
                self._result_value(
                    indicator_result,
                    "calculated_rows",
                    "calculated_indicators",
                    "processed_rows",
                    "indicator_count",
                )
            )

            result.saved_indicators = (
                self._result_value(
                    indicator_result,
                    "saved_rows",
                    "saved_indicators",
                )
            )

            if indicator_status in {
                "FAILED",
                "ERROR",
                "EMPTY",
            }:
                indicator_error = getattr(
                    indicator_result,
                    "error_message",
                    None,
                )

                raise RuntimeError(
                    indicator_error
                    or (
                        "Teknik gÃ¶sterge iÅŸlemi "
                        "baÅŸarÄ±sÄ±z."
                    )
                )

            if (
                result.calculated_indicators
                <= 0
            ):
                result.status = "FAILED"
                result.error_type = (
                    "NoIndicatorsCalculated"
                )
                result.error_message = (
                    "Teknik gÃ¶sterge motoru hiÃ§ "
                    "gÃ¶sterge hesaplamadÄ±."
                )

                return result

            result.status = "SUCCESS"

        except Exception as error:
            result.status = "FAILED"
            result.error_type = (
                type(error).__name__
            )
            result.error_message = str(
                error
            )

        return result

    def run_many(
        self,
        instruments: Iterable[
            MarketInstrument
        ],
    ) -> PipelineBatchResult:
        unique: dict[
            tuple[str, str],
            MarketInstrument,
        ] = {}

        for instrument in instruments:
            key = (
                instrument.market.value,
                instrument.symbol,
            )
            unique[key] = instrument

        resolved_instruments = list(
            unique.values()
        )

        self._sync_instruments(
            resolved_instruments
        )

        batch = PipelineBatchResult()

        for instrument in (
            resolved_instruments
        ):
            batch.results.append(
                self.run_instrument(
                    instrument
                )
            )

        return batch

    def run_all(
        self,
    ) -> PipelineBatchResult:
        return self.run_many(
            self.universe.list()
        )

    def run_market(
        self,
        market: str | MarketType,
    ) -> PipelineBatchResult:
        market_type = (
            self._normalize_market(
                market
            )
        )

        instruments = (
            self.universe.list(
                market=market_type,
                enabled_only=True,
            )
        )

        return self.run_many(
            instruments
        )

    def run_symbols(
        self,
        symbols: Iterable[str],
        market: str | MarketType | None = None,
    ) -> PipelineBatchResult:
        clean_symbols = [
            str(symbol).strip()
            for symbol in symbols
            if str(symbol).strip()
        ]

        if not clean_symbols:
            return PipelineBatchResult()

        if market is None:
            normalized_symbols = {
                self._compact_key(symbol)
                for symbol in clean_symbols
            }

            instruments = [
                instrument
                for instrument
                in self.universe.list(
                    enabled_only=True
                )
                if (
                    self._compact_key(
                        instrument.symbol
                    )
                    in normalized_symbols
                    or self._compact_key(
                        instrument.provider_symbol
                    )
                    in normalized_symbols
                )
            ]

            return self.run_many(
                instruments
            )

        market_type = (
            self._normalize_market(
                market
            )
        )

        instruments: list[
            MarketInstrument
        ] = []

        failed_results: list[
            InstrumentPipelineResult
        ] = []

        for symbol in clean_symbols:
            try:
                instrument = (
                    self._resolve_instrument(
                        symbol,
                        market_type,
                    )
                )

                instruments.append(
                    instrument
                )

            except Exception as error:
                failed_results.append(
                    InstrumentPipelineResult(
                        market=market_type.value,
                        symbol=str(
                            symbol
                        ).strip(),
                        provider_symbol="",
                        status="FAILED",
                        error_type=(
                            type(error).__name__
                        ),
                        error_message=str(
                            error
                        ),
                    )
                )

        batch = self.run_many(
            instruments
        )

        batch.results.extend(
            failed_results
        )

        return batch
