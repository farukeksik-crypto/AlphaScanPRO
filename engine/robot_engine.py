from __future__ import annotations

from engine.ai_decision_engine import AIDecisionEngine

from engine.sector_correlation_engine import SectorCorrelationEngine

from engine.market_regime_engine import MarketRegimeEngine
from engine.adaptive_strategy_engine import AdaptiveStrategyEngine
from engine.multi_timeframe_intelligence import MultiTimeframeIntelligence

from engine.smart_exit import SmartExitConfig, SmartExitAction, evaluate_smart_exit

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd

from engine.trade_intelligence import analyze_closed_trade
from engine.portfolio_risk_manager import PortfolioRiskConfig
from engine.robot_risk_enforcement import RobotRiskEnforcer
from engine.position_lifecycle import (
    PositionLifecycleRepository,
    SafePositionLifecycle,
)


@dataclass
class RobotConfig:
    starting_balance: float = 1_000_000.0
    commission_rate: float = 0.001
    slippage_rate: float = 0.0005
    break_even_trigger_pct: float = 0.03
    break_even_buffer_pct: float = 0.002
    break_even_extra_buffer_pct: float = 0.0002
    break_even_include_costs: bool = True
    trailing_stop_pct: float = 0.015
    atr_trailing_enabled: bool = True
    atr_trailing_multiplier: float = 2.0
    atr_trailing_min_pct: float = 0.008
    atr_trailing_max_pct: float = 0.040
    target1_sell_ratio: float = 0.50

    # Sprint 6.3F-C — Kademeli Smart Exit
    smart_exit_partial_enabled: bool = True
    smart_exit_watch_score: int = 35
    smart_exit_partial_score: int = 50
    smart_exit_full_score: int = 70
    smart_exit_min_confirmations: int = 2
    smart_exit_full_min_confirmations: int = 3
    smart_exit_partial_sell_ratio: float = 0.50

    # Sprint 6.3F-A — Zaman bazlı çıkış
    time_exit_enabled: bool = True
    max_holding_hours: float = 72.0
    
    # Sprint 6.4.1 — Daily Risk Guard
    risk_lock_enabled: bool = True
    max_daily_loss_pct: float = 3.0
    max_daily_trades: int = 20
    max_consecutive_losses: int = 4
    max_daily_commission_pct: float = 1.0

    time_exit_min_profit_pct: float = 0.50
    max_positions: int = 5
    position_size_pct: float = 0.20
    # Sprint 6.5 — Risk bazlı dinamik pozisyon büyüklüğü
    risk_based_position_sizing: bool = True
    risk_per_trade_pct: float = 1.0
    min_position_size_pct: float = 0.02
    max_position_size_pct: float = 0.20

    # Sprint 6.6 — Portföy Risk Yöneticisi
    portfolio_risk_guard_enabled: bool = True
    max_portfolio_risk_pct: float = 4.0
    max_portfolio_exposure_pct: float = 80.0
    max_single_position_exposure_pct: float = 25.0
    min_cash_reserve_pct: float = 20.0
    robot_risk_enforcement_enabled: bool = True
    max_group_exposure_pct: float = 40.0

    minimum_score: float = 75.0
    minimum_confidence: float = 0.0
    minimum_probability: float = 55.0
    allowed_decisions: tuple[str, ...] = ("NET AL", "AL ADAY")
    allowed_risks: tuple[str, ...] = ("Düşük", "Orta")

    # High Risk Override
    high_risk_override_enabled: bool = True
    high_risk_override_min_score: float = 85.0
    high_risk_override_min_confidence: float = 70.0
    high_risk_override_min_probability: float = 70.0
    strategy_profile: str = "Default"
    market: str = "BIST"
    account_id: str = "bist_main"
    currency: str = "TRY"

    # Sprint 7.1B — Market Regime
    market_regime_guard_enabled: bool = True
    market_regime_risk_scaling_enabled: bool = True
    market_regime_position_scaling_enabled: bool = True

    # Sprint 10.16B — Adaptive Strategy Engine
    adaptive_strategy_enabled: bool = True
    multi_timeframe_intelligence_enabled: bool = True

    # Sprint 7.2B — Sector & Correlation Guard
    sector_correlation_guard_enabled: bool = True
    max_sector_positions: int = 2
    correlation_limit: float = 0.85
    correlation_min_observations: int = 30

    # Sprint 8.1B — AI Decision Guard
    ai_decision_enabled: bool = True
    ai_minimum_trade_score: float = 70.0
    ai_strong_buy_score: float = 88.0
    ai_buy_score: float = 78.0
    ai_watch_score: float = 65.0


class RobotEngine:
    """
    AlphaScan PRO sanal işlem motoru.

    Gerçek emir göndermez. Tüm işlemleri SQLite üzerinde sanal olarak kaydeder.
    """

    def __init__(self, database, config: RobotConfig | None = None):
        self.database = database
        self.config = config or RobotConfig()
        self.market = str(self.config.market or "BIST").upper()
        self.account_id = str(self.config.account_id or "bist_main")
        self.currency = str(self.config.currency or "TRY")
        self.market_regime_engine = MarketRegimeEngine()
        self.multi_timeframe_intelligence = MultiTimeframeIntelligence(regime_engine=self.market_regime_engine)
        self.adaptive_strategy_engine = AdaptiveStrategyEngine(
            base_minimum_entry_score=self.config.minimum_score,
            base_trailing_atr_multiplier=self.config.atr_trailing_multiplier,
            base_max_holding_hours=self.config.max_holding_hours,
        )
        self.sector_correlation_engine = SectorCorrelationEngine(
            max_sector_positions=self.config.max_sector_positions,
            correlation_limit=self.config.correlation_limit,
            min_observations=self.config.correlation_min_observations,
        )
        self.ai_decision_engine = AIDecisionEngine(
            minimum_trade_score=self.config.ai_minimum_trade_score,
            strong_buy_score=self.config.ai_strong_buy_score,
            buy_score=self.config.ai_buy_score,
            watch_score=self.config.ai_watch_score,
        )
        self.robot_risk_enforcer = RobotRiskEnforcer(
            self.database,
            account_id=self.account_id,
            market=self.market,
            config=PortfolioRiskConfig(
                initial_equity=float(self.config.starting_balance),
                max_open_positions=int(self.config.max_positions),
                max_total_exposure_pct=float(self.config.max_portfolio_exposure_pct),
                max_symbol_exposure_pct=float(self.config.max_single_position_exposure_pct),
                max_group_exposure_pct=float(self.config.max_group_exposure_pct),
                max_total_risk_pct=float(self.config.max_portfolio_risk_pct),
                max_risk_per_trade_pct=float(self.config.risk_per_trade_pct),
                daily_loss_limit_pct=float(self.config.max_daily_loss_pct),
                allow_position_reduction=True,
            ),
        )
        self.position_lifecycle = SafePositionLifecycle(
            PositionLifecycleRepository(self.database),
        )
    def _record_event(
        self,
        event_type: str,
        symbol: str,
        position_id: int | str,
        **extra,
    ) -> None:
        self.position_lifecycle.record(
            position_id=str(position_id),
            symbol=symbol,
            event_type=event_type,
            market=self.market,
            universe=getattr(self.config, "universe", None),
            account_id=self.account_id,
            **extra,
        )
    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    def get_state(self) -> dict[str, Any]:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT enabled, balance, daily_profit, total_profit, updated_at,
                       starting_balance, currency, market, account_id
                FROM robot_accounts
                WHERE account_id = ?
                """,
                (self.account_id,),
            ).fetchone()

        if row is None:
            return {
                "enabled": False,
                "balance": self.config.starting_balance,
                "daily_profit": 0.0,
                "total_profit": 0.0,
                "updated_at": None,
                "starting_balance": self.config.starting_balance,
                "currency": self.currency,
                "market": self.market,
                "account_id": self.account_id,
            }

        return {
            "enabled": bool(row[0]),
            "balance": float(row[1]),
            "daily_profit": float(row[2]),
            "total_profit": float(row[3]),
            "updated_at": row[4],
            "starting_balance": float(row[5]),
            "currency": str(row[6]),
            "market": str(row[7]),
            "account_id": str(row[8]),
        }

    def set_enabled(self, enabled: bool) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE robot_accounts
                SET enabled = ?, updated_at = ?
                WHERE account_id = ?
                """,
                (int(enabled), self._now(), self.account_id),
            )
            connection.commit()

    def reset_account(self) -> None:
        with self.database.connect() as connection:
            connection.execute(
                "DELETE FROM positions WHERE account_id = ?",
                (self.account_id,),
            )
            connection.execute(
                "DELETE FROM trade_history WHERE account_id = ?",
                (self.account_id,),
            )
            connection.execute(
                """
                UPDATE robot_accounts
                SET enabled = 0,
                    balance = starting_balance,
                    daily_profit = 0,
                    total_profit = 0,
                    updated_at = ?
                WHERE account_id = ?
                """,
                (self._now(), self.account_id),
            )
            connection.commit()

    def get_open_positions(self) -> pd.DataFrame:
        query = """
            SELECT
                id,
                symbol,
                quantity,
                COALESCE(initial_quantity, quantity) AS initial_quantity,
                entry_price,
                stop_price,
                target1,
                target2,
                opened_at,
                status,
                market,
                universe,
                technical_score,
                confidence_score,
                confidence_label,
                decision,
                entry_reason,
                strategy_profile,
                highest_price,
                lowest_price,
                COALESCE(break_even_active, 0) AS break_even_active,
                COALESCE(trailing_active, 0) AS trailing_active,
                COALESCE(target1_completed, 0) AS target1_completed
            FROM positions
            WHERE status = 'OPEN' AND account_id = ?
            ORDER BY opened_at DESC
        """

        with self.database.connect() as connection:
            return pd.read_sql_query(
                query,
                connection,
                params=(self.account_id,),
            )

    def get_trade_history(self, limit: int = 200) -> pd.DataFrame:
        query = """
            SELECT
                id,
                symbol,
                side,
                quantity,
                price,
                commission,
                profit,
                created_at,
                market,
                universe,
                technical_score,
                confidence_score,
                confidence_label,
                decision,
                reason,
                strategy_profile,
                position_id,
                entry_price,
                exit_price,
                profit_pct,
                holding_minutes,
                mfe_pct,
                mae_pct,
                risk_pct,
                reward_pct,
                risk_reward,
                entry_efficiency,
                exit_efficiency,
                trade_quality_score,
                trade_grade
            FROM trade_history
            WHERE account_id = ?
            ORDER BY id DESC
            LIMIT ?
        """

        with self.database.connect() as connection:
            return pd.read_sql_query(
                query,
                connection,
                params=(self.account_id, int(limit)),
            )

    def has_open_position(self, symbol: str) -> bool:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM positions
                WHERE symbol = ?
                  AND status = 'OPEN'
                  AND account_id = ?
                LIMIT 1
                """,
                (symbol, self.account_id),
            ).fetchone()

        return row is not None

    def _open_position_count(self) -> int:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*)
                FROM positions
                WHERE status = 'OPEN'
                  AND account_id = ?
                """,
                (self.account_id,),
            ).fetchone()

        return int(row[0] if row else 0)

    def get_today_trade_count(self) -> int:
        """Bugün açılan pozisyon sayısını döndürür."""
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*)
                FROM trade_history
                WHERE account_id = ?
                  AND side = 'BUY'
                  AND DATE(created_at) = DATE('now', 'localtime')
                """,
                (self.account_id,),
            ).fetchone()
        return int(row[0] if row else 0)

    def get_today_realized_profit(self) -> float:
        """Bugünkü gerçekleşmiş toplam kâr/zararı döndürür."""
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(SUM(profit), 0)
                FROM trade_history
                WHERE account_id = ?
                  AND side = 'SELL'
                  AND DATE(created_at) = DATE('now', 'localtime')
                """,
                (self.account_id,),
            ).fetchone()
        return float(row[0] if row else 0.0)

    def get_today_commission(self) -> float:
        """Bugün ödenen toplam komisyonu döndürür."""
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(SUM(commission), 0)
                FROM trade_history
                WHERE account_id = ?
                  AND DATE(created_at) = DATE('now', 'localtime')
                """,
                (self.account_id,),
            ).fetchone()
        return float(row[0] if row else 0.0)

    def get_consecutive_losses(self) -> int:
        """Son kapanan işlemlerden itibaren arka arkaya zarar sayısını döndürür."""
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT profit
                FROM trade_history
                WHERE account_id = ?
                  AND side = 'SELL'
                ORDER BY id DESC
                LIMIT ?
                """,
                (
                    self.account_id,
                    max(1, int(self.config.max_consecutive_losses)),
                ),
            ).fetchall()

        count = 0
        for row in rows:
            if float(row[0] or 0.0) < 0:
                count += 1
            else:
                break
        return count

    def risk_lock_reason(self) -> str | None:
        """Yeni pozisyon açılmasını engelleyen risk sebebini döndürür."""
        if not self.config.risk_lock_enabled:
            return None

        state = self.get_state()
        starting_balance = max(
            float(state.get("starting_balance", self.config.starting_balance)),
            0.0,
        )

        daily_profit = self.get_today_realized_profit()
        daily_loss_limit = (
            starting_balance * float(self.config.max_daily_loss_pct) / 100.0
        )
        if daily_loss_limit > 0 and daily_profit <= -daily_loss_limit:
            return (
                "Günlük zarar limiti aşıldı: "
                f"{daily_profit:.2f} / -{daily_loss_limit:.2f} {self.currency}"
            )

        trade_count = self.get_today_trade_count()
        if (
            int(self.config.max_daily_trades) > 0
            and trade_count >= int(self.config.max_daily_trades)
        ):
            return (
                "Günlük işlem limiti doldu: "
                f"{trade_count}/{int(self.config.max_daily_trades)}"
            )

        loss_count = self.get_consecutive_losses()
        if (
            int(self.config.max_consecutive_losses) > 0
            and loss_count >= int(self.config.max_consecutive_losses)
        ):
            return (
                "Arka arkaya zarar limiti doldu: "
                f"{loss_count}/{int(self.config.max_consecutive_losses)}"
            )

        commission = self.get_today_commission()
        commission_limit = (
            starting_balance
            * float(self.config.max_daily_commission_pct)
            / 100.0
        )
        if commission_limit > 0 and commission >= commission_limit:
            return (
                "Günlük komisyon limiti doldu: "
                f"{commission:.2f}/{commission_limit:.2f} {self.currency}"
            )

        return None

    def get_portfolio_risk_summary(
        self,
        *,
        state: dict[str, Any] | None = None,
    ) -> dict[str, float]:
        """Açık pozisyonların toplam maruziyet ve stop riskini hesaplar."""
        state = state or self.get_state()
        starting_balance = float(
            state.get("starting_balance")
            or self.config.starting_balance
            or 0.0
        )
        cash_balance = float(state.get("balance") or 0.0)
        positions = self.get_open_positions()

        if positions.empty:
            return {
                "starting_balance": starting_balance,
                "cash_balance": cash_balance,
                "open_exposure": 0.0,
                "open_risk": 0.0,
                "exposure_pct": 0.0,
                "risk_pct": 0.0,
                "cash_reserve_pct": (
                    cash_balance / starting_balance * 100.0
                    if starting_balance > 0
                    else 0.0
                ),
            }

        quantity = pd.to_numeric(
            positions["quantity"], errors="coerce"
        ).fillna(0.0)
        entry_price = pd.to_numeric(
            positions["entry_price"], errors="coerce"
        ).fillna(0.0)
        stop_price = pd.to_numeric(
            positions["stop_price"], errors="coerce"
        ).fillna(0.0)

        open_exposure = float((quantity * entry_price).sum())
        open_risk = float(
            (quantity * (entry_price - stop_price).clip(lower=0)).sum()
        )

        return {
            "starting_balance": starting_balance,
            "cash_balance": cash_balance,
            "open_exposure": open_exposure,
            "open_risk": open_risk,
            "exposure_pct": (
                open_exposure / starting_balance * 100.0
                if starting_balance > 0
                else 0.0
            ),
            "risk_pct": (
                open_risk / starting_balance * 100.0
                if starting_balance > 0
                else 0.0
            ),
            "cash_reserve_pct": (
                cash_balance / starting_balance * 100.0
                if starting_balance > 0
                else 0.0
            ),
        }

    def portfolio_risk_lock_reason(
        self,
        *,
        state: dict[str, Any],
        price: float,
        stop_price: float,
        quantity: float,
    ) -> str:
        """Yeni işlem sonrası portföy limitlerini kontrol eder."""
        if not self.config.portfolio_risk_guard_enabled:
            return ""

        starting_balance = float(
            state.get("starting_balance")
            or self.config.starting_balance
            or 0.0
        )
        if starting_balance <= 0:
            return "Başlangıç sermayesi hesaplanamadı."

        summary = self.get_portfolio_risk_summary(state=state)
        new_exposure = float(quantity) * float(price)
        new_risk = float(quantity) * max(float(price) - float(stop_price), 0.0)

        single_exposure_pct = new_exposure / starting_balance * 100.0
        projected_exposure_pct = (
            summary["open_exposure"] + new_exposure
        ) / starting_balance * 100.0
        projected_risk_pct = (
            summary["open_risk"] + new_risk
        ) / starting_balance * 100.0

        commission = new_exposure * float(self.config.commission_rate)
        projected_cash = float(state.get("balance") or 0.0) - (
            new_exposure + commission
        )
        projected_cash_reserve_pct = projected_cash / starting_balance * 100.0

        if single_exposure_pct > float(
            self.config.max_single_position_exposure_pct
        ):
            return (
                "Tek pozisyon maruziyet limiti aşılıyor: "
                f"%{single_exposure_pct:.2f} > "
                f"%{self.config.max_single_position_exposure_pct:.2f}"
            )

        if projected_exposure_pct > float(
            self.config.max_portfolio_exposure_pct
        ):
            return (
                "Toplam portföy maruziyet limiti aşılıyor: "
                f"%{projected_exposure_pct:.2f} > "
                f"%{self.config.max_portfolio_exposure_pct:.2f}"
            )

        if projected_risk_pct > float(self.config.max_portfolio_risk_pct):
            return (
                "Toplam portföy stop riski limiti aşılıyor: "
                f"%{projected_risk_pct:.2f} > "
                f"%{self.config.max_portfolio_risk_pct:.2f}"
            )

        if projected_cash_reserve_pct < float(
            self.config.min_cash_reserve_pct
        ):
            return (
                "Minimum nakit rezervi korunamıyor: "
                f"%{projected_cash_reserve_pct:.2f} < "
                f"%{self.config.min_cash_reserve_pct:.2f}"
            )

        return ""

    def calculate_position_quantity(
        self,
        *,
        balance: float,
        price: float,
        stop_price: float,
    ) -> dict[str, float | str | bool]:
        """Stop mesafesine göre güvenli pozisyon miktarını hesaplar."""
        balance = float(balance)
        price = float(price)
        stop_price = float(stop_price)

        if balance <= 0 or price <= 0:
            return {
                "ok": False,
                "message": "Pozisyon büyüklüğü için geçersiz bakiye veya fiyat.",
            }

        max_budget = balance * float(self.config.max_position_size_pct)
        min_budget = balance * float(self.config.min_position_size_pct)

        if not self.config.risk_based_position_sizing:
            budget = min(
                balance * float(self.config.position_size_pct),
                max_budget,
            )
            quantity = budget / (
                price * (1.0 + self.config.commission_rate)
            )
            return {
                "ok": quantity > 0,
                "quantity": quantity,
                "budget": budget,
                "risk_amount": 0.0,
                "stop_distance": max(price - stop_price, 0.0),
                "sizing_mode": "FIXED_PERCENT",
            }

        stop_distance = price - stop_price
        if stop_distance <= 0:
            return {
                "ok": False,
                "message": "Risk bazlı pozisyon için stop fiyatı giriş fiyatından düşük olmalı.",
            }

        risk_amount = (
            balance * float(self.config.risk_per_trade_pct) / 100.0
        )
        quantity_by_risk = risk_amount / stop_distance
        quantity_by_budget = max_budget / (
            price * (1.0 + self.config.commission_rate)
        )
        quantity = min(quantity_by_risk, quantity_by_budget)
        budget = quantity * price

        if budget < min_budget:
            min_quantity = min_budget / (
                price * (1.0 + self.config.commission_rate)
            )
            min_quantity_risk = min_quantity * stop_distance
            if min_quantity_risk <= risk_amount:
                quantity = min(min_quantity, quantity_by_budget)
                budget = quantity * price

        if quantity <= 0:
            return {
                "ok": False,
                "message": "Dinamik pozisyon miktarı hesaplanamadı.",
            }

        estimated_risk = quantity * stop_distance
        return {
            "ok": True,
            "quantity": quantity,
            "budget": budget,
            "risk_amount": estimated_risk,
            "stop_distance": stop_distance,
            "sizing_mode": "RISK_BASED",
        }

    def get_market_regime_result(self, market_frame=None) -> dict[str, Any]:
        if not getattr(self.config, "market_regime_guard_enabled", True):
            return {"regime": "DISABLED", "score": 100.0,
                    "confidence": 100.0, "allow_new_positions": True,
                    "risk_multiplier": 1.0,
                    "max_positions_multiplier": 1.0,
                    "cash_target_pct": 0.0,
                    "reasons": ["Market regime guard kapalı."]}

        if market_frame is None:
            return {"regime": "NOT_PROVIDED", "score": 0.0,
                    "confidence": 0.0, "allow_new_positions": True,
                    "risk_multiplier": 1.0,
                    "max_positions_multiplier": 1.0,
                    "cash_target_pct": 0.0,
                    "reasons": ["Rejim verisi yok; mevcut davranış korundu."]}

        return self.market_regime_engine.analyze(market_frame).to_dict()

    def get_adaptive_strategy_policy(self, market_frame=None) -> dict[str, Any]:
        regime = self.get_market_regime_result(market_frame)
        if not getattr(self.config, "adaptive_strategy_enabled", True):
            return {
                "profile": "DISABLED",
                "allow_new_positions": True,
                "minimum_entry_score": float(self.config.minimum_score),
                "position_size_multiplier": 1.0,
                "target1_multiplier": 1.0,
                "target2_multiplier": 1.0,
                "trailing_atr_multiplier": float(self.config.atr_trailing_multiplier),
                "smart_exit_score_delta": 0,
                "max_holding_hours_multiplier": 1.0,
                "reasons": ["Adaptive Strategy kapalı."],
            }
        return self.adaptive_strategy_engine.build_policy(regime).to_dict()

    def get_multi_timeframe_result(self, multi_timeframe_frames=None) -> dict[str, Any]:
        if not getattr(self.config, "multi_timeframe_intelligence_enabled", True):
            return {
                "dominant_regime": "DISABLED", "alignment_score": 100.0,
                "confidence": 100.0, "conflict_level": "LOW",
                "allow_new_positions": True, "risk_multiplier": 1.0,
                "position_size_multiplier": 1.0,
                "minimum_entry_score_delta": 0.0, "recommendation": "NORMAL",
                "reasons": ["Multi-Timeframe Intelligence kapalı."], "timeframes": [],
            }
        if not multi_timeframe_frames:
            return {
                "dominant_regime": "NOT_PROVIDED", "alignment_score": 100.0,
                "confidence": 100.0, "conflict_level": "LOW",
                "allow_new_positions": True, "risk_multiplier": 1.0,
                "position_size_multiplier": 1.0,
                "minimum_entry_score_delta": 0.0, "recommendation": "NORMAL",
                "reasons": ["Çoklu zaman dilimi verisi yok; mevcut davranış korundu."], "timeframes": [],
            }
        return self.multi_timeframe_intelligence.analyze_frames(multi_timeframe_frames).to_dict()

    def market_regime_lock_reason(self, market_frame=None) -> str:
        result = self.get_market_regime_result(market_frame)
        if not result.get("allow_new_positions", True):
            regime = str(result.get("regime", "BİLİNMİYOR"))
            score = float(result.get("score", 0.0) or 0.0)
            return f"Piyasa rejimi yeni işleme izin vermiyor: {regime} (skor={score:.2f})"
        return ""

    def apply_market_regime_to_quantity(self, quantity: float, market_frame=None):
        result = self.get_market_regime_result(market_frame)
        multiplier = 1.0
        if getattr(self.config, "market_regime_risk_scaling_enabled", True):
            multiplier = float(result.get("risk_multiplier", 1.0) or 0.0)
        return max(0.0, float(quantity) * multiplier), result

    def get_regime_adjusted_max_positions(self, market_frame=None):
        result = self.get_market_regime_result(market_frame)
        multiplier = 1.0
        if getattr(self.config, "market_regime_position_scaling_enabled", True):
            multiplier = float(result.get("max_positions_multiplier", 1.0) or 0.0)
        return max(0, int(self.config.max_positions * multiplier)), result

    def get_sector_correlation_result(
        self,
        *,
        symbol: str,
        sector: str | None = None,
        open_positions=None,
        candidate_prices=None,
        position_price_map=None,
    ) -> dict[str, Any]:
        if not getattr(self.config, "sector_correlation_guard_enabled", True):
            return {
                "allowed": True,
                "symbol": str(symbol or "").upper(),
                "sector": str(sector or "UNKNOWN").upper(),
                "sector_position_count": 0,
                "max_sector_positions": self.config.max_sector_positions,
                "highest_correlation": 0.0,
                "highest_correlated_symbol": None,
                "correlation_limit": self.config.correlation_limit,
                "reasons": ["Sector & correlation guard kapalı."],
            }

        if open_positions is None:
            open_positions = []

        result = self.sector_correlation_engine.check_candidate(
            symbol=symbol,
            sector=sector,
            open_positions=open_positions,
            candidate_prices=candidate_prices,
            position_price_map=position_price_map,
        )
        return result.to_dict()

    def sector_correlation_lock_reason(
        self,
        *,
        symbol: str,
        sector: str | None = None,
        open_positions=None,
        candidate_prices=None,
        position_price_map=None,
    ) -> tuple[str, dict[str, Any]]:
        result = self.get_sector_correlation_result(
            symbol=symbol,
            sector=sector,
            open_positions=open_positions,
            candidate_prices=candidate_prices,
            position_price_map=position_price_map,
        )

        if result.get("allowed", True):
            return "", result

        reasons = result.get("reasons") or ["Sektör/korelasyon limiti aşıldı."]
        return " | ".join(str(reason) for reason in reasons), result

    def evaluate_ai_decision(
        self,
        *,
        technical_score: float = 50.0,
        trend_quality: float = 50.0,
        volume_quality: float = 50.0,
        risk_quality: float = 50.0,
        market_regime_score: float = 50.0,
        correlation_quality: float = 50.0,
        backtest_quality: float = 50.0,
        fundamental_quality: float = 50.0,
        hard_block_reasons=None,
    ) -> dict[str, Any]:
        if not getattr(self.config, "ai_decision_enabled", True):
            return {
                "score": 100.0,
                "decision": "DISABLED",
                "confidence": 100.0,
                "allow_trade": True,
                "reasons": ["AI Decision Guard kapalı."],
                "components": {},
            }

        result = self.ai_decision_engine.evaluate(
            technical_score=technical_score,
            trend_quality=trend_quality,
            volume_quality=volume_quality,
            risk_quality=risk_quality,
            market_regime_score=market_regime_score,
            correlation_quality=correlation_quality,
            backtest_quality=backtest_quality,
            fundamental_quality=fundamental_quality,
            hard_block_reasons=hard_block_reasons,
        )
        return result.to_dict()

    def set_emergency_risk_lock(self, locked: bool, reason: str = "") -> None:
        self.robot_risk_enforcer.set_manual_lock(locked, reason)

    def get_emergency_risk_lock(self) -> dict[str, Any]:
        return self.robot_risk_enforcer.lock_status()

    def open_position(
        self,
        *,
        symbol: str,
        price: float,
        stop_price: float,
        target1: float,
        target2: float,
        score: float = 0.0,
        confidence: float = 0.0,
        confidence_label: str = "",
        decision: str = "",
        reason: str = "",
        market: str = "",
        universe: str = "",
        strategy_profile: str | None = None,
        market_frame=None,
        multi_timeframe_frames=None,
        sector=None,
        open_positions=None,
        candidate_prices=None,
        position_price_map=None,
        technical_score=50.0,
        trend_quality=50.0,
        volume_quality=50.0,
        risk_quality=50.0,
        market_regime_score=50.0,
        correlation_quality=50.0,
        backtest_quality=50.0,
        fundamental_quality=50.0,
        ai_hard_block_reasons=None,
    ) -> dict[str, Any]:
        ai_decision_result = self.evaluate_ai_decision(
            technical_score=technical_score,
            trend_quality=trend_quality,
            volume_quality=volume_quality,
            risk_quality=risk_quality,
            market_regime_score=market_regime_score,
            correlation_quality=correlation_quality,
            backtest_quality=backtest_quality,
            fundamental_quality=fundamental_quality,
            hard_block_reasons=ai_hard_block_reasons,
        )
        if not ai_decision_result.get("allow_trade", False):
            ai_reasons = ai_decision_result.get("reasons") or []
            ai_message = " | ".join(str(reason) for reason in ai_reasons)
            return {
                "ok": False,
                "message": (
                    f"AI Decision reddetti: {ai_decision_result.get('decision')} "
                    f"({ai_decision_result.get('score')}/100)"
                    + (f" | {ai_message}" if ai_message else "")
                ),
                "ai_decision": ai_decision_result,
            }

        sector_correlation_lock, sector_correlation_result = (
            self.sector_correlation_lock_reason(
                symbol=symbol,
                sector=sector,
                open_positions=open_positions,
                candidate_prices=candidate_prices,
                position_price_map=position_price_map,
            )
        )
        if sector_correlation_lock:
            return {
                "ok": False,
                "message": sector_correlation_lock,
                "sector_correlation": sector_correlation_result,
            }

        multi_timeframe_result = self.get_multi_timeframe_result(multi_timeframe_frames)
        if not multi_timeframe_result.get("allow_new_positions", True):
            return {
                "ok": False,
                "message": (
                    "Multi-Timeframe Intelligence yeni işlemi kilitledi: "
                    f"{multi_timeframe_result.get('dominant_regime')} / "
                    f"{multi_timeframe_result.get('conflict_level')}"
                ),
                "multi_timeframe": multi_timeframe_result,
            }

        market_regime_lock = self.market_regime_lock_reason(market_frame)
        if market_regime_lock:
            return {"ok": False, "message": market_regime_lock,
                    "market_regime": self.get_market_regime_result(market_frame)}

        adaptive_policy = self.get_adaptive_strategy_policy(market_frame)
        if not adaptive_policy.get("allow_new_positions", True):
            return {
                "ok": False,
                "message": f"Adaptive Strategy yeni işlemi kilitledi: {adaptive_policy.get('profile')}",
                "adaptive_strategy": adaptive_policy,
            }
        adaptive_minimum_score = float(adaptive_policy.get("minimum_entry_score", self.config.minimum_score))
        adaptive_minimum_score += float(multi_timeframe_result.get("minimum_entry_score_delta", 0.0) or 0.0)
        if float(score) < adaptive_minimum_score:
            return {
                "ok": False,
                "message": f"Adaptive giriş eşiği karşılanmadı: {float(score):.2f} < {adaptive_minimum_score:.2f}",
                "adaptive_strategy": adaptive_policy,
            }
        target1, target2 = self.adaptive_strategy_engine.adjust_targets(
            price, target1, target2,
            self.adaptive_strategy_engine.build_policy(self.get_market_regime_result(market_frame)),
        )

        state = self.get_state()
        market = self.market

        if not state["enabled"]:
            return {"ok": False, "message": "Robot kapalı."}


        risk_reason = self.risk_lock_reason()
        if risk_reason:
            return {
                "ok": False,
                "message": f"Risk Manager yeni işlem açılmasını durdurdu: {risk_reason}",
                "risk_locked": True,
                "risk_reason": risk_reason,
            }

        if price <= 0:
            return {"ok": False, "message": "Geçersiz fiyat."}

        if self.has_open_position(symbol):
            return {
                "ok": False,
                "message": f"{symbol} için açık pozisyon zaten var.",
            }

        regime_max_positions, regime_result = self.get_regime_adjusted_max_positions(market_frame)
        if self._open_position_count() >= regime_max_positions:
            return {
                "ok": False,
                "message": "Maksimum açık pozisyon sayısına ulaşıldı.",
            }

        quantity_info = self.calculate_position_quantity(
            balance=state["balance"],
            price=price,
            stop_price=stop_price,
        )
        if not quantity_info.get("ok"):
            return {
                "ok": False,
                "message": str(
                    quantity_info.get(
                        "message",
                        "Pozisyon miktarı hesaplanamadı.",
                    )
                ),
            }

        quantity = float(quantity_info["quantity"])
        quantity, regime_result = self.apply_market_regime_to_quantity(
            quantity,
            market_frame,
        )
        quantity *= float(adaptive_policy.get("position_size_multiplier", 1.0) or 0.0)
        quantity *= float(multi_timeframe_result.get("position_size_multiplier", 1.0) or 0.0)
        if quantity <= 0:
            return {
                "ok": False,
                "message": "Adaptive Strategy pozisyon miktarını sıfıra indirdi.",
                "adaptive_strategy": adaptive_policy,
            }

        risk_enforcement = None
        if self.config.robot_risk_enforcement_enabled:
            open_frame = self.get_open_positions()
            open_items = open_frame.to_dict("records") if not open_frame.empty else []
            risk_enforcement = self.robot_risk_enforcer.evaluate(
                symbol=symbol, price=price, stop_price=stop_price,
                requested_quantity=quantity,
                equity=float(state.get("starting_balance") or self.config.starting_balance)
                       + float(state.get("total_profit") or 0.0),
                day_start_equity=float(state.get("starting_balance") or self.config.starting_balance),
                realized_pnl_today=self.get_today_realized_profit(),
                positions=open_items, group=universe or market,
                metadata={"score": score, "decision": decision, "strategy_profile": strategy_profile or self.config.strategy_profile},
            )
            if not risk_enforcement.approved:
                return {
                    "ok": False,
                    "message": f"Robot Risk Enforcement reddetti: {risk_enforcement.message}",
                    "risk_enforcement": risk_enforcement.to_dict(),
                }
            quantity = float(risk_enforcement.approved_quantity)

        budget = float(quantity_info["budget"])
        sizing_mode = str(quantity_info["sizing_mode"])
        estimated_risk = float(quantity_info["risk_amount"])
        portfolio_risk_reason = self.portfolio_risk_lock_reason(
            state=state,
            price=price,
            stop_price=stop_price,
            quantity=quantity,
        )
        if portfolio_risk_reason:
            return {
                "ok": False,
                "message": portfolio_risk_reason,
                "portfolio_risk_locked": True,
            }


        gross_cost = quantity * price
        commission = gross_cost * self.config.commission_rate
        total_cost = gross_cost + commission

        if total_cost > state["balance"]:
            return {
                "ok": False,
                "message": "Yetersiz sanal bakiye.",
            }

        opened_at = self._now()
        new_balance = state["balance"] - total_cost
        profile = strategy_profile or self.config.strategy_profile

        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO positions (
                    symbol,
                    quantity,
                    entry_price,
                    stop_price,
                    target1,
                    target2,
                    opened_at,
                    status,
                    market,
                    universe,
                    technical_score,
                    confidence_score,
                    confidence_label,
                    decision,
                    entry_reason,
                    strategy_profile,
                    account_id,
                    currency,
                    highest_price,
                    lowest_price
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'OPEN',
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol,
                    quantity,
                    price,
                    stop_price,
                    target1,
                    target2,
                    opened_at,
                    market,
                    universe,
                    score,
                    confidence,
                    confidence_label,
                    decision,
                    reason,
                    profile,
                    self.account_id,
                    self.currency,
                    price,
                    price,
                ),
            )

            position_id = int(cursor.lastrowid)

            connection.execute(
                """
                INSERT INTO trade_history (
                    symbol,
                    side,
                    quantity,
                    price,
                    commission,
                    profit,
                    created_at,
                    market,
                    universe,
                    technical_score,
                    confidence_score,
                    confidence_label,
                    decision,
                    reason,
                    strategy_profile,
                    position_id,
                    account_id,
                    currency
                )
                VALUES (?, 'BUY', ?, ?, ?, 0,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol,
                    quantity,
                    price,
                    commission,
                    opened_at,
                    market,
                    universe,
                    score,
                    confidence,
                    confidence_label,
                    decision,
                    reason,
                    profile,
                    position_id,
                    self.account_id,
                    self.currency,
                ),
            )

            connection.execute(
                """
                UPDATE robot_accounts
                SET balance = ?, updated_at = ?
                WHERE account_id = ?
                """,
                (new_balance, opened_at, self.account_id),
            )

            connection.execute(
                """
                INSERT INTO system_events (
                    created_at,
                    event_type,
                    message
                )
                VALUES (?, 'ROBOT_BUY', ?)
                """,
                (
                    opened_at,
                    (
                        f"{market}/{universe} | {symbol} sanal alım | "
                        f"fiyat={price:.4f} | miktar={quantity:.4f} | "
                        f"skor={score:.1f} | güven={confidence:.1f} | "
                        f"profil={profile} | {reason}"
                    ),
                ),
            )

            connection.commit()

        self.position_lifecycle.record(
            position_id=str(position_id),
            symbol=symbol,
            event_type="POSITION_OPENED",
            market=market,
            universe=universe,
            account_id=self.account_id,
            entry_price=price,
            price=price,
            stop_price=stop_price,
            target_price=target1,
            quantity=quantity,
            technical_score=score,
            confidence_score=confidence,
            message="Sanal pozisyon açıldı.",
            metadata={
                "decision": decision,
                "strategy_profile": profile,
                "target2": target2,
                "commission": commission,
            },
        )
        portfolio_summary = self.get_portfolio_risk_summary()

        return {
            "ok": True,
            "message": f"{symbol} sanal pozisyon açıldı.",
            "position_id": position_id,
            "symbol": symbol,
            "quantity": quantity,
            "price": price,
            "commission": commission,
            "balance": new_balance,
            "market": market,
            "universe": universe,
            "score": score,
            "confidence": confidence,
            "sizing_mode": sizing_mode,
            "estimated_risk": estimated_risk,
            "risk_per_trade_pct": float(self.config.risk_per_trade_pct),
            "portfolio_risk": portfolio_summary["risk_pct"],
            "portfolio_exposure": portfolio_summary["exposure_pct"],
            "cash_reserve": portfolio_summary["cash_reserve_pct"],
            "risk_enforcement": risk_enforcement.to_dict() if risk_enforcement else None,
        }

    def close_position(
        self,
        position_id: int,
        exit_price: float,
        exit_reason: str,
    ) -> dict[str, Any]:
        if exit_price <= 0:
            return {
                "ok": False,
                "message": "Geçersiz çıkış fiyatı.",
            }

        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    symbol,
                    quantity,
                    entry_price,
                    market,
                    universe,
                    technical_score,
                    confidence_score,
                    confidence_label,
                    decision,
                    entry_reason,
                    strategy_profile,
                    opened_at,
                    highest_price,
                    lowest_price,
                    stop_price,
                    target2
                FROM positions
                WHERE id = ?
                  AND status = 'OPEN'
                  AND account_id = ?
                """,
                (position_id, self.account_id),
            ).fetchone()

            if row is None:
                return {
                    "ok": False,
                    "message": "Açık pozisyon bulunamadı.",
                }

            (
                symbol,
                quantity,
                entry_price,
                market,
                universe,
                technical_score,
                confidence_score,
                confidence_label,
                decision,
                entry_reason,
                strategy_profile,
                opened_at,
                highest_price,
                lowest_price,
                stop_price,
                target2,
            ) = row

            quantity = float(quantity)
            entry_price = float(entry_price)

            state_row = connection.execute(
                """
                SELECT balance, daily_profit, total_profit
                FROM robot_accounts
                WHERE account_id = ?
                """,
                (self.account_id,),
            ).fetchone()

            if state_row is None:
                return {
                    "ok": False,
                    "message": "Robot hesabı bulunamadı.",
                }

            balance = float(state_row[0])
            daily_profit = float(state_row[1])
            total_profit = float(state_row[2])

            gross_revenue = quantity * exit_price
            sell_commission = (
                gross_revenue * self.config.commission_rate
            )
            net_revenue = gross_revenue - sell_commission

            entry_gross = quantity * entry_price
            buy_commission = (
                entry_gross * self.config.commission_rate
            )

            profit = (
                net_revenue
                - entry_gross
                - buy_commission
            )
            closed_at = self._now()
            new_balance = balance + net_revenue

            analytics = analyze_closed_trade(
                entry_price=entry_price,
                exit_price=exit_price,
                quantity=quantity,
                total_profit=profit,
                opened_at=opened_at,
                closed_at=closed_at,
                highest_price=highest_price,
                lowest_price=lowest_price,
                stop_price=stop_price,
                target_price=target2,
                technical_score=float(technical_score or 0),
                confidence_score=float(confidence_score or 0),
            )

            connection.execute(
                """
                UPDATE positions
                SET status = 'CLOSED'
                WHERE id = ?
                """,
                (position_id,),
            )

            connection.execute(
                """
                INSERT INTO trade_history (
                    symbol,
                    side,
                    quantity,
                    price,
                    commission,
                    profit,
                    created_at,
                    market,
                    universe,
                    technical_score,
                    confidence_score,
                    confidence_label,
                    decision,
                    reason,
                    strategy_profile,
                    position_id,
                    account_id,
                    currency,
                    entry_price,
                    exit_price,
                    profit_pct,
                    holding_minutes,
                    mfe_pct,
                    mae_pct,
                    risk_pct,
                    reward_pct,
                    risk_reward,
                    entry_efficiency,
                    exit_efficiency,
                    trade_quality_score,
                    trade_grade
                )
                VALUES (?, 'SELL', ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol,
                    quantity,
                    exit_price,
                    sell_commission,
                    profit,
                    closed_at,
                    market,
                    universe,
                    technical_score,
                    confidence_score,
                    confidence_label,
                    decision,
                    exit_reason,
                    strategy_profile,
                    position_id,
                    self.account_id,
                    self.currency,
                    entry_price,
                    exit_price,
                    analytics.profit_pct,
                    analytics.holding_minutes,
                    analytics.mfe_pct,
                    analytics.mae_pct,
                    analytics.risk_pct,
                    analytics.reward_pct,
                    analytics.risk_reward,
                    analytics.entry_efficiency,
                    analytics.exit_efficiency,
                    analytics.trade_quality_score,
                    analytics.trade_grade,
                ),
            )

            connection.execute(
                """
                UPDATE robot_accounts
                SET balance = ?,
                    daily_profit = ?,
                    total_profit = ?,
                    updated_at = ?
                WHERE account_id = ?
                """,
                (
                    new_balance,
                    daily_profit + profit,
                    total_profit + profit,
                    closed_at,
                    self.account_id,
                ),
            )

            connection.execute(
                """
                INSERT INTO system_events (
                    created_at,
                    event_type,
                    message
                )
                VALUES (?, 'ROBOT_SELL', ?)
                """,
                (
                    closed_at,
                    (
                        f"{market}/{universe} | {symbol} sanal satış | "
                        f"fiyat={exit_price:.4f} | "
                        f"kâr/zarar={profit:.2f} | "
                        f"neden={exit_reason} | "
                        f"profil={strategy_profile}"
                    ),
                ),
            )

            connection.commit()

        self.position_lifecycle.record(
            position_id=str(position_id),
            symbol=symbol,
            event_type="POSITION_CLOSED",
            market=market,
            universe=universe,
            account_id=self.account_id,
            entry_price=entry_price,
            price=exit_price,
            quantity=quantity,
            profit=profit,
            profit_pct=analytics.profit_pct,
            technical_score=float(technical_score or 0),
            confidence_score=float(confidence_score or 0),
            reason=exit_reason,
            message="Sanal pozisyon kapatıldı.",
            metadata={
                "trade_grade": analytics.trade_grade,
                "trade_quality_score": analytics.trade_quality_score,
                "holding_minutes": analytics.holding_minutes,
                "risk_reward": analytics.risk_reward,
            },
        )

        return {
            "ok": True,
            "message": f"{symbol} pozisyonu kapatıldı.",
            "symbol": symbol,
            "profit": profit,
            "balance": new_balance,
            "market": market,
            "universe": universe,
        }

    def process_open_positions(
        self,
        latest_prices: dict[str, float],
        latest_signals: dict[str, dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        latest_signals = latest_signals or {}
        positions = self.get_open_positions()

        if positions.empty:
            return actions

        for _, position in positions.iterrows():
            # Sprint 6.3F-D: Aynı pozisyon aynı turda yalnızca bir satış yapabilir.
            sale_executed = False

            symbol = str(position["symbol"])
            current_price = latest_prices.get(symbol)

            if current_price is None:
                continue

            current_price = float(current_price)
            position_id = int(position["id"])
            entry_price = float(position["entry_price"])
            quantity = float(position["quantity"])
            initial_quantity = float(
                position.get("initial_quantity", quantity) or quantity
            )
            stop_price = float(position["stop_price"] or 0)
            target1 = float(position["target1"] or 0)
            target2 = float(position["target2"] or 0)
            stored_highest = float(
                position.get("highest_price", entry_price) or entry_price
            )
            highest_price = max(stored_highest, current_price)
            break_even_active = bool(
                int(position.get("break_even_active", 0) or 0)
            )
            trailing_active = bool(
                int(position.get("trailing_active", 0) or 0)
            )
            target1_completed = bool(
                int(position.get("target1_completed", 0) or 0)
            )
            signal = latest_signals.get(symbol, {})
            atr_value = float(signal.get("atr", 0) or 0)

            with self.database.connect() as connection:
                connection.execute(
                    """
                    UPDATE positions
                    SET highest_price = CASE
                            WHEN highest_price IS NULL OR ? > highest_price
                            THEN ? ELSE highest_price END,
                        lowest_price = CASE
                            WHEN lowest_price IS NULL OR ? < lowest_price
                            THEN ? ELSE lowest_price END,
                        initial_quantity = COALESCE(initial_quantity, quantity)
                    WHERE id = ?
                      AND status = 'OPEN'
                      AND account_id = ?
                    """,
                    (
                        current_price,
                        current_price,
                        current_price,
                        current_price,
                        position_id,
                        self.account_id,
                    ),
                )

                if (
                    not target1_completed
                    and target1 > 0
                    and current_price >= target1
                    and quantity > 0
                ):
                    sell_quantity = min(
                        quantity,
                        initial_quantity * self.config.target1_sell_ratio,
                    )
                    remaining_quantity = max(
                        0.0,
                        quantity - sell_quantity,
                    )
                    gross_value = sell_quantity * current_price
                    commission = gross_value * self.config.commission_rate
                    net_value = gross_value - commission
                    realized_pnl = (
                        (current_price - entry_price) * sell_quantity
                        - commission
                    )

                    connection.execute(
                        """
                        UPDATE positions
                        SET quantity = ?,
                            target1_completed = 1
                        WHERE id = ?
                          AND status = 'OPEN'
                          AND account_id = ?
                        """,
                        (
                            remaining_quantity,
                            position_id,
                            self.account_id,
                        ),
                    )

                    connection.execute(
                        """
                       
                        UPDATE robot_accounts
                        SET balance = balance + ?,
                            updated_at = ?
                        WHERE account_id = ?
                        """,
                        (
                            net_value,
                            self._now(),
                            self.account_id,
                        ),
                    )
                       
                    connection.execute(
                        """
                        INSERT INTO system_events (
                            created_at,
                            event_type,
                            message
                        )
                        VALUES (?, 'ROBOT_TARGET1_PARTIAL', ?)
                        """,
                        (
                            self._now(),
                            (
                                f"{self.market} | {symbol} hedef 1 kısmi satış | "
                                f"satılan={sell_quantity:.8f} | "
                                f"kalan={remaining_quantity:.8f} | "
                                f"fiyat={current_price:.4f} | "
                                f"pnl={realized_pnl:.2f}"
                            ),
                        ),
                    )

                    quantity = remaining_quantity
                    target1_completed = True
                    sale_executed = True
                    actions.append(
                        {
                            "action": "PARTIAL_SELL",
                            "symbol": symbol,
                            "position_id": position_id,
                            "quantity": sell_quantity,
                            "remaining_quantity": remaining_quantity,
                            "price": current_price,
                            "commission": commission,
                            "realized_pnl": realized_pnl,
                            "reason": "HEDEF 1 KISMİ SATIŞ",
                        }
                    )

                trigger_price = entry_price * (
                    1.0 + self.config.break_even_trigger_pct
                )
                break_even_cost_buffer_pct = 0.0
                if self.config.break_even_include_costs:
                    break_even_cost_buffer_pct = (
                        2.0 * self.config.commission_rate
                        + 2.0 * self.config.slippage_rate
                        + self.config.break_even_extra_buffer_pct
                    )
                effective_break_even_buffer_pct = max(
                    self.config.break_even_buffer_pct,
                    break_even_cost_buffer_pct,
                )
                break_even_stop = entry_price * (
                    1.0 + effective_break_even_buffer_pct
                )

                if (
                    quantity > 0
                    and not break_even_active
                    and current_price >= trigger_price
                    and break_even_stop > stop_price
                ):
                    connection.execute(
                        """
                                            
                        UPDATE positions
                        SET stop_price = ?,
                            break_even_active = 1
                        WHERE id = ?
                          AND status = 'OPEN'
                          AND account_id = ?
                        """,
                        (
                            break_even_stop,
                            position_id,
                            self.account_id,
                        ),
                    )
                    previous_stop = stop_price
                    self.position_lifecycle.record(
                        position_id=str(position_id),
                        symbol=symbol,
                        event_type="BREAK_EVEN_ACTIVATED",
                        market=self.market,
                        universe=getattr(self.config, "universe", None),
                        account_id=self.account_id,
                        price=current_price,
                        entry_price=entry_price,
                        stop_price=break_even_stop,
                        previous_stop_price=previous_stop,
                        quantity=quantity,
                        technical_score=float(position.get("technical_score", 0) or 0),
                        confidence_score=float(position.get("confidence_score", 0) or 0),
                        reason="BREAK EVEN",
                        message="Break-even stop aktif edildi.",
                        metadata={
                            "trigger_price": trigger_price,
                            "buffer_pct": effective_break_even_buffer_pct,
                        },
                    )
                    connection.execute(
                        """
                        INSERT INTO system_events (
                            created_at,
                            event_type,
                            message
                        )
                        VALUES (?, 'ROBOT_BREAK_EVEN', ?)
                        """,
                        (
                            self._now(),
                            (
                                f"{self.market} | {symbol} break-even aktif | "
                                f"neden=kâr eşiği aşıldı ve işlem maliyetleri güvenceye alındı | "
                                f"fiyat={current_price:.4f} | "
                                f"giriş={entry_price:.4f} | "
                                f"komisyon=%{self.config.commission_rate * 100:.3f} | "
                                f"slipaj=%{self.config.slippage_rate * 100:.3f} | "
                                f"tampon=%{effective_break_even_buffer_pct * 100:.3f} | "
                                f"eski_stop={stop_price:.4f} | "
                                f"yeni_stop={break_even_stop:.4f}"
                            ),
                        ),
                    )
                    stop_price = break_even_stop
                    break_even_active = True

                trailing_mode = "PERCENT"
                trailing_distance = (
                    highest_price * self.config.trailing_stop_pct
                )

                if self.config.atr_trailing_enabled and atr_value > 0:
                    min_distance = (
                        highest_price
                        * self.config.atr_trailing_min_pct
                    )
                    max_distance = (
                        highest_price
                        * self.config.atr_trailing_max_pct
                    )
                    atr_distance = (
                        atr_value
                        * self.config.atr_trailing_multiplier
                    )
                    trailing_distance = min(
                        max(atr_distance, min_distance),
                        max_distance,
                    )
                    trailing_mode = "ATR"

                trailing_stop = highest_price - trailing_distance

                if (
                    quantity > 0
                    and break_even_active
                    and trailing_stop > stop_price
                ):
                    connection.execute(
                        """
                        UPDATE positions
                        SET stop_price = ?,
                            trailing_active = 1
                        WHERE id = ?
                          AND status = 'OPEN'
                          AND account_id = ?
                        """,
                        (
                            trailing_stop,
                            position_id,
                            self.account_id,
                        ),
                    )
                    previous_stop = stop_price

                    self.position_lifecycle.record(
                        position_id=str(position_id),
                        symbol=symbol,
                        event_type="ATR_TRAILING_UPDATED",
                        market=self.market,
                        universe=getattr(self.config, "universe", None),
                        account_id=self.account_id,
                        price=current_price,
                        entry_price=entry_price,
                        stop_price=trailing_stop,
                        previous_stop_price=previous_stop,
                        quantity=quantity,
                        technical_score=float(position.get("technical_score", 0) or 0),
                        confidence_score=float(position.get("confidence_score", 0) or 0),
                        reason="TRAILING STOP UPDATED",
                        message="Trailing stop kâr yönünde güncellendi.",
                        metadata={
                            "trailing_mode": trailing_mode,
                            "highest_price": highest_price,
                            "atr_value": atr_value,
                            "trailing_distance": trailing_distance,
                            "atr_multiplier": self.config.atr_trailing_multiplier,
                        },
                    )
                    connection.execute(
                        """
                        INSERT INTO system_events (
                            created_at,
                            event_type,
                            message
                        )
                        VALUES (?, 'ROBOT_TRAILING', ?)
                        """,
                        (
                            self._now(),
                            (
                                f"{self.market} | {symbol} trailing stop güncellendi | "
                                f"mod={trailing_mode} | "
                                f"zirve={highest_price:.4f} | "
                                f"atr={atr_value:.4f} | "
                                f"çarpan={self.config.atr_trailing_multiplier:.2f} | "
                                f"min=%{self.config.atr_trailing_min_pct * 100:.2f} | "
                                f"max=%{self.config.atr_trailing_max_pct * 100:.2f} | "
                                f"mesafe={trailing_distance:.4f} | "
                                f"eski_stop={stop_price:.4f} | "
                                f"yeni_stop={trailing_stop:.4f} | "
                                f"neden=stop yalnızca kâr yönünde sıkılaştırıldı"
                            ),
                        ),
                    )
                    stop_price = trailing_stop
                    trailing_active = True

                connection.commit()

            # Sprint 6.3F-D: Hedef 1 bu turda satış yaptıysa
            # aynı fiyat güncellemesinde ikinci çıkış emri üretme.
            if sale_executed:
                continue

            if quantity <= 0:
                continue

            # Çıkış önceliği:
            # 1) Stop / Break-even / Trailing
            # 2) Hedef 2
            # 3) Smart Exit
            # 4) Time Exit
            if stop_price > 0 and current_price <= stop_price:
                if trailing_active:
                    exit_reason = "TRAILING STOP"
                elif break_even_active and stop_price >= entry_price:
                    exit_reason = "BREAK EVEN"
                else:
                    exit_reason = "STOP"

                actions.append(
                    self.close_position(
                        position_id,
                        current_price,
                        exit_reason,
                    )
                )

            elif target2 > 0 and current_price >= target2:
                actions.append(
                    self.close_position(
                        position_id,
                        current_price,
                        "HEDEF 2",
                    )
                )

            else:
                smart_exit = evaluate_smart_exit(
                    entry_price=entry_price,
                    current_price=current_price,
                    current_rsi=signal.get("rsi"),
                    previous_rsi=signal.get("previous_rsi"),
                    macd_hist=signal.get("macd_hist"),
                    close_price=signal.get("close", current_price),
                    ema20=signal.get("ema20"),
                    volume_ratio=signal.get("volume_ratio"),
                    current_adx=signal.get("adx"),
                    previous_adx=signal.get("previous_adx"),
                    break_even_active=break_even_active,
                    trailing_active=trailing_active,
                    partial_stage=1 if target1_completed else 0,
                    config=SmartExitConfig(
                        watch_score_threshold=self.config.smart_exit_watch_score,
                        partial_exit_score_threshold=self.config.smart_exit_partial_score,
                        full_exit_score_threshold=self.config.smart_exit_full_score,
                        min_confirmations=self.config.smart_exit_min_confirmations,
                        full_exit_min_confirmations=(
                            self.config.smart_exit_full_min_confirmations
                        ),
                    ),
                )

                if smart_exit.should_exit:
                    reason_text = " | ".join(smart_exit.reasons)
                    strong_exit = (
                        smart_exit.action == SmartExitAction.FULL_EXIT
                    )
                    can_partial = (
                        self.config.smart_exit_partial_enabled
                        and not strong_exit
                        and smart_exit.score
                        >= self.config.smart_exit_partial_score
                        and not target1_completed
                        and quantity > 0
                    )

                    if can_partial:
                        sell_quantity = min(
                            quantity,
                            initial_quantity
                            * self.config.smart_exit_partial_sell_ratio,
                        )
                        remaining_quantity = max(
                            0.0,
                            quantity - sell_quantity,
                        )
                        gross_value = sell_quantity * current_price
                        commission = (
                            gross_value
                            * self.config.commission_rate
                        )
                        net_value = gross_value - commission
                        realized_pnl = (
                            (current_price - entry_price)
                            * sell_quantity
                            - commission
                        )

                        with self.database.connect() as connection:
                            connection.execute(
                                """
                                UPDATE positions
                                SET quantity = ?,
                                    target1_completed = 1
                                WHERE id = ?
                                  AND status = 'OPEN'
                                  AND account_id = ?
                                """,
                                (
                                    remaining_quantity,
                                    position_id,
                                    self.account_id,
                                ),
                            )
                            connection.execute(
                                """
                                UPDATE robot_accounts
                                SET balance = balance + ?,
                                    updated_at = ?
                                WHERE account_id = ?
                                """,
                                (
                                    net_value,
                                    self._now(),
                                    self.account_id,
                                ),
                            )
                            connection.execute(
                                """
                                INSERT INTO system_events (
                                    created_at,
                                    event_type,
                                    message
                                )
                                VALUES (
                                    ?,
                                    'ROBOT_SMART_EXIT_PARTIAL',
                                    ?
                                )
                                """,
                                (
                                    self._now(),
                                    (
                                        f"{self.market} | {symbol} "
                                        f"kademeli akıllı çıkış | "
                                        f"pozisyon_id={position_id} | "
                                        f"puan={smart_exit.score} | "
                                        f"onay={smart_exit.confirmations} | "
                                        f"kar=%{smart_exit.profit_pct:.2f} | "
                                        f"satılan={sell_quantity:.8f} | "
                                        f"kalan={remaining_quantity:.8f} | "
                                        f"pnl={realized_pnl:.2f} | "
                                        f"neden={reason_text}"
                                    ),
                                ),
                            )
                            connection.commit()

                        self._record_event(
                            "SMART_EXIT_PARTIAL",
                            symbol,
                            position_id,
                            price=current_price,
                            entry_price=entry_price,
                            quantity=sell_quantity,
                            profit=realized_pnl,
                            profit_pct=smart_exit.profit_pct,
                            technical_score=float(
                                position.get("technical_score", 0) or 0
                            ),
                            confidence_score=float(
                                position.get("confidence_score", 0) or 0
                            ),
                            reason=reason_text,
                            message="Akıllı çıkış sistemi kısmi satış yaptı.",
                            metadata={
                                "sold_quantity": sell_quantity,
                                "remaining_quantity": remaining_quantity,
                                "commission": commission,
                                "smart_exit_score": smart_exit.score,
                                "confirmations": smart_exit.confirmations,
                            },
                        )
                        actions.append(
                            {
                                "action": "SMART_EXIT_PARTIAL",
                                "symbol": symbol,
                                "position_id": position_id,
                                "quantity": sell_quantity,
                                "remaining_quantity": remaining_quantity,
                                "price": current_price,
                                "commission": commission,
                                "realized_pnl": realized_pnl,
                                "smart_exit_score": smart_exit.score,
                                "reason": "AKILLI ÇIKIŞ KISMİ SATIŞ",
                            }
                        )

                        quantity = remaining_quantity
                        target1_completed = True

                        if quantity <= 0:
                            continue

                    else:
                        with self.database.connect() as connection:
                            connection.execute(
                                """
                                INSERT INTO system_events (
                                    created_at,
                                    event_type,
                                    message
                                )
                                VALUES (?, 'ROBOT_SMART_EXIT', ?)
                                """,
                                (
                                    self._now(),
                                    (
                                        f"{self.market} | {symbol} "
                                        f"akıllı çıkış tam kapanış | "
                                        f"pozisyon_id={position_id} | "
                                        f"puan={smart_exit.score} | "
                                        f"onay={smart_exit.confirmations} | "
                                        f"kar=%{smart_exit.profit_pct:.2f} | "
                                        f"neden={reason_text}"
                                    ),
                                ),
                            )
                            connection.commit()

                        self._record_event(
                            "SMART_EXIT_FULL",
                            symbol,
                            position_id,
                            price=current_price,
                            entry_price=entry_price,
                            quantity=quantity,
                            profit_pct=smart_exit.profit_pct,
                            technical_score=float(
                                position.get("technical_score", 0) or 0
                            ),
                            confidence_score=float(
                                position.get("confidence_score", 0) or 0
                            ),
                            reason=reason_text,
                            message="Akıllı çıkış sistemi pozisyonu tamamen kapattı.",
                            metadata={
                                "smart_exit_score": smart_exit.score,
                                "confirmations": smart_exit.confirmations,
                            },
                        )

                        actions.append(
                            self.close_position(
                                position_id,
                                current_price,
                                "AKILLI ÇIKIŞ TAM",
                            )
                        )

                elif self.config.time_exit_enabled:
                    opened_at_raw = position.get("opened_at")
                    holding_hours = 0.0

                    try:
                        opened_at_dt = datetime.fromisoformat(
                            str(opened_at_raw)
                        )
                        holding_hours = max(
                            0.0,
                            (
                                datetime.now() - opened_at_dt
                            ).total_seconds() / 3600.0,
                        )
                    except (TypeError, ValueError):
                        holding_hours = 0.0

                    profit_pct = (
                        ((current_price / entry_price) - 1.0) * 100.0
                    )

                    if (
                        holding_hours >= self.config.max_holding_hours
                        and profit_pct
                        >= self.config.time_exit_min_profit_pct
                    ):
                        with self.database.connect() as connection:
                            connection.execute(
                                """
                                INSERT INTO system_events (
                                    created_at, event_type, message
                                )
                                VALUES (?, 'ROBOT_TIME_EXIT', ?)
                                """,
                                (
                                    self._now(),
                                    (
                                        f"{self.market} | {symbol} "
                                        f"zaman bazlı çıkış | "
                                        f"süre={holding_hours:.1f} saat | "
                                        f"kar=%{profit_pct:.2f} | "
                                        f"eşik={self.config.max_holding_hours:.1f} saat"
                                    ),
                                ),
                            )
                            connection.commit()

                        actions.append(
                            self.close_position(
                                position_id,
                                current_price,
                                "ZAMAN BAZLI ÇIKIŞ",
                            )
                        )

        return actions

    def process_scanner_results(
        self,
        results: list[dict[str, Any]],
        *,
        market: str = "",
        universe: str = "",
        strategy_profile: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self.get_state()["enabled"]:
            return [
                {
                    "ok": False,
                    "message": "Robot kapalı.",
                }
            ]

        actions: list[dict[str, Any]] = []

        candidates = sorted(
            results,
            key=lambda row: (
                float(
                    row.get(
                        "Başarı Göstergesi %",
                        0,
                    )
                    or 0
                ),
                float(
                    row.get(
                        "Güven",
                        0,
                    )
                    or 0
                ),
                float(
                    row.get(
                        "Puan",
                        0,
                    )
                    or 0
                ),
            ),
            reverse=True,
        )

        for row in candidates:
            decision = str(
                row.get(
                    "Karar",
                    "",
                )
            ).strip()

            score = float(
                row.get(
                    "Puan",
                    0,
                )
                or 0
            )

            if decision not in self.config.allowed_decisions:
                continue

            if score < self.config.minimum_score:
                continue

            confidence = float(
                row.get(
                    "Güven",
                    0,
                )
                or 0
            )

            if confidence < self.config.minimum_confidence:
                continue

            probability = float(
                row.get(
                    "Başarı Göstergesi %",
                    0,
                )
                or 0
            )

            if probability < self.config.minimum_probability:
                continue

            risk_level = str(
                row.get(
                    "Risk",
                    "",
                )
            ).strip()

            high_risk_override = (
                self.config.high_risk_override_enabled
                and risk_level == "Yüksek"
                and score >= self.config.high_risk_override_min_score
                and confidence >= self.config.high_risk_override_min_confidence
                and probability >= self.config.high_risk_override_min_probability
            )

            risk_allowed = (
                not self.config.allowed_risks
                or risk_level in self.config.allowed_risks
                or high_risk_override
            )

            if not risk_allowed:
                continue

            symbol = str(
                row.get(
                    "Kod",
                    "",
                )
            ).strip()

            price = float(
                row.get(
                    "Fiyat",
                    0,
                )
                or 0
            )

            if not symbol or price <= 0:
                continue

            row_market = str(
                row.get(
                    "Piyasa",
                    market,
                )
            )

            row_universe = str(
                row.get(
                    "Evren",
                    universe,
                )
            )

            actions.append(
                self.open_position(
                    symbol=symbol,
                    price=price,
                    stop_price=float(
                        row.get(
                            "Stop",
                            0,
                        )
                        or 0
                    ),
                    target1=float(
                        row.get(
                            "Hedef 1",
                            0,
                        )
                        or 0
                    ),
                    target2=float(
                        row.get(
                            "Hedef 2",
                            0,
                        )
                        or 0
                    ),
                    score=score,
                    confidence=float(
                        row.get(
                            "Güven",
                            0,
                        )
                        or 0
                    ),
                    confidence_label=str(
                        row.get(
                            "Güven Durumu",
                            "",
                        )
                    ),
                    decision=decision,
                    reason=str(
                        row.get(
                            "AI Analizi",
                            row.get(
                                "Neden",
                                "",
                            ),
                        )
                    ),
                    market=row_market,
                    universe=row_universe,
                    strategy_profile=strategy_profile,
                    sector=row.get("Sektör") or row.get("Sector"),
                )
            )

            if (
                self._open_position_count()
                >= self.config.max_positions
            ):
                break

        return actions
