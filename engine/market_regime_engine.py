from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MarketRegimeResult:
    regime: str
    score: float
    confidence: float
    allow_new_positions: bool
    risk_multiplier: float
    max_positions_multiplier: float
    cash_target_pct: float
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["reasons"] = list(self.reasons)
        return data


class MarketRegimeEngine:
    REQUIRED_COLUMNS = {"close", "ema20", "ema50", "ema200", "rsi", "adx", "macd_hist", "atr"}

    def analyze(self, frame: pd.DataFrame) -> MarketRegimeResult:
        if frame is None or frame.empty:
            return self._fallback("YETERSİZ VERİ", "Piyasa verisi bulunamadı.")

        normalized = self._normalize_columns(frame)
        missing = self.REQUIRED_COLUMNS.difference(normalized.columns)
        if missing:
            return self._fallback(
                "YETERSİZ VERİ",
                "Eksik kolonlar: " + ", ".join(sorted(missing)),
            )

        clean = normalized.replace([np.inf, -np.inf], np.nan).dropna(
            subset=list(self.REQUIRED_COLUMNS)
        )
        if len(clean) < 20:
            return self._fallback(
                "YETERSİZ VERİ",
                f"En az 20 geçerli mum gerekli; mevcut={len(clean)}.",
            )

        last = clean.iloc[-1]
        previous = clean.iloc[-6] if len(clean) >= 6 else clean.iloc[0]

        close = float(last["close"])
        ema20 = float(last["ema20"])
        ema50 = float(last["ema50"])
        ema200 = float(last["ema200"])
        rsi = float(last["rsi"])
        adx = float(last["adx"])
        macd_hist = float(last["macd_hist"])
        atr = float(last["atr"])

        ema20_slope_pct = (
            (ema20 / float(previous["ema20"]) - 1.0) * 100.0
            if float(previous["ema20"]) != 0
            else 0.0
        )
        atr_pct = atr / close * 100.0 if close > 0 else 0.0

        score = 0.0
        reasons: list[str] = []

        if ema50 > ema200:
            score += 22
            reasons.append("EMA50, EMA200 üzerinde.")
        else:
            reasons.append("EMA50, EMA200 altında.")

        if close > ema50:
            score += 14
            reasons.append("Fiyat EMA50 üzerinde.")
        else:
            reasons.append("Fiyat EMA50 altında.")

        if ema20 > ema50:
            score += 10
            reasons.append("EMA20, EMA50 üzerinde.")

        if ema20_slope_pct > 0.25:
            score += 12
            reasons.append("EMA20 eğimi güçlü pozitif.")
        elif ema20_slope_pct > 0:
            score += 6
            reasons.append("EMA20 eğimi pozitif.")
        else:
            reasons.append("EMA20 eğimi negatif.")

        if 50 <= rsi <= 68:
            score += 14
            reasons.append("RSI yükseliş bölgesinde.")
        elif 42 <= rsi < 50:
            score += 7
            reasons.append("RSI toparlanma bölgesinde.")
        elif rsi < 35:
            reasons.append("RSI zayıf bölgede.")

        if macd_hist > 0:
            score += 12
            reasons.append("MACD histogram pozitif.")
        else:
            reasons.append("MACD histogram negatif.")

        if adx >= 25:
            score += 10
            reasons.append("ADX güçlü trend gösteriyor.")
        elif adx >= 18:
            score += 6
            reasons.append("ADX kabul edilebilir trend gösteriyor.")
        else:
            reasons.append("ADX trend gücü düşük.")

        if atr_pct <= 2.5:
            score += 6
            reasons.append("Volatilite kontrollü.")
        elif atr_pct >= 5.0:
            score -= 8
            reasons.append("Volatilite yüksek.")

        score = max(0.0, min(100.0, score))
        regime = self._classify(score)
        confidence = self._confidence(score)
        policy = self._policy(regime)

        return MarketRegimeResult(
            regime=regime,
            score=round(score, 2),
            confidence=round(confidence, 2),
            allow_new_positions=policy["allow_new_positions"],
            risk_multiplier=policy["risk_multiplier"],
            max_positions_multiplier=policy["max_positions_multiplier"],
            cash_target_pct=policy["cash_target_pct"],
            reasons=tuple(reasons),
        )

    @staticmethod
    def _normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
        aliases = {
            "Close": "close",
            "EMA20": "ema20",
            "EMA50": "ema50",
            "EMA200": "ema200",
            "RSI": "rsi",
            "ADX": "adx",
            "MACD_HIST": "macd_hist",
            "MACD Hist": "macd_hist",
            "ATR": "atr",
        }
        return frame.rename(columns=aliases).copy()

    @staticmethod
    def _classify(score: float) -> str:
        if score >= 80:
            return "BULL"
        if score >= 65:
            return "RECOVERY"
        if score >= 45:
            return "SIDEWAYS"
        if score >= 25:
            return "WEAK"
        return "BEAR"

    @staticmethod
    def _confidence(score: float) -> float:
        boundaries = [0, 25, 45, 65, 80, 100]
        distance = min(abs(score - boundary) for boundary in boundaries)
        return min(100.0, 55.0 + distance * 3.0)

    @staticmethod
    def _policy(regime: str) -> dict[str, float | bool]:
        policies = {
            "BULL": {
                "allow_new_positions": True,
                "risk_multiplier": 1.00,
                "max_positions_multiplier": 1.00,
                "cash_target_pct": 15.0,
            },
            "RECOVERY": {
                "allow_new_positions": True,
                "risk_multiplier": 0.80,
                "max_positions_multiplier": 0.80,
                "cash_target_pct": 25.0,
            },
            "SIDEWAYS": {
                "allow_new_positions": True,
                "risk_multiplier": 0.60,
                "max_positions_multiplier": 0.60,
                "cash_target_pct": 40.0,
            },
            "WEAK": {
                "allow_new_positions": True,
                "risk_multiplier": 0.35,
                "max_positions_multiplier": 0.40,
                "cash_target_pct": 60.0,
            },
            "BEAR": {
                "allow_new_positions": False,
                "risk_multiplier": 0.00,
                "max_positions_multiplier": 0.00,
                "cash_target_pct": 85.0,
            },
        }
        return policies[regime]

    @staticmethod
    def _fallback(regime: str, reason: str) -> MarketRegimeResult:
        return MarketRegimeResult(
            regime=regime,
            score=0.0,
            confidence=0.0,
            allow_new_positions=False,
            risk_multiplier=0.0,
            max_positions_multiplier=0.0,
            cash_target_pct=100.0,
            reasons=(reason,),
        )
