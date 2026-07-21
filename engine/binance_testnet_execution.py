from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Protocol
import math
import time

from engine.robot_runtime import RuntimeAction, StrategyDecision


class TestnetOrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class TestnetOrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class TestnetOrderStatus(str, Enum):
    NEW = "NEW"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"
    UNKNOWN = "UNKNOWN"


class BinanceTestnetClientProtocol(Protocol):
    def create_order(self, **kwargs: Any) -> dict[str, Any]:
        ...

    def get_order(self, **kwargs: Any) -> dict[str, Any]:
        ...

    def cancel_order(self, **kwargs: Any) -> dict[str, Any]:
        ...

    def get_symbol_info(self, symbol: str) -> dict[str, Any]:
        ...


@dataclass
class BinanceTestnetExecutionConfig:
    enabled: bool = False
    require_explicit_enable: bool = True
    default_order_type: TestnetOrderType = TestnetOrderType.MARKET
    default_quote_order_value: float = 50.0
    max_quote_order_value: float = 250.0
    min_quote_order_value: float = 10.0
    allow_market_orders: bool = True
    allow_limit_orders: bool = True
    allow_duplicate_open_orders: bool = False
    recv_window: int = 5000
    max_order_history: int = 5000
    dry_run: bool = True

    def validate(self) -> None:
        if self.default_quote_order_value <= 0:
            raise ValueError("default_quote_order_value pozitif olmalıdır.")
        if self.max_quote_order_value <= 0:
            raise ValueError("max_quote_order_value pozitif olmalıdır.")
        if self.min_quote_order_value <= 0:
            raise ValueError("min_quote_order_value pozitif olmalıdır.")
        if self.min_quote_order_value > self.max_quote_order_value:
            raise ValueError("Minimum emir değeri maksimumdan büyük olamaz.")
        if self.recv_window <= 0:
            raise ValueError("recv_window pozitif olmalıdır.")
        if self.max_order_history <= 0:
            raise ValueError("max_order_history pozitif olmalıdır.")


@dataclass
class SymbolRules:
    symbol: str
    min_qty: float = 0.0
    max_qty: float = float("inf")
    step_size: float = 0.0
    min_notional: float = 0.0
    tick_size: float = 0.0

    def normalize_quantity(self, quantity: float) -> float:
        if quantity <= 0 or not math.isfinite(quantity):
            raise ValueError("quantity pozitif ve sonlu olmalıdır.")
        value = min(quantity, self.max_qty)
        if self.step_size > 0:
            steps = math.floor((value + 1e-12) / self.step_size)
            value = steps * self.step_size
        if value < self.min_qty:
            return 0.0
        return float(f"{value:.12f}")

    def normalize_price(self, price: float) -> float:
        if price <= 0 or not math.isfinite(price):
            raise ValueError("price pozitif ve sonlu olmalıdır.")
        value = price
        if self.tick_size > 0:
            ticks = math.floor((value + 1e-12) / self.tick_size)
            value = ticks * self.tick_size
        return float(f"{value:.12f}")


@dataclass
class TestnetOrderRecord:
    local_id: int
    symbol: str
    side: TestnetOrderSide
    order_type: TestnetOrderType
    status: TestnetOrderStatus
    requested_quantity: float
    normalized_quantity: float
    requested_price: float | None
    normalized_price: float | None
    quote_order_value: float | None
    exchange_order_id: str | None
    client_order_id: str | None
    executed_quantity: float
    cumulative_quote_quantity: float
    reason: str
    timestamp: float
    raw_response: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["side"] = self.side.value
        data["order_type"] = self.order_type.value
        data["status"] = self.status.value
        return data


class BinanceTestnetExecutionEngine:
    def __init__(
        self,
        *,
        client: BinanceTestnetClientProtocol,
        config: BinanceTestnetExecutionConfig | None = None,
        time_fn=time.time,
    ) -> None:
        self.client = client
        self.config = config or BinanceTestnetExecutionConfig()
        self.config.validate()
        self.time_fn = time_fn
        self.orders: list[TestnetOrderRecord] = []
        self.open_orders: dict[str, TestnetOrderRecord] = {}
        self._symbol_rules_cache: dict[str, SymbolRules] = {}
        self._local_id = 0

    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        return symbol.replace("/", "").replace("-", "").upper()

    def enable(self) -> None:
        self.config.enabled = True

    def disable(self) -> None:
        self.config.enabled = False

    def execute(
        self,
        decision: StrategyDecision,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}
        if decision.action not in {RuntimeAction.BUY, RuntimeAction.SELL}:
            return self._record_skipped(
                decision,
                "HOLD/SKIP kararı için Testnet emri oluşturulmadı.",
            ).to_dict()

        if self.config.require_explicit_enable and not self.config.enabled:
            return self._record_skipped(
                decision,
                "Testnet execution açıkça etkinleştirilmedi.",
            ).to_dict()

        symbol = self.normalize_symbol(decision.symbol)
        if (
            symbol in self.open_orders
            and not self.config.allow_duplicate_open_orders
        ):
            return self._record_rejected(
                decision,
                "Aynı sembolde açık Testnet emri bulunuyor.",
            ).to_dict()

        order_type = self._resolve_order_type(decision)
        if order_type == TestnetOrderType.MARKET and not self.config.allow_market_orders:
            return self._record_rejected(
                decision,
                "Market emirleri devre dışı.",
            ).to_dict()
        if order_type == TestnetOrderType.LIMIT and not self.config.allow_limit_orders:
            return self._record_rejected(
                decision,
                "Limit emirleri devre dışı.",
            ).to_dict()

        try:
            payload, requested_quantity, normalized_quantity, requested_price, normalized_price, quote_value = (
                self._build_order_payload(decision, context, order_type)
            )

            if self.config.dry_run:
                response = {
                    "symbol": symbol,
                    "orderId": f"DRY-{self._local_id + 1}",
                    "clientOrderId": f"alphascan-dry-{self._local_id + 1}",
                    "status": "NEW",
                    "executedQty": "0",
                    "cummulativeQuoteQty": "0",
                    "dryRun": True,
                    "request": payload,
                }
            else:
                response = self.client.create_order(**payload)

            record = self._record_response(
                decision=decision,
                order_type=order_type,
                requested_quantity=requested_quantity,
                normalized_quantity=normalized_quantity,
                requested_price=requested_price,
                normalized_price=normalized_price,
                quote_order_value=quote_value,
                response=response,
            )

            if record.status in {
                TestnetOrderStatus.NEW,
                TestnetOrderStatus.PARTIALLY_FILLED,
            }:
                self.open_orders[symbol] = record
            else:
                self.open_orders.pop(symbol, None)

            return record.to_dict()
        except Exception as exc:
            return self._record_error(decision, str(exc)).to_dict()

    def refresh_order(
        self,
        symbol: str,
        *,
        exchange_order_id: str | None = None,
        client_order_id: str | None = None,
    ) -> dict[str, Any]:
        symbol = self.normalize_symbol(symbol)
        record = self.open_orders.get(symbol)
        if record is None and exchange_order_id is None and client_order_id is None:
            raise ValueError("İzlenecek açık emir bulunamadı.")

        params: dict[str, Any] = {"symbol": symbol, "recvWindow": self.config.recv_window}
        if exchange_order_id is not None:
            params["orderId"] = exchange_order_id
        elif client_order_id is not None:
            params["origClientOrderId"] = client_order_id
        elif record and record.exchange_order_id:
            params["orderId"] = record.exchange_order_id
        elif record and record.client_order_id:
            params["origClientOrderId"] = record.client_order_id
        else:
            raise ValueError("Emir kimliği bulunamadı.")

        response = self.client.get_order(**params)
        status = self._map_status(response.get("status"))

        if record:
            record.status = status
            record.executed_quantity = float(response.get("executedQty", 0) or 0)
            record.cumulative_quote_quantity = float(
                response.get("cummulativeQuoteQty", 0)
                or response.get("cumulativeQuoteQty", 0)
                or 0
            )
            record.raw_response = dict(response)

        if status not in {
            TestnetOrderStatus.NEW,
            TestnetOrderStatus.PARTIALLY_FILLED,
        }:
            self.open_orders.pop(symbol, None)

        return dict(response)

    def cancel_open_order(self, symbol: str) -> dict[str, Any]:
        symbol = self.normalize_symbol(symbol)
        record = self.open_orders.get(symbol)
        if record is None:
            raise ValueError("İptal edilecek açık emir bulunamadı.")

        params: dict[str, Any] = {"symbol": symbol, "recvWindow": self.config.recv_window}
        if record.exchange_order_id:
            params["orderId"] = record.exchange_order_id
        elif record.client_order_id:
            params["origClientOrderId"] = record.client_order_id
        else:
            raise ValueError("Emir kimliği bulunamadı.")

        response = self.client.cancel_order(**params)
        record.status = self._map_status(response.get("status", "CANCELED"))
        record.raw_response = dict(response)
        self.open_orders.pop(symbol, None)
        return dict(response)

    def get_symbol_rules(self, symbol: str, *, refresh: bool = False) -> SymbolRules:
        symbol = self.normalize_symbol(symbol)
        if symbol in self._symbol_rules_cache and not refresh:
            return self._symbol_rules_cache[symbol]

        info = self.client.get_symbol_info(symbol)
        rules = SymbolRules(symbol=symbol)
        for filter_item in info.get("filters", []):
            filter_type = filter_item.get("filterType")
            if filter_type == "LOT_SIZE":
                rules.min_qty = float(filter_item.get("minQty", 0) or 0)
                rules.max_qty = float(filter_item.get("maxQty", "inf") or "inf")
                rules.step_size = float(filter_item.get("stepSize", 0) or 0)
            elif filter_type in {"MIN_NOTIONAL", "NOTIONAL"}:
                rules.min_notional = float(
                    filter_item.get("minNotional", 0)
                    or filter_item.get("notional", 0)
                    or 0
                )
            elif filter_type == "PRICE_FILTER":
                rules.tick_size = float(filter_item.get("tickSize", 0) or 0)

        self._symbol_rules_cache[symbol] = rules
        return rules

    def orders_report(self, limit: int = 100) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        return [order.to_dict() for order in self.orders[-limit:]]

    def health_report(self) -> dict[str, Any]:
        return {
            "enabled": self.config.enabled,
            "dry_run": self.config.dry_run,
            "order_count": len(self.orders),
            "open_order_count": len(self.open_orders),
            "cached_symbols": len(self._symbol_rules_cache),
        }

    def _build_order_payload(
        self,
        decision: StrategyDecision,
        context: dict[str, Any],
        order_type: TestnetOrderType,
    ) -> tuple[dict[str, Any], float, float, float | None, float | None, float | None]:
        symbol = self.normalize_symbol(decision.symbol)
        rules = self.get_symbol_rules(symbol)
        side = (
            TestnetOrderSide.BUY
            if decision.action == RuntimeAction.BUY
            else TestnetOrderSide.SELL
        )

        price = self._resolve_price(decision, context)
        requested_quantity = float(decision.quantity or 0.0)
        quote_value = decision.metadata.get(
            "quote_order_value",
            decision.metadata.get(
                "order_value",
                self.config.default_quote_order_value,
            ),
        )
        quote_value = min(float(quote_value), self.config.max_quote_order_value)

        if quote_value < self.config.min_quote_order_value:
            raise ValueError("Emir değeri minimum limitin altında.")

        if requested_quantity <= 0:
            requested_quantity = quote_value / price

        normalized_quantity = rules.normalize_quantity(requested_quantity)
        if normalized_quantity <= 0:
            raise ValueError("Miktar sembol LOT_SIZE kuralına uymuyor.")

        notional = normalized_quantity * price
        if rules.min_notional > 0 and notional < rules.min_notional:
            raise ValueError("Emir sembol minimum notional kuralının altında.")

        normalized_price: float | None = None
        payload: dict[str, Any] = {
            "symbol": symbol,
            "side": side.value,
            "type": order_type.value,
            "quantity": self._format_decimal(normalized_quantity),
            "recvWindow": self.config.recv_window,
        }

        if order_type == TestnetOrderType.LIMIT:
            normalized_price = rules.normalize_price(price)
            payload.update(
                {
                    "price": self._format_decimal(normalized_price),
                    "timeInForce": str(
                        decision.metadata.get("time_in_force", "GTC")
                    ),
                }
            )

        client_order_id = decision.metadata.get("client_order_id")
        if client_order_id:
            payload["newClientOrderId"] = str(client_order_id)

        return (
            payload,
            requested_quantity,
            normalized_quantity,
            price,
            normalized_price,
            quote_value,
        )

    def _resolve_order_type(self, decision: StrategyDecision) -> TestnetOrderType:
        raw = decision.metadata.get(
            "order_type",
            self.config.default_order_type.value,
        )
        return TestnetOrderType(str(raw).upper())

    def _resolve_price(
        self,
        decision: StrategyDecision,
        context: dict[str, Any],
    ) -> float:
        if decision.price is not None:
            price = float(decision.price)
        else:
            kline = context.get("kline") or {}
            snapshot = context.get("market_snapshot") or {}
            prices = snapshot.get("last_prices") or {}
            symbol = self.normalize_symbol(decision.symbol)

            if isinstance(kline, dict) and kline.get("close") is not None:
                price = float(kline["close"])
            elif symbol in prices:
                price = float(prices[symbol])
            else:
                raise ValueError("Emir fiyatı bulunamadı.")

        if price <= 0 or not math.isfinite(price):
            raise ValueError("Emir fiyatı pozitif ve sonlu olmalıdır.")
        return price

    @staticmethod
    def _format_decimal(value: float) -> str:
        text = f"{value:.12f}".rstrip("0").rstrip(".")
        return text or "0"

    def _record_response(
        self,
        *,
        decision: StrategyDecision,
        order_type: TestnetOrderType,
        requested_quantity: float,
        normalized_quantity: float,
        requested_price: float | None,
        normalized_price: float | None,
        quote_order_value: float | None,
        response: dict[str, Any],
    ) -> TestnetOrderRecord:
        self._local_id += 1
        record = TestnetOrderRecord(
            local_id=self._local_id,
            symbol=self.normalize_symbol(decision.symbol),
            side=(
                TestnetOrderSide.BUY
                if decision.action == RuntimeAction.BUY
                else TestnetOrderSide.SELL
            ),
            order_type=order_type,
            status=self._map_status(response.get("status")),
            requested_quantity=requested_quantity,
            normalized_quantity=normalized_quantity,
            requested_price=requested_price,
            normalized_price=normalized_price,
            quote_order_value=quote_order_value,
            exchange_order_id=(
                str(response.get("orderId"))
                if response.get("orderId") is not None
                else None
            ),
            client_order_id=response.get("clientOrderId"),
            executed_quantity=float(response.get("executedQty", 0) or 0),
            cumulative_quote_quantity=float(
                response.get("cummulativeQuoteQty", 0)
                or response.get("cumulativeQuoteQty", 0)
                or 0
            ),
            reason=decision.reason,
            timestamp=self.time_fn(),
            raw_response=dict(response),
            metadata=dict(decision.metadata),
        )
        self._append_order(record)
        return record

    def _record_skipped(
        self,
        decision: StrategyDecision,
        reason: str,
    ) -> TestnetOrderRecord:
        return self._record_simple(
            decision,
            TestnetOrderStatus.SKIPPED,
            reason,
        )

    def _record_rejected(
        self,
        decision: StrategyDecision,
        reason: str,
    ) -> TestnetOrderRecord:
        return self._record_simple(
            decision,
            TestnetOrderStatus.REJECTED,
            reason,
        )

    def _record_error(
        self,
        decision: StrategyDecision,
        reason: str,
    ) -> TestnetOrderRecord:
        return self._record_simple(
            decision,
            TestnetOrderStatus.ERROR,
            reason,
        )

    def _record_simple(
        self,
        decision: StrategyDecision,
        status: TestnetOrderStatus,
        reason: str,
    ) -> TestnetOrderRecord:
        self._local_id += 1
        record = TestnetOrderRecord(
            local_id=self._local_id,
            symbol=self.normalize_symbol(decision.symbol),
            side=(
                TestnetOrderSide.BUY
                if decision.action == RuntimeAction.BUY
                else TestnetOrderSide.SELL
            ),
            order_type=self.config.default_order_type,
            status=status,
            requested_quantity=float(decision.quantity or 0.0),
            normalized_quantity=0.0,
            requested_price=decision.price,
            normalized_price=None,
            quote_order_value=None,
            exchange_order_id=None,
            client_order_id=None,
            executed_quantity=0.0,
            cumulative_quote_quantity=0.0,
            reason=reason,
            timestamp=self.time_fn(),
            raw_response={},
            metadata=dict(decision.metadata),
        )
        self._append_order(record)
        return record

    def _append_order(self, record: TestnetOrderRecord) -> None:
        self.orders.append(record)
        if len(self.orders) > self.config.max_order_history:
            del self.orders[: len(self.orders) - self.config.max_order_history]

    @staticmethod
    def _map_status(value: Any) -> TestnetOrderStatus:
        text = str(value or "UNKNOWN").upper()
        try:
            return TestnetOrderStatus(text)
        except ValueError:
            return TestnetOrderStatus.UNKNOWN


class BinanceTestnetRuntimeBridge:
    def __init__(
        self,
        *,
        runtime: Any,
        execution_engine: BinanceTestnetExecutionEngine,
    ) -> None:
        self.runtime = runtime
        self.execution_engine = execution_engine
        self.bound = False

    def bind(self) -> None:
        if self.bound:
            return
        self.runtime.execution = self.execution_engine
        self.bound = True

    def enable(self) -> None:
        self.execution_engine.enable()

    def disable(self) -> None:
        self.execution_engine.disable()

    def dashboard(self) -> dict[str, Any]:
        return {
            "bound": self.bound,
            "health": self.execution_engine.health_report(),
            "open_orders": {
                symbol: order.to_dict()
                for symbol, order in self.execution_engine.open_orders.items()
            },
            "recent_orders": self.execution_engine.orders_report(limit=20),
        }
