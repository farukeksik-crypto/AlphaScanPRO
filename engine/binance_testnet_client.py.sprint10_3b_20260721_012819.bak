from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from engine.exchange_layer import (
    ExchangeAdapter,
    ExchangeAuthenticationError,
    ExchangeBalance,
    ExchangeConfig,
    ExchangeConnectionError,
    ExchangeMode,
    ExchangeOrder,
    ExchangeOrderError,
    ExchangeOrderRequest,
    ExchangeOrderSide,
    ExchangeOrderStatus,
    ExchangeOrderType,
    ExchangePosition,
    ExchangeRateLimitError,
)


BINANCE_SPOT_TESTNET_BASE_URL = "https://testnet.binance.vision"
BINANCE_SPOT_LIVE_BASE_URL = "https://api.binance.com"


@dataclass
class BinanceCredentials:
    api_key: str
    api_secret: str

    @classmethod
    def from_env(
        cls,
        *,
        api_key_name: str = "BINANCE_TESTNET_API_KEY",
        api_secret_name: str = "BINANCE_TESTNET_API_SECRET",
    ) -> "BinanceCredentials":
        return cls(
            api_key=os.getenv(api_key_name, "").strip(),
            api_secret=os.getenv(api_secret_name, "").strip(),
        )

    def validate(self) -> None:
        if not self.api_key:
            raise ExchangeAuthenticationError(
                "Binance Testnet API key bulunamadı."
            )
        if not self.api_secret:
            raise ExchangeAuthenticationError(
                "Binance Testnet API secret bulunamadı."
            )


class BinanceHttpTransport:
    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str] | None = None,
        timeout: float = 20.0,
    ) -> Any:
        request = Request(
            url=url,
            method=method.upper(),
            headers=dict(headers or {}),
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = response.read().decode("utf-8")
                return json.loads(payload) if payload else {}
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(body)
            except json.JSONDecodeError:
                detail = {"msg": body or str(exc)}
            if exc.code in {401, 403}:
                raise ExchangeAuthenticationError(
                    detail.get("msg", "Binance kimlik doğrulama hatası.")
                ) from exc
            if exc.code in {418, 429}:
                raise ExchangeRateLimitError(
                    detail.get("msg", "Binance rate limit hatası.")
                ) from exc
            raise ExchangeOrderError(
                detail.get("msg", f"Binance HTTP hatası: {exc.code}")
            ) from exc
        except URLError as exc:
            raise ExchangeConnectionError(
                f"Binance bağlantı hatası: {exc.reason}"
            ) from exc


class BinanceSpotTestnetClient(ExchangeAdapter):
    def __init__(
        self,
        config: ExchangeConfig | None = None,
        *,
        credentials: BinanceCredentials | None = None,
        transport: BinanceHttpTransport | Any | None = None,
        time_ms_fn: Callable[[], int] | None = None,
    ) -> None:
        resolved = config or ExchangeConfig(
            mode=ExchangeMode.TESTNET,
            exchange_name="BINANCE",
            recv_window_ms=5_000,
            request_timeout_seconds=20.0,
            max_retries=3,
            retry_delay_seconds=0.0,
            allow_live_trading=False,
        )
        if resolved.mode not in {ExchangeMode.TESTNET, ExchangeMode.LIVE}:
            raise ValueError(
                "BinanceSpotTestnetClient yalnızca TESTNET veya LIVE modunda çalışır."
            )
        super().__init__(resolved)
        self.credentials = credentials or BinanceCredentials.from_env()
        self.transport = transport or BinanceHttpTransport()
        self.time_ms_fn = time_ms_fn or (lambda: int(time.time() * 1000))
        self.base_url = (
            BINANCE_SPOT_TESTNET_BASE_URL
            if self.config.mode == ExchangeMode.TESTNET
            else BINANCE_SPOT_LIVE_BASE_URL
        )

    def connect(self) -> bool:
        self.credentials.validate()
        self.ping()
        self.connected = True
        return True

    def disconnect(self) -> None:
        self.connected = False

    def ping(self) -> bool:
        payload = self._public_request("GET", "/api/v3/ping")
        return payload == {} or payload is not None

    def get_server_time(self) -> int:
        payload = self._public_request("GET", "/api/v3/time")
        return int(payload["serverTime"])

    def get_price(self, symbol: str) -> float:
        payload = self._public_request(
            "GET",
            "/api/v3/ticker/price",
            {"symbol": self._normalize_symbol(symbol)},
        )
        return float(payload["price"])

    def get_exchange_info(
        self,
        symbol: str | None = None,
    ) -> dict[str, Any]:
        params = (
            {"symbol": self._normalize_symbol(symbol)}
            if symbol
            else None
        )
        return dict(
            self._public_request("GET", "/api/v3/exchangeInfo", params)
        )

    def get_balances(self) -> list[ExchangeBalance]:
        self._require_connection()
        payload = self._signed_request("GET", "/api/v3/account")
        return [
            ExchangeBalance(
                asset=str(row["asset"]),
                free=float(row["free"]),
                locked=float(row["locked"]),
            )
            for row in payload.get("balances", [])
            if float(row["free"]) != 0 or float(row["locked"]) != 0
        ]

    def get_positions(self) -> list[ExchangePosition]:
        self._require_connection()
        balances = self.get_balances()
        positions: list[ExchangePosition] = []
        for balance in balances:
            if balance.asset in {"USDT", "USDC", "FDUSD", "TRY", "BTC"}:
                continue
            symbol = f"{balance.asset}USDT"
            try:
                current_price = self.get_price(symbol)
            except (ExchangeOrderError, KeyError, ValueError):
                continue
            positions.append(
                ExchangePosition(
                    symbol=symbol,
                    quantity=balance.total,
                    average_price=0.0,
                    current_price=current_price,
                )
            )
        return positions

    def place_order(self, request: ExchangeOrderRequest) -> ExchangeOrder:
        self._require_connection()
        request.validate()

        params: dict[str, Any] = {
            "symbol": self._normalize_symbol(request.symbol),
            "side": request.side.value,
            "type": request.order_type.value,
            "quantity": self._format_decimal(request.quantity),
            "newClientOrderId": request.client_order_id,
            "newOrderRespType": "FULL",
        }

        if request.order_type in {
            ExchangeOrderType.LIMIT,
            ExchangeOrderType.STOP_LIMIT,
        }:
            params["price"] = self._format_decimal(float(request.price))
            params["timeInForce"] = "GTC"

        if request.order_type in {
            ExchangeOrderType.STOP,
            ExchangeOrderType.STOP_LIMIT,
        }:
            params["stopPrice"] = self._format_decimal(
                float(request.stop_price)
            )

        payload = self._signed_request("POST", "/api/v3/order", params)
        return self._map_order(payload, fallback=request)

    def test_order(self, request: ExchangeOrderRequest) -> bool:
        self._require_connection()
        request.validate()
        params: dict[str, Any] = {
            "symbol": self._normalize_symbol(request.symbol),
            "side": request.side.value,
            "type": request.order_type.value,
            "quantity": self._format_decimal(request.quantity),
        }
        if request.order_type in {
            ExchangeOrderType.LIMIT,
            ExchangeOrderType.STOP_LIMIT,
        }:
            params["price"] = self._format_decimal(float(request.price))
            params["timeInForce"] = "GTC"
        if request.order_type in {
            ExchangeOrderType.STOP,
            ExchangeOrderType.STOP_LIMIT,
        }:
            params["stopPrice"] = self._format_decimal(
                float(request.stop_price)
            )
        payload = self._signed_request(
            "POST",
            "/api/v3/order/test",
            params,
        )
        return payload == {} or payload is not None

    def get_order(self, exchange_order_id: str) -> ExchangeOrder:
        self._require_connection()
        payload = self._signed_request(
            "GET",
            "/api/v3/order",
            {"orderId": exchange_order_id},
        )
        return self._map_order(payload)

    def get_symbol_order(
        self,
        *,
        symbol: str,
        exchange_order_id: str,
    ) -> ExchangeOrder:
        self._require_connection()
        payload = self._signed_request(
            "GET",
            "/api/v3/order",
            {
                "symbol": self._normalize_symbol(symbol),
                "orderId": exchange_order_id,
            },
        )
        return self._map_order(payload)

    def cancel_order(self, exchange_order_id: str) -> ExchangeOrder:
        raise ExchangeOrderError(
            "Binance iptal işlemi için symbol gereklidir; cancel_symbol_order kullanın."
        )

    def cancel_symbol_order(
        self,
        *,
        symbol: str,
        exchange_order_id: str,
    ) -> ExchangeOrder:
        self._require_connection()
        payload = self._signed_request(
            "DELETE",
            "/api/v3/order",
            {
                "symbol": self._normalize_symbol(symbol),
                "orderId": exchange_order_id,
            },
        )
        return self._map_order(payload)

    def _public_request(
        self,
        method: str,
        path: str,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        query = urlencode(dict(params or {}))
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{query}"
        return self.retry.run(
            lambda: self.transport.request(
                method=method,
                url=url,
                headers={},
                timeout=self.config.request_timeout_seconds,
            )
        )

    def _signed_request(
        self,
        method: str,
        path: str,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        self.credentials.validate()
        payload = dict(params or {})
        payload["recvWindow"] = self.config.recv_window_ms
        payload["timestamp"] = self.time_ms_fn()

        unsigned_query = urlencode(payload)
        signature = hmac.new(
            self.credentials.api_secret.encode("utf-8"),
            unsigned_query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        signed_query = f"{unsigned_query}&signature={signature}"
        url = f"{self.base_url}{path}?{signed_query}"

        return self.retry.run(
            lambda: self.transport.request(
                method=method,
                url=url,
                headers={"X-MBX-APIKEY": self.credentials.api_key},
                timeout=self.config.request_timeout_seconds,
            )
        )

    def _map_order(
        self,
        payload: Mapping[str, Any],
        fallback: ExchangeOrderRequest | None = None,
    ) -> ExchangeOrder:
        status_raw = str(payload.get("status", "UNKNOWN")).upper()
        status = (
            ExchangeOrderStatus(status_raw)
            if status_raw in ExchangeOrderStatus._value2member_map_
            else ExchangeOrderStatus.UNKNOWN
        )

        side_raw = str(
            payload.get(
                "side",
                fallback.side.value if fallback else "BUY",
            )
        ).upper()
        type_raw = str(
            payload.get(
                "type",
                fallback.order_type.value if fallback else "MARKET",
            )
        ).upper()

        quantity = float(
            payload.get(
                "origQty",
                fallback.quantity if fallback else 0.0,
            )
        )
        filled = float(payload.get("executedQty", 0.0))
        cumulative_quote = float(
            payload.get("cummulativeQuoteQty", 0.0)
        )
        average_price = (
            cumulative_quote / filled
            if filled > 0 and cumulative_quote > 0
            else float(payload.get("price", 0.0))
        )

        commission = 0.0
        for fill in payload.get("fills", []) or []:
            commission += float(fill.get("commission", 0.0))

        return ExchangeOrder(
            exchange_order_id=str(
                payload.get("orderId", payload.get("clientOrderId", ""))
            ),
            client_order_id=str(
                payload.get(
                    "clientOrderId",
                    fallback.client_order_id if fallback else "",
                )
            ),
            symbol=str(
                payload.get(
                    "symbol",
                    self._normalize_symbol(fallback.symbol)
                    if fallback
                    else "",
                )
            ),
            side=ExchangeOrderSide(side_raw),
            order_type=ExchangeOrderType(type_raw),
            status=status,
            quantity=quantity,
            filled_quantity=filled,
            average_price=average_price,
            commission=commission,
            raw=dict(payload),
        )

    def _require_connection(self) -> None:
        if not self.connected:
            raise ExchangeConnectionError(
                "Binance Testnet bağlantısı kapalı."
            )

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        return symbol.replace("/", "").replace("-", "").upper()

    @staticmethod
    def _format_decimal(value: float) -> str:
        return format(Decimal(str(value)).normalize(), "f")
