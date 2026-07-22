from __future__ import annotations
import json

from datetime import datetime
from typing import Any

from config.market_universes import get_crypto_pairs
from engine.analysis_engine import analyze_signal_payload
from engine.filter_analytics import FilterAnalytics
from engine.robot_engine import RobotConfig, RobotEngine
from engine.market_accounts import account_for_context, normalize_market
from database.robot_settings_repository import load_robot_settings
from engine.notification_manager import NotificationManager
from engine.scanner import scan_commodities, scan_crypto, scan_yahoo_items


class BackgroundOrchestrator:
    def __init__(self, database, data_engine, watchlists: dict, settings, logger):
        self.database = database
        self.data_engine = data_engine
        self.watchlists = watchlists
        self.settings = settings
        self.logger = logger
        self.notifier = NotificationManager(database, settings, logger)
        self.robot = self._robot_for_market("BIST", "Genel")
        self.filter_analytics = FilterAnalytics(database, logger)

    def _robot_for_market(self, market: str, universe: str = "") -> RobotEngine:
        normalized = normalize_market(market)
        account = account_for_context(normalized, universe)
        saved = load_robot_settings(
            self.database,
            account_id=account["account_id"],
            market=normalized,
        )
        return RobotEngine(
            self.database,
            RobotConfig(
                starting_balance=float(account["starting_balance"]),
                max_positions=int(saved["max_positions"]),
                position_size_pct=float(saved["position_size_pct"]),
                minimum_score=float(saved["minimum_score"]),
                minimum_confidence=float(saved["minimum_confidence"]),
                minimum_probability=float(saved["minimum_probability"]),
                allowed_decisions=tuple(saved["allowed_decisions"]),
                allowed_risks=tuple(saved["allowed_risks"]),
                strategy_profile=str(saved["strategy_profile"]),
                market=normalized,
                account_id=account["account_id"],
                currency=account["currency"],
            ),
        )

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    def _start_run(self, market: str, universe: str) -> int:
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO background_runs(market, universe, started_at, status)
                VALUES (?, ?, ?, 'RUNNING')
                """,
                (market, universe, self._now()),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def _finish_run(self, run_id: int, *, status: str, scanned: int = 0,
                    failures: int = 0, actions: int = 0, error: str = "") -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE background_runs
                SET finished_at = ?, status = ?, scanned_count = ?,
                    failure_count = ?, action_count = ?, error_message = ?
                WHERE id = ?
                """,
                (self._now(), status, scanned, failures, actions, error, run_id),
            )
            connection.commit()

    @staticmethod
    def _normalize(rows: list[dict[str, Any]], market: str, universe: str) -> list[dict[str, Any]]:
        normalized = []
        for row in rows:
            item = dict(row)
            symbol = str(item.get("Kod") or item.get("Coin") or item.get("Emtia") or "").strip()
            name = str(item.get("Hisse") or item.get("Coin") or item.get("Emtia") or symbol)
            analysis = analyze_signal_payload(item)
            item.update({
                "Kod": symbol,
                "Ad": name,
                "Piyasa": market,
                "Evren": universe,
                "Güven": analysis["confidence"],
                "Güven Durumu": analysis["confidence_label"],
                "Güven Yıldızı": analysis["confidence_stars"],
                "Risk": analysis["risk_level"],
                "Başarı Göstergesi %": analysis["probability"],
                "AI Analizi": analysis["summary"],
            })
            normalized.append(item)
        return normalized

    def _save_results(self, run_id: int, rows: list[dict[str, Any]], market: str, universe: str) -> None:
        created_at = self._now()
        limited = rows[: self.settings.max_saved_rows_per_run]
        with self.database.connect() as connection:
            connection.executemany(
                """
                INSERT INTO background_scan_results(
                    run_id, market, universe, symbol, name, decision, score,
                    price, stop_price, target1, target2, confidence,
                    confidence_label, risk_level, probability, reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [(
                    run_id, market, universe, row.get("Kod", ""), row.get("Ad", ""),
                    row.get("Karar", ""), float(row.get("Puan", 0) or 0),
                    float(row.get("Fiyat", 0) or 0), float(row.get("Stop", 0) or 0),
                    float(row.get("Hedef 1", 0) or 0), float(row.get("Hedef 2", 0) or 0),
                    float(row.get("Güven", 0) or 0), row.get("Güven Durumu", ""),
                    row.get("Risk", ""), float(row.get("Başarı Göstergesi %", 0) or 0),
                    row.get("AI Analizi", row.get("Neden", "")), created_at,
                ) for row in limited],
            )
            connection.commit()

    def _save_robot_diagnostics(
        self,
        market: str,
        universe: str,
        diagnostics: list[str],
        scanned_count: int,
    ) -> None:
        payload = {
            "market": market,
            "universe": universe,
            "scanned_count": scanned_count,
            "diagnostics": diagnostics,
        }

        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO system_events (
                    created_at,
                    event_type,
                    message
                )
                VALUES (?, ?, ?)
                """,
                (
                    self._now(),
                    "ROBOT_DIAGNOSTIC",
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            connection.commit()

    def _candidate_diagnostics(self, rows: list[dict[str, Any]], market: str = "BIST", universe: str = "", limit: int = 8) -> list[str]:
        diagnostics: list[str] = []
        ranked = sorted(rows, key=lambda row: float(row.get("Puan", 0) or 0), reverse=True)
        robot = self._robot_for_market(market, universe)
        state = robot.get_state()
        for row in ranked[:limit]:
            symbol = str(row.get("Kod", "?"))
            decision = str(row.get("Karar", ""))
            score = float(row.get("Puan", 0) or 0)
            confidence = float(row.get("Güven", 0) or 0)
            probability = float(row.get("Başarı Göstergesi %", 0) or 0)
            risk = str(row.get("Risk", "")).strip()
            reasons: list[str] = []
            if not state["enabled"]:
                reasons.append("robot kapalı")
            if decision not in robot.config.allowed_decisions:
                reasons.append(f"karar={decision or 'yok'}")
            if score < robot.config.minimum_score:
                reasons.append(f"puan {score:.0f} < {robot.config.minimum_score:.0f}")
            if confidence < robot.config.minimum_confidence:
                reasons.append(f"güven {confidence:.0f} < {robot.config.minimum_confidence:.0f}")
            if probability < robot.config.minimum_probability:
                reasons.append(f"olasılık %{probability:.0f} < %{robot.config.minimum_probability:.0f}")
            if robot.config.allowed_risks and risk not in robot.config.allowed_risks:
                reasons.append(f"risk={risk or 'yok'} kabul edilmiyor")
            if robot.has_open_position(symbol):
                reasons.append("açık pozisyon var")
            if not reasons:
                reasons.append("işleme uygun aday")
            diagnostics.append(f"{symbol}: " + ", ".join(reasons))
        return diagnostics

    def _process_robot(self, rows: list[dict[str, Any]], market: str, universe: str, enabled: bool):
        robot = self._robot_for_market(market, universe)
        latest_prices = {
            str(row.get("Kod", "")): float(row.get("Fiyat", 0) or 0)
            for row in rows if row.get("Kod") and float(row.get("Fiyat", 0) or 0) > 0
        }
        latest_signals = {
            str(row.get("Kod", "")): {
                "rsi": float(row.get("RSI", 0) or 0),
                "previous_rsi": float(row.get("Previous_RSI", 0) or 0),
                "macd_hist": float(row.get("MACD_HIST", 0) or 0),
                "close": float(row.get("Close", row.get("Fiyat", 0)) or 0),
                "ema20": float(row.get("EMA20", 0) or 0),
                "atr": float(row.get("ATR", 0) or 0),
                "volume_ratio": float(row.get("Volume_Ratio", 0) or 0),
                "adx": float(row.get("ADX", 0) or 0),
                "previous_adx": float(row.get("Previous_ADX", 0) or 0),
            }
            for row in rows
            if row.get("Kod")
        }
        actions = robot.process_open_positions(
            latest_prices,
            latest_signals=latest_signals,
        )
        if enabled:
            actions.extend(robot.process_scanner_results(
                rows, market=normalize_market(market), universe=universe,
                strategy_profile=f"Background {normalize_market(market)} V1"
            ))
        return actions

    def _notify_actions(self, market: str, universe: str, actions: list[dict[str, Any]]) -> None:
        successful = [action for action in actions if action.get("ok")]
        for action in successful:
            symbol = str(action.get("symbol", ""))
            if "profit" in action:
                profit = float(action.get("profit", 0) or 0)
                self.notifier.send(
                    "ROBOT_SELL",
                    f"AlphaScan satış: {symbol}",
                    f"{market}/{universe} sanal pozisyon kapandı. Kâr/Zarar: {profit:,.2f}",
                    action,
                )
            else:
                score = float(action.get("score", 0) or 0)
                price = float(action.get("price", 0) or 0)
                self.notifier.send(
                    "ROBOT_BUY",
                    f"AlphaScan alım: {symbol}",
                    f"{market}/{universe} sanal işlem açıldı. Fiyat: {price:.4f} | Puan: {score:.0f}",
                    action,
                )

    def _execute(self, market: str, universe: str, scan_callable, robot_enabled: bool) -> dict[str, Any]:
        run_id = self._start_run(market, universe)
        try:
            rows, failures = scan_callable()
            rows = self._normalize(rows, market, universe)
            self._save_results(run_id, rows, market, universe)

            analytics_robot = self._robot_for_market(market, universe)
            analytics_count = self.filter_analytics.record_rows(
                run_id=run_id,
                rows=rows,
                market=market,
                universe=universe,
                robot=analytics_robot,
                robot_enabled=robot_enabled,
            )

            self.logger.info(
                "%s/%s filtre analizi: %s karar kaydedildi",
                market,
                universe,
                analytics_count,
            )

            actions = self._process_robot(
                rows,
                market,
                universe,
                robot_enabled,
            )
            successful_actions = [action for action in actions if action.get("ok")]
            self._finish_run(run_id, status="SUCCESS", scanned=len(rows), failures=len(failures), actions=len(successful_actions))
            self.logger.info("%s/%s tamamlandı: %s sonuç, %s hata, %s robot aksiyonu", market, universe, len(rows), len(failures), len(successful_actions))
            if successful_actions:
                self._notify_actions(market, universe, successful_actions)
            else:
                diagnostics = self._candidate_diagnostics(rows, market, universe)

                self._save_robot_diagnostics(
                    market=market,
                    universe=universe,
                    diagnostics=diagnostics,
                    scanned_count=len(rows),
                )

                self.logger.info(
                    "%s/%s işlem açılmama nedenleri: %s",
                    market,
                    universe,
                    " | ".join(diagnostics),
                )

                if self.settings.notify_no_action:
                    self.notifier.send(
                        "NO_ACTION",
                        f"AlphaScan: {market} tarandı",
                        f"{len(rows)} sonuç incelendi, uygun işlem bulunamadı.",
                        {"market": market, "universe": universe, "diagnostics": diagnostics},
                    )
            return {"ok": True, "rows": len(rows), "failures": len(failures), "actions": successful_actions}
        except Exception as exc:
            self._finish_run(run_id, status="ERROR", error=str(exc))
            self.logger.exception("%s/%s taraması başarısız", market, universe)
            return {"ok": False, "error": str(exc)}

    def run_bist(self) -> dict[str, Any]:
        configured = list(getattr(self.settings, "bist_universes", []) or [])
        if not configured:
            configured = [self.settings.bist_universe]

        # Aynı evrenin farklı yazımlarla iki kez taranmasını engeller.
        unique_universes: list[str] = []
        seen: set[str] = set()
        for universe in configured:
            key = str(universe).strip()
            normalized = key.casefold().replace("ı", "i")
            if key and normalized not in seen:
                seen.add(normalized)
                unique_universes.append(key)

        results: list[dict[str, Any]] = []
        for universe in unique_universes:
            items = self.watchlists.get(universe, [])
            if not items and universe in {"Arındırma 0", "Arindirma 0"}:
                items = self.watchlists.get("arindirma_0", [])
            if not items and universe in {"Katılım Tüm", "Katilim Tum"}:
                items = self.watchlists.get("katilim_tum", [])
            if not items:
                self.logger.warning("BIST/%s evreni boş; tarama atlandı.", universe)
                results.append({"ok": False, "universe": universe, "error": "Evren boş"})
                continue
            results.append(
                self._execute(
                    "BIST", universe,
                    lambda selected=items: scan_yahoo_items(self.data_engine, selected, workers=4),
                    self.settings.bist.robot_enabled,
                )
            )

        return {
            "ok": bool(results) and all(item.get("ok", False) for item in results),
            "universes": results,
            "rows": sum(int(item.get("rows", 0) or 0) for item in results),
            "failures": sum(int(item.get("failures", 0) or 0) for item in results),
            "actions": [
                action
                for item in results
                for action in item.get("actions", [])
            ],
        }

    def run_crypto(self) -> dict[str, Any]:
        pairs = get_crypto_pairs(self.settings.crypto_group)
        return self._execute(
            "KRIPTO", self.settings.crypto_group,
            lambda: scan_crypto(self.data_engine, pairs),
            self.settings.crypto.robot_enabled,
        )

    def run_commodity(self) -> dict[str, Any]:
        return self._execute(
            "EMTIA", "Ana Emtialar",
            lambda: scan_commodities(self.data_engine, self.settings.commodities),
            self.settings.commodity.robot_enabled,
        )