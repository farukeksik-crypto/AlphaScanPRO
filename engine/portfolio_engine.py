from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable


@dataclass
class PortfolioConfig:
    max_open_positions: int = 5
    max_asset_weight_pct: float = 25.0
    max_market_weight_pct: float = 70.0
    max_sector_weight_pct: float = 35.0
    max_total_exposure_pct: float = 95.0
    max_correlated_positions: int = 2
    correlation_threshold: float = 0.80


@dataclass
class PortfolioPosition:
    symbol: str
    market: str
    quantity: float
    entry_price: float
    current_price: float
    stop_price: float | None = None
    sector: str | None = None
    side: str = "LONG"

    @property
    def market_value(self) -> float:
        return float(self.quantity) * float(self.current_price)

    @property
    def cost_value(self) -> float:
        return float(self.quantity) * float(self.entry_price)

    @property
    def unrealized_pnl(self) -> float:
        direction = 1.0 if self.side.upper() == "LONG" else -1.0
        return (
            float(self.current_price) - float(self.entry_price)
        ) * float(self.quantity) * direction

    @property
    def risk_amount(self) -> float:
        if self.stop_price is None:
            return 0.0
        return abs(
            float(self.entry_price) - float(self.stop_price)
        ) * float(self.quantity)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.update(
            {
                "market_value": round(self.market_value, 8),
                "cost_value": round(self.cost_value, 8),
                "unrealized_pnl": round(self.unrealized_pnl, 8),
                "risk_amount": round(self.risk_amount, 8),
            }
        )
        return data


@dataclass
class PortfolioDecision:
    allowed: bool
    code: str
    reason: str
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PortfolioEngine:
    def __init__(
        self,
        config: PortfolioConfig | None = None,
        positions: Iterable[PortfolioPosition | dict[str, Any]] | None = None,
    ) -> None:
        self.config = config or PortfolioConfig()
        self._positions: list[PortfolioPosition] = []
        for position in positions or []:
            self.add_position(position)

    def add_position(
        self,
        position: PortfolioPosition | dict[str, Any],
    ) -> PortfolioPosition:
        item = (
            position
            if isinstance(position, PortfolioPosition)
            else PortfolioPosition(**position)
        )
        self._validate_position(item)
        self._positions.append(item)
        return item

    def remove_position(self, symbol: str) -> int:
        before = len(self._positions)
        self._positions = [
            position
            for position in self._positions
            if position.symbol != symbol
        ]
        return before - len(self._positions)

    def list_positions(self) -> list[PortfolioPosition]:
        return list(self._positions)

    def total_market_value(self) -> float:
        return round(
            sum(position.market_value for position in self._positions),
            8,
        )

    def total_unrealized_pnl(self) -> float:
        return round(
            sum(position.unrealized_pnl for position in self._positions),
            8,
        )

    def total_risk_amount(self) -> float:
        return round(
            sum(position.risk_amount for position in self._positions),
            8,
        )

    def exposure_by_asset(self) -> dict[str, float]:
        totals: dict[str, float] = {}
        for position in self._positions:
            totals[position.symbol] = (
                totals.get(position.symbol, 0.0)
                + position.market_value
            )
        return {
            key: round(value, 8)
            for key, value in sorted(totals.items())
        }

    def exposure_by_market(self) -> dict[str, float]:
        totals: dict[str, float] = {}
        for position in self._positions:
            key = position.market.upper()
            totals[key] = totals.get(key, 0.0) + position.market_value
        return {
            key: round(value, 8)
            for key, value in sorted(totals.items())
        }

    def exposure_by_sector(self) -> dict[str, float]:
        totals: dict[str, float] = {}
        for position in self._positions:
            key = (position.sector or "UNKNOWN").upper()
            totals[key] = totals.get(key, 0.0) + position.market_value
        return {
            key: round(value, 8)
            for key, value in sorted(totals.items())
        }

    def weights(
        self,
        *,
        equity: float,
    ) -> dict[str, dict[str, float] | float]:
        self._validate_positive(equity, "equity")

        def percent_map(values: dict[str, float]) -> dict[str, float]:
            return {
                key: round(value / equity * 100.0, 8)
                for key, value in values.items()
            }

        total_exposure_pct = self.total_market_value() / equity * 100.0
        return {
            "asset": percent_map(self.exposure_by_asset()),
            "market": percent_map(self.exposure_by_market()),
            "sector": percent_map(self.exposure_by_sector()),
            "total_exposure_pct": round(total_exposure_pct, 8),
        }

    def check_capacity(
        self,
        *,
        equity: float,
        candidate: PortfolioPosition | dict[str, Any],
    ) -> PortfolioDecision:
        self._validate_positive(equity, "equity")
        item = (
            candidate
            if isinstance(candidate, PortfolioPosition)
            else PortfolioPosition(**candidate)
        )
        self._validate_position(item)

        if len(self._positions) >= self.config.max_open_positions:
            return PortfolioDecision(
                allowed=False,
                code="MAX_OPEN_POSITIONS",
                reason="Maksimum açık pozisyon sayısına ulaşıldı.",
                details={
                    "open_positions": len(self._positions),
                    "limit": self.config.max_open_positions,
                },
            )

        current_total = self.total_market_value()
        proposed_total = current_total + item.market_value
        proposed_total_pct = proposed_total / equity * 100.0

        asset_total = self.exposure_by_asset().get(item.symbol, 0.0)
        proposed_asset_pct = (
            asset_total + item.market_value
        ) / equity * 100.0

        if proposed_asset_pct > self.config.max_asset_weight_pct:
            return PortfolioDecision(
                allowed=False,
                code="MAX_ASSET_WEIGHT",
                reason="Tek varlık ağırlık limiti aşılacak.",
                details={
                    "symbol": item.symbol,
                    "proposed_asset_weight_pct": round(
                        proposed_asset_pct,
                        8,
                    ),
                    "limit": self.config.max_asset_weight_pct,
                },
            )

        market_key = item.market.upper()
        market_total = self.exposure_by_market().get(market_key, 0.0)
        proposed_market_pct = (
            market_total + item.market_value
        ) / equity * 100.0

        if proposed_market_pct > self.config.max_market_weight_pct:
            return PortfolioDecision(
                allowed=False,
                code="MAX_MARKET_WEIGHT",
                reason="Piyasa ağırlık limiti aşılacak.",
                details={
                    "market": market_key,
                    "proposed_market_weight_pct": round(
                        proposed_market_pct,
                        8,
                    ),
                    "limit": self.config.max_market_weight_pct,
                },
            )

        sector_key = (item.sector or "UNKNOWN").upper()
        sector_total = self.exposure_by_sector().get(sector_key, 0.0)
        proposed_sector_pct = (
            sector_total + item.market_value
        ) / equity * 100.0

        if proposed_sector_pct > self.config.max_sector_weight_pct:
            return PortfolioDecision(
                allowed=False,
                code="MAX_SECTOR_WEIGHT",
                reason="Sektör ağırlık limiti aşılacak.",
                details={
                    "sector": sector_key,
                    "proposed_sector_weight_pct": round(
                        proposed_sector_pct,
                        8,
                    ),
                    "limit": self.config.max_sector_weight_pct,
                },
            )

        if proposed_total_pct > self.config.max_total_exposure_pct:
            return PortfolioDecision(
                allowed=False,
                code="MAX_TOTAL_EXPOSURE",
                reason="Toplam portföy maruziyet limiti aşılacak.",
                details={
                    "proposed_total_exposure_pct": round(
                        proposed_total_pct,
                        8,
                    ),
                    "limit": self.config.max_total_exposure_pct,
                },
            )

        return PortfolioDecision(
            allowed=True,
            code="OK",
            reason="Portföy kapasitesi yeni pozisyon için uygun.",
            details={
                "proposed_total_exposure_pct": round(
                    proposed_total_pct,
                    8,
                ),
                "proposed_asset_weight_pct": round(
                    proposed_asset_pct,
                    8,
                ),
                "proposed_market_weight_pct": round(
                    proposed_market_pct,
                    8,
                ),
                "proposed_sector_weight_pct": round(
                    proposed_sector_pct,
                    8,
                ),
            },
        )

    def check_correlation(
        self,
        *,
        candidate_symbol: str,
        correlations: dict[str, float],
    ) -> PortfolioDecision:
        correlated = []
        for position in self._positions:
            value = correlations.get(position.symbol)
            if value is None:
                continue
            if abs(float(value)) >= self.config.correlation_threshold:
                correlated.append(
                    {
                        "symbol": position.symbol,
                        "correlation": round(float(value), 8),
                    }
                )

        if len(correlated) >= self.config.max_correlated_positions:
            return PortfolioDecision(
                allowed=False,
                code="CORRELATION_LIMIT",
                reason="Yüksek korelasyonlu pozisyon limiti aşılacak.",
                details={
                    "candidate_symbol": candidate_symbol,
                    "correlated_positions": correlated,
                    "limit": self.config.max_correlated_positions,
                    "threshold": self.config.correlation_threshold,
                },
            )

        return PortfolioDecision(
            allowed=True,
            code="OK",
            reason="Korelasyon limiti uygun.",
            details={
                "candidate_symbol": candidate_symbol,
                "correlated_positions": correlated,
            },
        )

    def evaluate_candidate(
        self,
        *,
        equity: float,
        candidate: PortfolioPosition | dict[str, Any],
        correlations: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        item = (
            candidate
            if isinstance(candidate, PortfolioPosition)
            else PortfolioPosition(**candidate)
        )

        capacity = self.check_capacity(
            equity=equity,
            candidate=item,
        )
        if not capacity.allowed:
            return {
                "allowed": False,
                "stage": "capacity",
                "decision": capacity.to_dict(),
            }

        correlation = self.check_correlation(
            candidate_symbol=item.symbol,
            correlations=correlations or {},
        )
        if not correlation.allowed:
            return {
                "allowed": False,
                "stage": "correlation",
                "decision": correlation.to_dict(),
            }

        return {
            "allowed": True,
            "stage": "approved",
            "candidate": item.to_dict(),
            "checks": {
                "capacity": capacity.to_dict(),
                "correlation": correlation.to_dict(),
            },
        }

    def portfolio_report(
        self,
        *,
        equity: float,
        cash: float,
    ) -> dict[str, Any]:
        self._validate_positive(equity, "equity")
        if cash < 0:
            raise ValueError("cash negatif olamaz.")

        return {
            "config": asdict(self.config),
            "position_count": len(self._positions),
            "positions": [
                position.to_dict()
                for position in self._positions
            ],
            "cash": round(float(cash), 8),
            "total_market_value": self.total_market_value(),
            "total_unrealized_pnl": self.total_unrealized_pnl(),
            "total_risk_amount": self.total_risk_amount(),
            "weights": self.weights(equity=equity),
            "available_equity_pct": round(
                max(
                    0.0,
                    100.0
                    - self.total_market_value() / equity * 100.0,
                ),
                8,
            ),
        }

    @staticmethod
    def _validate_position(position: PortfolioPosition) -> None:
        if not position.symbol:
            raise ValueError("symbol boş olamaz.")
        if not position.market:
            raise ValueError("market boş olamaz.")
        if float(position.quantity) <= 0:
            raise ValueError("quantity 0'dan büyük olmalıdır.")
        if float(position.entry_price) <= 0:
            raise ValueError("entry_price 0'dan büyük olmalıdır.")
        if float(position.current_price) <= 0:
            raise ValueError("current_price 0'dan büyük olmalıdır.")

    @staticmethod
    def _validate_positive(value: float, name: str) -> None:
        if float(value) <= 0:
            raise ValueError(f"{name} 0'dan büyük olmalıdır.")
