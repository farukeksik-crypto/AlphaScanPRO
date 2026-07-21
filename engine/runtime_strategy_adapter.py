from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Iterable, Mapping, Protocol
import math

from engine.live_market_data import KlineUpdate, MarketDataEvent, MarketDataEventType
from engine.robot_runtime import RuntimeAction, StrategyDecision


class SignalLabel(str, Enum):
    NET_AL = "NET AL"
    AL_ADAY = "AL ADAY"
    IZLE = "İZLE"
    BEKLE = "BEKLE"
    SAT = "SAT"
    YETERSIZ_VERI = "YETERSİZ VERİ"


@dataclass
class StrategyIntegrationConfig:
    min_bars: int = 220
    buy_score: float = 62.0
    sell_score: float = 42.0
    allow_al_aday: bool = False
    default_quantity: float | None = None
    max_history_per_symbol: int = 1_000

    def validate(self) -> None:
        if self.min_bars < 2:
            raise ValueError("min_bars en az 2 olmalıdır.")
        if not 0 <= self.sell_score <= 100:
            raise ValueError("sell_score 0-100 aralığında olmalıdır.")
        if not 0 <= self.buy_score <= 100:
            raise ValueError("buy_score 0-100 aralığında olmalıdır.")
        if self.sell_score >= self.buy_score:
            raise ValueError("sell_score, buy_score değerinden küçük olmalıdır.")
        if self.default_quantity is not None and self.default_quantity <= 0:
            raise ValueError("default_quantity pozitif olmalıdır.")
        if self.max_history_per_symbol < self.min_bars:
            raise ValueError("max_history_per_symbol min_bars'tan küçük olamaz.")


@dataclass
class Candle:
    symbol: str
    interval: str
    open_time: int
    close_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_count: int = 0

    @classmethod
    def from_kline(cls, symbol: str, kline: KlineUpdate) -> "Candle":
        return cls(
            symbol=symbol,
            interval=kline.interval,
            open_time=kline.open_time,
            close_time=kline.close_time,
            open=float(kline.open),
            high=float(kline.high),
            low=float(kline.low),
            close=float(kline.close),
            volume=float(kline.volume),
            trade_count=int(kline.trade_count),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AlphaScanSignal:
    symbol: str
    label: SignalLabel
    score: float
    reason: str
    price: float
    stop: float | None = None
    target: float | None = None
    quantity: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["label"] = self.label.value
        return data


class DecisionEngineProtocol(Protocol):
    def evaluate(
        self,
        *,
        symbol: str,
        candles: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> Any:
        ...


class CandleHistoryStore:
    def __init__(self, max_history_per_symbol: int = 1_000) -> None:
        if max_history_per_symbol <= 0:
            raise ValueError("max_history_per_symbol pozitif olmalıdır.")
        self.max_history_per_symbol = max_history_per_symbol
        self._history: dict[tuple[str, str], deque[Candle]] = {}

    def append(self, candle: Candle) -> bool:
        key = (candle.symbol.upper(), candle.interval)
        series = self._history.setdefault(
            key,
            deque(maxlen=self.max_history_per_symbol),
        )

        for existing in reversed(series):
            if existing.open_time == candle.open_time:
                if existing.close_time == candle.close_time:
                    return False
                break

        series.append(candle)
        ordered = sorted(series, key=lambda item: item.open_time)
        self._history[key] = deque(
            ordered[-self.max_history_per_symbol :],
            maxlen=self.max_history_per_symbol,
        )
        return True

    def get(self, symbol: str, interval: str) -> list[Candle]:
        return list(self._history.get((symbol.upper(), interval), ()))

    def count(self, symbol: str, interval: str) -> int:
        return len(self.get(symbol, interval))

    def latest(self, symbol: str, interval: str) -> Candle | None:
        candles = self.get(symbol, interval)
        return candles[-1] if candles else None

    def snapshot(self) -> dict[str, list[dict[str, Any]]]:
        return {
            f"{symbol}:{interval}": [item.to_dict() for item in candles]
            for (symbol, interval), candles in self._history.items()
        }


class RuleBasedAlphaScanDecisionEngine:
    def evaluate(
        self,
        *,
        symbol: str,
        candles: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        if len(candles) < 2:
            return {
                "symbol": symbol,
                "label": SignalLabel.YETERSIZ_VERI.value,
                "score": 0.0,
                "reason": "Karar için yeterli mum yok.",
                "price": candles[-1]["close"] if candles else 0.0,
            }

        closes = [float(row["close"]) for row in candles]
        volumes = [float(row.get("volume", 0.0)) for row in candles]
        last = closes[-1]
        previous = closes[-2]
        short_window = closes[-min(20, len(closes)) :]
        long_window = closes[-min(50, len(closes)) :]
        volume_window = volumes[-min(20, len(volumes)) :]

        short_avg = sum(short_window) / len(short_window)
        long_avg = sum(long_window) / len(long_window)
        volume_avg = sum(volume_window) / len(volume_window) if volume_window else 0.0
        last_volume = volumes[-1] if volumes else 0.0

        score = 0.0
        reasons: list[str] = []

        if last > short_avg:
            score += 30
            reasons.append("Fiyat kısa ortalamanın üstünde")
        if short_avg > long_avg:
            score += 25
            reasons.append("Kısa trend güçlü")
        if last > previous:
            score += 20
            reasons.append("Son mum pozitif")
        if volume_avg > 0 and last_volume >= volume_avg * 0.85:
            score += 15
            reasons.append("Hacim yeterli")
        if last >= max(closes[-min(10, len(closes)) :]) * 0.98:
            score += 10
            reasons.append("Fiyat kısa dönem zirvesine yakın")

        if score >= 75:
            label = SignalLabel.NET_AL
        elif score >= 62:
            label = SignalLabel.AL_ADAY
        elif score >= 45:
            label = SignalLabel.IZLE
        else:
            label = SignalLabel.BEKLE

        stop = last * 0.93 if last > 0 else None
        target = last * 1.10 if last > 0 else None

        return {
            "symbol": symbol,
            "label": label.value,
            "score": score,
            "reason": ", ".join(reasons) or "Pozitif koşul oluşmadı",
            "price": last,
            "stop": stop,
            "target": target,
            "metadata": {
                "short_average": short_avg,
                "long_average": long_avg,
                "last_volume": last_volume,
                "volume_average": volume_avg,
            },
        }


class AlphaScanRuntimeStrategyAdapter:
    def __init__(
        self,
        *,
        decision_engine: Any | None = None,
        config: StrategyIntegrationConfig | None = None,
        history_store: CandleHistoryStore | None = None,
    ) -> None:
        self.config = config or StrategyIntegrationConfig()
        self.config.validate()
        self.decision_engine = decision_engine or RuleBasedAlphaScanDecisionEngine()
        self.history_store = history_store or CandleHistoryStore(
            self.config.max_history_per_symbol
        )
        self.last_signal: dict[str, AlphaScanSignal] = {}

    def ingest_event(self, event: MarketDataEvent) -> bool:
        if event.event_type != MarketDataEventType.KLINE:
            return False
        kline = event.payload
        if not isinstance(kline, KlineUpdate) or not kline.closed:
            return False
        candle = Candle.from_kline(event.symbol, kline)
        return self.history_store.append(candle)

    def seed_history(
        self,
        symbol: str,
        interval: str,
        candles: Iterable[Mapping[str, Any] | Candle],
    ) -> int:
        count = 0
        for item in candles:
            if isinstance(item, Candle):
                candle = item
            else:
                candle = Candle(
                    symbol=symbol.upper(),
                    interval=interval,
                    open_time=int(item["open_time"]),
                    close_time=int(item.get("close_time", item["open_time"])),
                    open=float(item["open"]),
                    high=float(item["high"]),
                    low=float(item["low"]),
                    close=float(item["close"]),
                    volume=float(item.get("volume", 0.0)),
                    trade_count=int(item.get("trade_count", 0)),
                )
            count += int(self.history_store.append(candle))
        return count

    def evaluate(
        self,
        *,
        symbol: str,
        interval: str,
        kline: KlineUpdate,
        context: dict[str, Any],
    ) -> StrategyDecision:
        if kline.closed:
            self.history_store.append(Candle.from_kline(symbol, kline))

        candles = self.history_store.get(symbol, interval)
        if len(candles) < self.config.min_bars:
            return StrategyDecision(
                symbol=symbol,
                action=RuntimeAction.HOLD,
                score=0.0,
                reason=(
                    f"Yetersiz veri: {len(candles)}/{self.config.min_bars} mum."
                ),
                price=kline.close,
                metadata={"bars": len(candles), "required": self.config.min_bars},
            )

        raw = self._call_decision_engine(
            symbol=symbol,
            candles=[item.to_dict() for item in candles],
            context=context,
        )
        signal = self._normalize_signal(symbol, raw, kline.close)
        self.last_signal[symbol] = signal

        action = self._map_action(signal)
        return StrategyDecision(
            symbol=symbol,
            action=action,
            score=signal.score,
            reason=signal.reason,
            quantity=signal.quantity or self.config.default_quantity,
            price=signal.price,
            metadata={
                **signal.metadata,
                "label": signal.label.value,
                "stop": signal.stop,
                "target": signal.target,
                "bars": len(candles),
            },
        )

    def _call_decision_engine(
        self,
        *,
        symbol: str,
        candles: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> Any:
        engine = self.decision_engine
        if hasattr(engine, "evaluate"):
            return engine.evaluate(
                symbol=symbol,
                candles=candles,
                context=context,
            )
        if hasattr(engine, "analyze"):
            return engine.analyze(
                symbol=symbol,
                candles=candles,
                context=context,
            )
        if hasattr(engine, "decide"):
            return engine.decide(
                symbol=symbol,
                candles=candles,
                context=context,
            )
        if callable(engine):
            return engine(
                symbol=symbol,
                candles=candles,
                context=context,
            )
        raise TypeError("Karar motoru evaluate/analyze/decide veya callable olmalıdır.")

    def _normalize_signal(
        self,
        symbol: str,
        raw: Any,
        fallback_price: float,
    ) -> AlphaScanSignal:
        if isinstance(raw, AlphaScanSignal):
            return raw

        if hasattr(raw, "to_dict"):
            raw = raw.to_dict()
        elif not isinstance(raw, Mapping) and hasattr(raw, "__dict__"):
            raw = vars(raw)

        if not isinstance(raw, Mapping):
            raise TypeError("Karar motoru sonucu mapping veya AlphaScanSignal olmalıdır.")

        label_value = (
            raw.get("label")
            or raw.get("decision")
            or raw.get("karar")
            or raw.get("action")
            or SignalLabel.BEKLE.value
        )
        label = self._parse_label(label_value)

        score_value = (
            raw.get("score")
            if raw.get("score") is not None
            else raw.get("puan", 0.0)
        )
        score = float(score_value)
        if not math.isfinite(score):
            score = 0.0
        score = min(100.0, max(0.0, score))

        reason = str(
            raw.get("reason")
            or raw.get("neden")
            or raw.get("reasons")
            or "Karar motoru açıklama üretmedi."
        )
        price = float(raw.get("price", raw.get("fiyat", fallback_price)))
        stop = self._optional_float(raw.get("stop", raw.get("stop_price")))
        target = self._optional_float(raw.get("target", raw.get("target_price")))
        quantity = self._optional_float(raw.get("quantity", raw.get("miktar")))
        metadata = dict(raw.get("metadata") or {})

        return AlphaScanSignal(
            symbol=str(raw.get("symbol", raw.get("kod", symbol))).upper(),
            label=label,
            score=score,
            reason=reason,
            price=price,
            stop=stop,
            target=target,
            quantity=quantity,
            metadata=metadata,
        )

    def _map_action(self, signal: AlphaScanSignal) -> RuntimeAction:
        if signal.label == SignalLabel.SAT or signal.score <= self.config.sell_score:
            return RuntimeAction.SELL
        if signal.label == SignalLabel.NET_AL and signal.score >= self.config.buy_score:
            return RuntimeAction.BUY
        if (
            self.config.allow_al_aday
            and signal.label == SignalLabel.AL_ADAY
            and signal.score >= self.config.buy_score
        ):
            return RuntimeAction.BUY
        return RuntimeAction.HOLD

    @staticmethod
    def _parse_label(value: Any) -> SignalLabel:
        text = str(value).strip().upper()
        aliases = {
            "NET_AL": SignalLabel.NET_AL,
            "NET AL": SignalLabel.NET_AL,
            "BUY": SignalLabel.NET_AL,
            "AL": SignalLabel.NET_AL,
            "AL_ADAY": SignalLabel.AL_ADAY,
            "AL ADAY": SignalLabel.AL_ADAY,
            "İZLE": SignalLabel.IZLE,
            "IZLE": SignalLabel.IZLE,
            "WATCH": SignalLabel.IZLE,
            "BEKLE": SignalLabel.BEKLE,
            "HOLD": SignalLabel.BEKLE,
            "SAT": SignalLabel.SAT,
            "SELL": SignalLabel.SAT,
            "YETERSİZ VERİ": SignalLabel.YETERSIZ_VERI,
            "YETERSIZ VERI": SignalLabel.YETERSIZ_VERI,
        }
        return aliases.get(text, SignalLabel.BEKLE)

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        if value is None or value == "":
            return None
        return float(value)


class RuntimeStrategyBridge:
    def __init__(
        self,
        *,
        runtime: Any,
        strategy_adapter: AlphaScanRuntimeStrategyAdapter,
    ) -> None:
        self.runtime = runtime
        self.strategy_adapter = strategy_adapter
        self.bound = False

    def bind(self) -> None:
        if self.bound:
            return
        self.runtime.strategy = self.strategy_adapter
        self.runtime.market_data_engine.add_callback(
            self.strategy_adapter.ingest_event
        )
        self.bound = True

    def status(self) -> dict[str, Any]:
        return {
            "bound": self.bound,
            "strategy": type(self.strategy_adapter).__name__,
            "history_keys": len(self.strategy_adapter.history_store.snapshot()),
            "last_signal_count": len(self.strategy_adapter.last_signal),
        }
