from __future__ import annotations

import json

from datetime import datetime
from typing import Any

from config.market_universes import get_crypto_pairs
from database.robot_settings_repository import load_robot_settings
from engine.analysis_engine import analyze_signal_payload
from engine.filter_analytics import FilterAnalytics
from engine.decision_trace import build_decision_trace
from engine.market_accounts import account_for_context, normalize_market
from engine.market_intelligence_pipeline import MarketIntelligencePipeline
from engine.notification_manager import NotificationManager
from engine.robot_engine import RobotConfig, RobotEngine
from engine.robot_intelligence_hub import RobotIntelligenceHub
from engine.scanner import scan_commodities, scan_crypto, scan_yahoo_items


class BackgroundOrchestrator:
    def __init__(
        self,
        database,
        data_engine,
        watchlists: dict,
        settings,
        logger,
    ) -> None:
        self.database = database
        self.data_engine = data_engine
        self.watchlists = watchlists
        self.settings = settings
        self.logger = logger

        self.notifier = NotificationManager(
            database,
            settings,
            logger,
        )

        self.robot = self._robot_for_market(
            "BIST",
            "Genel",
        )

        self.filter_analytics = FilterAnalytics(
            database,
            logger,
        )
        self.intelligence_hub = RobotIntelligenceHub(database, logger)

        # Market Intelligence Pipeline ihtiyaç duyulduğunda oluşturulur.
        # Pipeline başlangıç sırasında hata verirse Background Worker
        # tamamen durmaz.
        self.market_intelligence_pipeline: (
            MarketIntelligencePipeline | None
        ) = None

    def _robot_for_market(
        self,
        market: str,
        universe: str = "",
    ) -> RobotEngine:
        normalized = normalize_market(market)

        account = account_for_context(
            normalized,
            universe,
        )

        saved = load_robot_settings(
            self.database,
            account_id=account["account_id"],
            market=normalized,
        )

        return RobotEngine(
            self.database,
            RobotConfig(
                starting_balance=float(
                    account["starting_balance"]
                ),
                max_positions=int(
                    saved["max_positions"]
                ),
                position_size_pct=float(
                    saved["position_size_pct"]
                ),
                minimum_score=float(
                    saved["minimum_score"]
                ),
                minimum_confidence=float(
                    saved["minimum_confidence"]
                ),
                minimum_probability=float(
                    saved["minimum_probability"]
                ),
                allowed_decisions=tuple(
                    saved["allowed_decisions"]
                ),
                allowed_risks=tuple(
                    saved["allowed_risks"]
                ),
                strategy_profile=str(
                    saved["strategy_profile"]
                ),
                market=normalized,
                account_id=account["account_id"],
                currency=account["currency"],
            ),
        )

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(
            timespec="seconds"
        )

    @staticmethod
    def _comparison_symbol(
        symbol: Any,
        market: str,
    ) -> str:
        value = str(
            symbol or ""
        ).strip().upper()

        normalized_market = normalize_market(
            market
        )

        compact_value = (
            value.replace("-", "")
            .replace("/", "")
            .replace("_", "")
            .replace(" ", "")
            .replace(".", "")
            .replace("=", "")
        )

        compact_value = compact_value.translate(
            str.maketrans(
                {
                    "Ç": "C",
                    "Ğ": "G",
                    "İ": "I",
                    "Ö": "O",
                    "Ş": "S",
                    "Ü": "U",
                }
            )
        )

        if normalized_market == "EMTIA":
            aliases = {
                "ALTIN": "GOLD",
                "GOLD": "GOLD",
                "GCF": "GOLD",
                "GUMUS": "SILVER",
                "SILVER": "SILVER",
                "SIF": "SILVER",
                "BAKIR": "COPPER",
                "COPPER": "COPPER",
                "HGF": "COPPER",
                "BRENT": "BRENT",
                "BRENTPETROL": "BRENT",
                "BZF": "BRENT",
                "WTI": "WTI",
                "WTIPETROL": "WTI",
                "HAMPETROL": "WTI",
                "CLF": "WTI",
                "DOGALGAZ": "NATGAS",
                "NATGAS": "NATGAS",
                "NGF": "NATGAS",
                "PLATIN": "PLATINUM",
                "PLATINUM": "PLATINUM",
                "PLF": "PLATINUM",
                "PALADYUM": "PALLADIUM",
                "PALLADIUM": "PALLADIUM",
                "PAF": "PALLADIUM",
                                "BESISIGIRI": "FEEDERCATTLE",
                "FEEDERCATTLE": "FEEDERCATTLE",

                "CANLISIGIR": "LIVECATTLE",
                "LIVECATTLE": "LIVECATTLE",

                "BUGDAY": "WHEAT",
                "WHEAT": "WHEAT",

                "KAHVE": "COFFEE",
                "COFFEE": "COFFEE",

                "KAKAO": "COCOA",
                "COCOA": "COCOA",

                "KALORIFERYAKITI": "HEATINGOIL",
                "HEATINGOIL": "HEATINGOIL",

                "MISIR": "CORN",
                "CORN": "CORN",

                "PAMUK": "COTTON",
                "COTTON": "COTTON",

                "PIRINC": "RICE",
                "RICE": "RICE",

                "PORTAKALSUYU": "ORANGEJUICE",
                "ORANGEJUICE": "ORANGEJUICE",

                "RBOBBENZIN": "RBOBGASOLINE",
                "RBOBGASOLINE": "RBOBGASOLINE",

                "SOYAFASULYESI": "SOYBEAN",
                "SOYBEAN": "SOYBEAN",

                "SOYAKUSPESI": "SOYBEANMEAL",
                "SOYBEANMEAL": "SOYBEANMEAL",

                "SOYAYAGI": "SOYBEANOIL",
                "SOYBEANOIL": "SOYBEANOIL",

                "YAGSIZDOMUZ": "LEANHOGS",
                "LEANHOGS": "LEANHOGS",

                "YULAF": "OATS",
                "OATS": "OATS",

                "SEKER": "SUGAR",
                "SUGAR": "SUGAR",
            }
            return aliases.get(
                compact_value,
                compact_value,
            )

        if normalized_market != "KRIPTO":
            return value

        for suffix in (
            "USDT",
            "USDC",
            "BUSD",
            "USD",
            "TRY",
            "EUR",
        ):
            if (
                compact_value.endswith(suffix)
                and len(compact_value) > len(suffix)
            ):
                return compact_value[
                    :-len(suffix)
                ]

        return compact_value

    def _start_run(
        self,
        market: str,
        universe: str,
    ) -> int:
        with self.database.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO background_runs(
                    market,
                    universe,
                    started_at,
                    status
                )
                VALUES (?, ?, ?, 'RUNNING')
                """,
                (
                    market,
                    universe,
                    self._now(),
                ),
            )

            connection.commit()

            return int(cursor.lastrowid)

    def _finish_run(
        self,
        run_id: int,
        *,
        status: str,
        scanned: int = 0,
        failures: int = 0,
        actions: int = 0,
        error: str = "",
    ) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                UPDATE background_runs
                SET
                    finished_at = ?,
                    status = ?,
                    scanned_count = ?,
                    failure_count = ?,
                    action_count = ?,
                    error_message = ?
                WHERE id = ?
                """,
                (
                    self._now(),
                    status,
                    scanned,
                    failures,
                    actions,
                    error,
                    run_id,
                ),
            )

            connection.commit()

    @staticmethod
    def _normalize(
        rows: list[dict[str, Any]],
        market: str,
        universe: str,
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []

        for row in rows:
            item = dict(row)

            symbol = str(
                item.get("Kod")
                or item.get("Coin")
                or item.get("Emtia")
                or ""
            ).strip()

            name = str(
                item.get("Hisse")
                or item.get("Coin")
                or item.get("Emtia")
                or symbol
            )

            analysis = analyze_signal_payload(item)

            item.update(
                {
                    "Kod": symbol,
                    "Ad": name,
                    "Piyasa": market,
                    "Evren": universe,
                    "Güven": analysis["confidence"],
                    "Güven Durumu": analysis[
                        "confidence_label"
                    ],
                    "Güven Yıldızı": analysis[
                        "confidence_stars"
                    ],
                    "Risk": analysis["risk_level"],
                    "Başarı Göstergesi %": analysis[
                        "probability"
                    ],
                    "AI Analizi": analysis["summary"],
                }
            )

            normalized.append(item)

        return normalized

    def _save_results(
        self,
        run_id: int,
        rows: list[dict[str, Any]],
        market: str,
        universe: str,
    ) -> None:
        created_at = self._now()

        limited = rows[
            : self.settings.max_saved_rows_per_run
        ]

        with self.database.connect() as connection:
            connection.executemany(
                """
                INSERT INTO background_scan_results(
                    run_id,
                    market,
                    universe,
                    symbol,
                    name,
                    decision,
                    score,
                    price,
                    stop_price,
                    target1,
                    target2,
                    confidence,
                    confidence_label,
                    risk_level,
                    probability,
                    reason,
                    created_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?
                )
                """,
                [
                    (
                        run_id,
                        market,
                        universe,
                        row.get("Kod", ""),
                        row.get("Ad", ""),
                        row.get("Karar", ""),
                        float(
                            row.get("Puan", 0)
                            or 0
                        ),
                        float(
                            row.get("Fiyat", 0)
                            or 0
                        ),
                        float(
                            row.get("Stop", 0)
                            or 0
                        ),
                        float(
                            row.get("Hedef 1", 0)
                            or 0
                        ),
                        float(
                            row.get("Hedef 2", 0)
                            or 0
                        ),
                        float(
                            row.get("Güven", 0)
                            or 0
                        ),
                        row.get(
                            "Güven Durumu",
                            "",
                        ),
                        row.get("Risk", ""),
                        float(
                            row.get(
                                "Başarı Göstergesi %",
                                0,
                            )
                            or 0
                        ),
                        row.get(
                            "AI Analizi",
                            row.get("Neden", ""),
                        ),
                        created_at,
                    )
                    for row in limited
                ],
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
                INSERT INTO system_events(
                    created_at,
                    event_type,
                    message
                )
                VALUES (?, ?, ?)
                """,
                (
                    self._now(),
                    "ROBOT_DIAGNOSTIC",
                    json.dumps(
                        payload,
                        ensure_ascii=False,
                    ),
                ),
            )

            connection.commit()

    def _candidate_diagnostics(
        self,
        rows: list[dict[str, Any]],
        market: str = "BIST",
        universe: str = "",
        limit: int = 8,
    ) -> list[str]:
        robot = self._robot_for_market(market, universe)
        ranked = sorted(
            rows,
            key=lambda row: float(row.get("Puan", 0) or 0),
            reverse=True,
        )
        return [
            build_decision_trace(row, robot).to_text()
            for row in ranked[:limit]
        ]

    def _run_market_intelligence(
        self,
        rows: list[dict[str, Any]],
        market: str,
        universe: str,
    ) -> dict[str, Any]:
        symbols = sorted(
            {
                str(
                    row.get("Kod", "")
                ).strip().upper()
                for row in rows
                if str(
                    row.get("Kod", "")
                ).strip()
            }
        )

        if not symbols:
            return {
                "ok": True,
                "total": 0,
                "successful": 0,
                "failed": 0,
                "received_candles": 0,
                "saved_candles": 0,
                "calculated_indicators": 0,
                "saved_indicators": 0,
                "failed_details": [],
                "successful_symbols": [],
                "intelligence_completed": True,
            }

        try:
            if (
                self.market_intelligence_pipeline
                is None
            ):
                self.market_intelligence_pipeline = (
                    MarketIntelligencePipeline()
                )

            batch = (
                self.market_intelligence_pipeline
                .run_symbols(
                    symbols,
                    market=market,
                )
            )

            failed_details = [
                {
                    "symbol": result.symbol,
                    "error_type": (
                        result.error_type
                    ),
                    "error_message": (
                        result.error_message
                    ),
                }
                for result in batch.results
                if result.status == "FAILED"
            ]

            successful_symbols = [
                str(result.symbol).strip().upper()
                for result in batch.results
                if result.status == "SUCCESS"
            ]

            self.logger.info(
                "%s/%s market intelligence: "
                "%s enstrüman, "
                "%s başarılı, "
                "%s başarısız, "
                "%s mum alındı, "
                "%s mum kaydedildi, "
                "%s gösterge hesaplandı, "
                "%s gösterge kaydedildi",
                market,
                universe,
                batch.total,
                batch.successful,
                batch.failed,
                batch.received_candles,
                batch.saved_candles,
                batch.calculated_indicators,
                batch.saved_indicators,
            )

            if failed_details:
                self.logger.warning(
                    "%s/%s market intelligence "
                    "hataları: %s",
                    market,
                    universe,
                    json.dumps(
                        failed_details[:10],
                        ensure_ascii=False,
                    ),
                )

            return {
                "ok": batch.failed == 0,
                "total": batch.total,
                "successful": batch.successful,
                "failed": batch.failed,
                "received_candles": (
                    batch.received_candles
                ),
                "saved_candles": (
                    batch.saved_candles
                ),
                "calculated_indicators": (
                    batch.calculated_indicators
                ),
                "saved_indicators": (
                    batch.saved_indicators
                ),
                "failed_details": failed_details,
                "successful_symbols": (
                    successful_symbols
                ),
                "intelligence_completed": True,
            }

        except Exception as exc:
            self.logger.exception(
                "%s/%s market intelligence "
                "çalıştırılamadı",
                market,
                universe,
            )

            return {
                "ok": False,
                "total": 0,
                "successful": 0,
                "failed": len(symbols),
                "received_candles": 0,
                "saved_candles": 0,
                "calculated_indicators": 0,
                "saved_indicators": 0,
                "failed_details": [],
                "successful_symbols": [],
                "intelligence_completed": False,
                "error": str(exc),
            }

    def _process_robot(
        self,
        rows: list[dict[str, Any]],
        market: str,
        universe: str,
        enabled: bool,
    ) -> list[dict[str, Any]]:
        robot = self._robot_for_market(
            market,
            universe,
        )

        latest_prices = {
            str(
                row.get("Kod", "")
            ): float(
                row.get("Fiyat", 0)
                or 0
            )
            for row in rows
            if (
                row.get("Kod")
                and float(
                    row.get("Fiyat", 0)
                    or 0
                )
                > 0
            )
        }

        latest_signals = {
            str(
                row.get("Kod", "")
            ): {
                "rsi": float(
                    row.get("RSI", 0)
                    or 0
                ),
                "previous_rsi": float(
                    row.get(
                        "Previous_RSI",
                        0,
                    )
                    or 0
                ),
                "macd_hist": float(
                    row.get(
                        "MACD_HIST",
                        0,
                    )
                    or 0
                ),
                "close": float(
                    row.get(
                        "Close",
                        row.get("Fiyat", 0),
                    )
                    or 0
                ),
                "ema20": float(
                    row.get("EMA20", 0)
                    or 0
                ),
                "atr": float(
                    row.get("ATR", 0)
                    or 0
                ),
                "volume_ratio": float(
                    row.get(
                        "Volume_Ratio",
                        0,
                    )
                    or 0
                ),
                "adx": float(
                    row.get("ADX", 0)
                    or 0
                ),
                "previous_adx": float(
                    row.get(
                        "Previous_ADX",
                        0,
                    )
                    or 0
                ),
            }
            for row in rows
            if row.get("Kod")
        }

        actions = robot.process_open_positions(
            latest_prices,
            latest_signals=latest_signals,
        )

        if enabled:
            actions.extend(
                robot.process_scanner_results(
                    rows,
                    market=normalize_market(
                        market
                    ),
                    universe=universe,
                    strategy_profile=(
                        "Background "
                        f"{normalize_market(market)} "
                        "V1"
                    ),
                )
            )

        return actions

    def _notify_actions(
        self,
        market: str,
        universe: str,
        actions: list[dict[str, Any]],
    ) -> None:
        successful = [
            action
            for action in actions
            if action.get("ok")
        ]

        for action in successful:
            symbol = str(
                action.get("symbol", "")
            )

            if "profit" in action:
                profit = float(
                    action.get("profit", 0)
                    or 0
                )

                self.notifier.send(
                    "ROBOT_SELL",
                    f"AlphaScan satış: {symbol}",
                    (
                        f"{market}/{universe} "
                        "sanal pozisyon kapandı. "
                        f"Kâr/Zarar: {profit:,.2f}"
                    ),
                    action,
                )

            else:
                score = float(
                    action.get("score", 0)
                    or 0
                )

                price = float(
                    action.get("price", 0)
                    or 0
                )

                self.notifier.send(
                    "ROBOT_BUY",
                    f"AlphaScan alım: {symbol}",
                    (
                        f"{market}/{universe} "
                        "sanal işlem açıldı. "
                        f"Fiyat: {price:.4f} | "
                        f"Puan: {score:.0f}"
                    ),
                    action,
                )

    def _execute(
        self,
        market: str,
        universe: str,
        scan_callable,
        robot_enabled: bool,
    ) -> dict[str, Any]:
        run_id = self._start_run(
            market,
            universe,
        )

        try:
            rows, failures = scan_callable()

            rows = self._normalize(
                rows,
                market,
                universe,
            )

            self._save_results(
                run_id,
                rows,
                market,
                universe,
            )

            # Market Intelligence başarısız olsa bile
            # ana tarama ve robot çalışmaya devam eder.
            intelligence_result = (
                self._run_market_intelligence(
                    rows=rows,
                    market=market,
                    universe=universe,
                )
            )

            # Market Intelligence tamamlandıysa yalnızca
            # güncel verisi başarıyla alınan semboller
            # filtre analizine ve robota gönderilir.
            #
            # Pipeline'ın kendisi beklenmeyen bir hatayla
            # çökerse ana tarama akışı korunur ve mevcut
            # satırlar kullanılmaya devam edilir.
            if intelligence_result.get(
                "intelligence_completed",
                False,
            ):
                successful_symbols = {
                    self._comparison_symbol(
                        symbol,
                        market,
                    )
                    for symbol in (
                        intelligence_result.get(
                            "successful_symbols",
                            [],
                        )
                        or []
                    )
                }
                
                excluded_symbols = sorted(
                    {
                        str(
                            row.get("Kod", "")
                        ).strip().upper()
                        for row in rows
                        if str(
                            row.get("Kod", "")
                        ).strip()
                        and self._comparison_symbol(
                            row.get("Kod", ""),
                            market,
                        )
                        not in successful_symbols
                    }
                )

                rows = [
                    row
                    for row in rows
                    if self._comparison_symbol(
                        row.get("Kod", ""),
                        market,
                    )
                    in successful_symbols
                ]

                if excluded_symbols:
                    self.logger.warning(
                        "%s/%s güncel verisi "
                        "olmayan semboller filtre "
                        "ve robot aşamasından "
                        "çıkarıldı: %s",
                        market,
                        universe,
                        ", ".join(
                            excluded_symbols
                        ),
                    )

            analytics_robot = (
                self._robot_for_market(
                    market,
                    universe,
                )
            )

            analytics_count = (
                self.filter_analytics.record_rows(
                    run_id=run_id,
                    rows=rows,
                    market=market,
                    universe=universe,
                    robot=analytics_robot,
                    robot_enabled=robot_enabled,
                )
            )

            self.logger.info(
                "%s/%s filtre analizi: "
                "%s karar kaydedildi",
                market,
                universe,
                analytics_count,
            )

            intelligence_event_count = self.intelligence_hub.capture_scan(
                run_id=run_id, rows=rows, market=market, universe=universe,
                robot=analytics_robot, robot_enabled=robot_enabled,
            )
            self.logger.info(
                "%s/%s intelligence: %s olay kaydedildi",
                market, universe, intelligence_event_count,
            )

            actions = self._process_robot(
                rows,
                market,
                universe,
                robot_enabled,
            )

            successful_actions = [
                action
                for action in actions
                if action.get("ok")
            ]

            self.intelligence_hub.capture_actions(
                actions=successful_actions, rows=rows, market=market, universe=universe,
                account_id=str(getattr(analytics_robot, "account_id", "")),
            )

            self._finish_run(
                run_id,
                status="SUCCESS",
                scanned=len(rows),
                failures=len(failures),
                actions=len(
                    successful_actions
                ),
            )

            self.logger.info(
                "%s/%s tamamlandı: "
                "%s sonuç, "
                "%s hata, "
                "%s robot aksiyonu",
                market,
                universe,
                len(rows),
                len(failures),
                len(successful_actions),
            )

            if successful_actions:
                self._notify_actions(
                    market,
                    universe,
                    successful_actions,
                )

            else:
                diagnostics = (
                    self._candidate_diagnostics(
                        rows,
                        market,
                        universe,
                    )
                )

                self._save_robot_diagnostics(
                    market=market,
                    universe=universe,
                    diagnostics=diagnostics,
                    scanned_count=len(rows),
                )

                self.logger.info(
                    "%s/%s işlem açılmama "
                    "nedenleri: %s",
                    market,
                    universe,
                    " | ".join(diagnostics),
                )

                if self.settings.notify_no_action:
                    self.notifier.send(
                        "NO_ACTION",
                        (
                            f"AlphaScan: "
                            f"{market} tarandı"
                        ),
                        (
                            f"{len(rows)} sonuç "
                            "incelendi, uygun işlem "
                            "bulunamadı."
                        ),
                        {
                            "market": market,
                            "universe": universe,
                            "diagnostics": diagnostics,
                        },
                    )

            return {
                "ok": True,
                "rows": len(rows),
                "failures": len(failures),
                "actions": successful_actions,
                "market_intelligence": (
                    intelligence_result
                ),
            }

        except Exception as exc:
            self._finish_run(
                run_id,
                status="ERROR",
                error=str(exc),
            )

            self.logger.exception(
                "%s/%s taraması başarısız",
                market,
                universe,
            )

            return {
                "ok": False,
                "error": str(exc),
            }

    def run_bist(
        self,
    ) -> dict[str, Any]:
        configured = list(
            getattr(
                self.settings,
                "bist_universes",
                [],
            )
            or []
        )

        if not configured:
            configured = [
                self.settings.bist_universe
            ]

        # Aynı evrenin farklı yazımlarla
        # iki kez taranmasını engeller.
        unique_universes: list[str] = []
        seen: set[str] = set()

        for universe in configured:
            key = str(universe).strip()

            normalized = (
                key.casefold()
                .replace("ı", "i")
            )

            if (
                key
                and normalized not in seen
            ):
                seen.add(normalized)
                unique_universes.append(key)

        results: list[dict[str, Any]] = []

        for universe in unique_universes:
            items = self.watchlists.get(
                universe,
                [],
            )

            if (
                not items
                and universe
                in {
                    "Arındırma 0",
                    "Arindirma 0",
                }
            ):
                items = self.watchlists.get(
                    "arindirma_0",
                    [],
                )

            if (
                not items
                and universe
                in {
                    "Katılım Tüm",
                    "Katilim Tum",
                }
            ):
                items = self.watchlists.get(
                    "katilim_tum",
                    [],
                )

            if not items:
                self.logger.warning(
                    "BIST/%s evreni boş; "
                    "tarama atlandı.",
                    universe,
                )

                results.append(
                    {
                        "ok": False,
                        "universe": universe,
                        "error": "Evren boş",
                    }
                )

                continue

            results.append(
                self._execute(
                    "BIST",
                    universe,
                    lambda selected=items: (
                        scan_yahoo_items(
                            self.data_engine,
                            selected,
                            workers=4,
                        )
                    ),
                    self.settings.bist.robot_enabled,
                )
            )

        return {
            "ok": (
                bool(results)
                and all(
                    item.get("ok", False)
                    for item in results
                )
            ),
            "universes": results,
            "rows": sum(
                int(
                    item.get("rows", 0)
                    or 0
                )
                for item in results
            ),
            "failures": sum(
                int(
                    item.get(
                        "failures",
                        0,
                    )
                    or 0
                )
                for item in results
            ),
            "actions": [
                action
                for item in results
                for action in item.get(
                    "actions",
                    [],
                )
            ],
        }

    def run_crypto(
        self,
    ) -> dict[str, Any]:
        pairs = get_crypto_pairs(
            self.settings.crypto_group
        )

        return self._execute(
            "KRIPTO",
            self.settings.crypto_group,
            lambda: scan_crypto(
                self.data_engine,
                pairs,
            ),
            self.settings.crypto.robot_enabled,
        )

    def run_commodity(
        self,
    ) -> dict[str, Any]:
        return self._execute(
            "EMTIA",
            "Ana Emtialar",
            lambda: scan_commodities(
                self.data_engine,
                self.settings.commodities,
            ),
            self.settings.commodity.robot_enabled,
        )