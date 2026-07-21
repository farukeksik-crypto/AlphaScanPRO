from __future__ import annotations

import inspect
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Protocol

from engine.multi_asset_engine import AssetType, SymbolConfig


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AdapterState(str, Enum):
    IDLE = "IDLE"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    DISCONNECTED = "DISCONNECTED"
    ERROR = "ERROR"


@dataclass(slots=True)
class MarketDataSnapshot:
    symbol: str
    asset_type: AssetType
    price: float
    timestamp: datetime
    source: str
    timeframe: str = ""
    volume: Optional[float] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.symbol = self.symbol.strip().upper()
        if not self.symbol:
            raise ValueError("symbol boş olamaz.")
        if self.price <= 0:
            raise ValueError("price pozitif olmalıdır.")
        if not self.source.strip():
            raise ValueError("source boş olamaz.")

    def to_market_data(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "asset_type": self.asset_type.value,
            "price": self.price,
            "timestamp": self.timestamp,
            "source": self.source,
            "timeframe": self.timeframe,
            "volume": self.volume,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "metadata": dict(self.metadata),
        }

    def to_dict(self) -> Dict[str, Any]:
        data = self.to_market_data()
        data["timestamp"] = self.timestamp.isoformat()
        return data


@dataclass(slots=True)
class AdapterHealth:
    name: str
    state: AdapterState = AdapterState.IDLE
    connected_at: Optional[datetime] = None
    disconnected_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    last_error_at: Optional[datetime] = None
    request_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    consecutive_failures: int = 0
    reconnect_count: int = 0
    last_error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "connected_at": self.connected_at.isoformat() if self.connected_at else None,
            "disconnected_at": (
                self.disconnected_at.isoformat()
                if self.disconnected_at else None
            ),
            "last_success_at": (
                self.last_success_at.isoformat()
                if self.last_success_at else None
            ),
            "last_error_at": (
                self.last_error_at.isoformat()
                if self.last_error_at else None
            ),
            "request_count": self.request_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "consecutive_failures": self.consecutive_failures,
            "reconnect_count": self.reconnect_count,
            "last_error": self.last_error,
        }


class MarketAdapter(Protocol):
    name: str
    asset_type: AssetType
    health: AdapterHealth

    async def connect(self) -> None:
        ...

    async def disconnect(self) -> None:
        ...

    async def fetch_snapshot(
        self,
        config: SymbolConfig,
    ) -> MarketDataSnapshot:
        ...


FetchCallable = Callable[[SymbolConfig], Any]


class BaseMarketAdapter:
    def __init__(
        self,
        *,
        name: str,
        asset_type: AssetType,
        fetcher: FetchCallable,
    ) -> None:
        self.name = name.strip()
        self.asset_type = asset_type
        self.fetcher = fetcher
        self.health = AdapterHealth(name=self.name)

        if not self.name:
            raise ValueError("adapter name boş olamaz.")

    async def _call(self, func: Callable[..., Any], *args: Any) -> Any:
        result = func(*args)
        if inspect.isawaitable(result):
            return await result
        return result

    async def connect(self) -> None:
        self.health.state = AdapterState.CONNECTING
        self.health.state = AdapterState.CONNECTED
        self.health.connected_at = utc_now()
        self.health.last_error = ""

    async def disconnect(self) -> None:
        self.health.state = AdapterState.DISCONNECTED
        self.health.disconnected_at = utc_now()

    def _normalize_snapshot(
        self,
        config: SymbolConfig,
        raw: Any,
    ) -> MarketDataSnapshot:
        if isinstance(raw, MarketDataSnapshot):
            return raw

        if isinstance(raw, (int, float)):
            return MarketDataSnapshot(
                symbol=config.symbol,
                asset_type=config.asset_type,
                price=float(raw),
                timestamp=utc_now(),
                source=self.name,
                timeframe=config.timeframe,
            )

        if not isinstance(raw, dict):
            raise TypeError("Fetcher sonucu sayı, dict veya MarketDataSnapshot olmalıdır.")

        price = (
            raw.get("price")
            or raw.get("close")
            or raw.get("last")
            or raw.get("last_price")
        )
        if price is None:
            raise ValueError(f"{config.symbol} için fiyat alanı bulunamadı.")

        timestamp = raw.get("timestamp") or raw.get("datetime") or utc_now()
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        return MarketDataSnapshot(
            symbol=config.symbol,
            asset_type=config.asset_type,
            price=float(price),
            timestamp=timestamp,
            source=str(raw.get("source") or self.name),
            timeframe=str(raw.get("timeframe") or config.timeframe),
            volume=(
                float(raw["volume"])
                if raw.get("volume") is not None else None
            ),
            open=(
                float(raw["open"])
                if raw.get("open") is not None else None
            ),
            high=(
                float(raw["high"])
                if raw.get("high") is not None else None
            ),
            low=(
                float(raw["low"])
                if raw.get("low") is not None else None
            ),
            close=(
                float(raw["close"])
                if raw.get("close") is not None else float(price)
            ),
            metadata=dict(raw.get("metadata", {}) or {}),
        )

    async def fetch_snapshot(
        self,
        config: SymbolConfig,
    ) -> MarketDataSnapshot:
        if config.asset_type != self.asset_type:
            raise ValueError(
                f"{self.name} adapteri {config.asset_type.value} desteklemiyor."
            )

        if self.health.state != AdapterState.CONNECTED:
            await self.connect()

        self.health.request_count += 1

        try:
            raw = await self._call(self.fetcher, config)
            snapshot = self._normalize_snapshot(config, raw)
        except Exception as exc:
            self.health.failure_count += 1
            self.health.consecutive_failures += 1
            self.health.last_error = str(exc)
            self.health.last_error_at = utc_now()
            self.health.state = AdapterState.DEGRADED
            raise
        else:
            self.health.success_count += 1
            self.health.consecutive_failures = 0
            self.health.last_success_at = utc_now()
            self.health.last_error = ""
            self.health.state = AdapterState.CONNECTED
            return snapshot

    async def reconnect(self) -> None:
        await self.disconnect()
        self.health.reconnect_count += 1
        await self.connect()

    def dashboard(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "asset_type": self.asset_type.value,
            "health": self.health.to_dict(),
        }


class BinanceMarketAdapter(BaseMarketAdapter):
    def __init__(self, fetcher: FetchCallable) -> None:
        super().__init__(
            name="BINANCE",
            asset_type=AssetType.CRYPTO,
            fetcher=fetcher,
        )


class YahooStockMarketAdapter(BaseMarketAdapter):
    def __init__(self, fetcher: FetchCallable) -> None:
        super().__init__(
            name="YAHOO_STOCK",
            asset_type=AssetType.STOCK,
            fetcher=fetcher,
        )


class YahooCommodityMarketAdapter(BaseMarketAdapter):
    def __init__(self, fetcher: FetchCallable) -> None:
        super().__init__(
            name="YAHOO_COMMODITY",
            asset_type=AssetType.COMMODITY,
            fetcher=fetcher,
        )


class MarketAdapterRegistry:
    def __init__(self) -> None:
        self._adapters: Dict[AssetType, BaseMarketAdapter] = {}

    def register(self, adapter: BaseMarketAdapter) -> None:
        self._adapters[adapter.asset_type] = adapter

    def unregister(self, asset_type: AssetType) -> None:
        if asset_type not in self._adapters:
            raise KeyError(asset_type)
        self._adapters.pop(asset_type)

    def get(self, asset_type: AssetType) -> BaseMarketAdapter:
        if asset_type not in self._adapters:
            raise KeyError(f"Adapter bulunamadı: {asset_type.value}")
        return self._adapters[asset_type]

    async def connect_all(self) -> None:
        for adapter in self._adapters.values():
            await adapter.connect()

    async def disconnect_all(self) -> None:
        for adapter in self._adapters.values():
            await adapter.disconnect()

    async def fetch(
        self,
        config: SymbolConfig,
    ) -> MarketDataSnapshot:
        adapter = self.get(config.asset_type)
        return await adapter.fetch_snapshot(config)

    async def fetch_many(
        self,
        configs: Iterable[SymbolConfig],
    ) -> Dict[str, MarketDataSnapshot | Exception]:
        results: Dict[str, MarketDataSnapshot | Exception] = {}
        for config in configs:
            try:
                results[config.symbol] = await self.fetch(config)
            except Exception as exc:
                results[config.symbol] = exc
        return results

    def dashboard(self) -> Dict[str, Any]:
        return {
            "adapter_count": len(self._adapters),
            "adapters": {
                asset_type.value: adapter.dashboard()
                for asset_type, adapter in sorted(
                    self._adapters.items(),
                    key=lambda item: item[0].value,
                )
            },
        }


class AdapterOrchestratorBridge:
    def __init__(
        self,
        *,
        registry: MarketAdapterRegistry,
        orchestrator: Any,
    ) -> None:
        self.registry = registry
        self.orchestrator = orchestrator
        self.processed_count = 0
        self.error_count = 0
        self.last_results: Dict[str, Any] = {}

    async def process_config(
        self,
        config: SymbolConfig,
    ) -> Any:
        try:
            snapshot = await self.registry.fetch(config)
            result = await self.orchestrator.process_symbol(
                config.symbol,
                market_data=snapshot.to_market_data(),
                now=snapshot.timestamp,
            )
        except Exception as exc:
            self.error_count += 1
            self.last_results[config.symbol] = exc
            raise
        else:
            self.processed_count += 1
            self.last_results[config.symbol] = result
            return result

    async def process_many(
        self,
        configs: Iterable[SymbolConfig],
    ) -> Dict[str, Any]:
        results: Dict[str, Any] = {}
        for config in configs:
            try:
                results[config.symbol] = await self.process_config(config)
            except Exception as exc:
                results[config.symbol] = exc
        return results

    def dashboard(self) -> Dict[str, Any]:
        return {
            "processed_count": self.processed_count,
            "error_count": self.error_count,
            "registry": self.registry.dashboard(),
            "last_result_symbols": sorted(self.last_results),
        }
