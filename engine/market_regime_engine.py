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
    volatility_level: str = "UNKNOWN"
    volatility_pct: float = 0.0
    trend_strength: float = 0.0
    momentum_score: float = 0.0
    liquidity_score: float = 0.0
    recommendation: str = "VERİ BEKLE"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["reasons"] = list(self.reasons)
        return data


class MarketRegimeEngine:
    """Piyasa rejimini trend, momentum, volatilite ve likidite ile sınıflandırır.

    ``analyze`` eski indikatörlü veri çerçevesiyle geriye dönük uyumludur.
    ``analyze_market_data`` ham OHLCV verisinden gerekli indikatörleri üretir.
    """

    REQUIRED_COLUMNS = {"close", "ema20", "ema50", "ema200", "rsi", "adx", "macd_hist", "atr"}

    def analyze_market_data(self, frame: pd.DataFrame) -> MarketRegimeResult:
        prepared = self.prepare_market_data(frame)
        return self.analyze(prepared)

    def prepare_market_data(self, frame: pd.DataFrame | None) -> pd.DataFrame:
        if frame is None or frame.empty:
            return pd.DataFrame()
        data = self._normalize_columns(frame)
        if "close" not in data.columns:
            return pd.DataFrame()

        close = pd.to_numeric(data["close"], errors="coerce")
        high = pd.to_numeric(data.get("high", close), errors="coerce")
        low = pd.to_numeric(data.get("low", close), errors="coerce")
        volume = pd.to_numeric(data.get("volume", pd.Series(index=data.index, dtype=float)), errors="coerce")

        data["close"] = close
        data["ema20"] = close.ewm(span=20, adjust=False).mean()
        data["ema50"] = close.ewm(span=50, adjust=False).mean()
        data["ema200"] = close.ewm(span=200, adjust=False).mean()
        data["rsi"] = self._rsi(close, 14)
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        data["macd_hist"] = macd - macd.ewm(span=9, adjust=False).mean()
        data["atr"] = self._atr(high, low, close, 14)
        data["adx"] = self._adx(high, low, close, 14)
        data["volume"] = volume
        data["volume_ma20"] = volume.rolling(20, min_periods=5).mean()
        return data

    def analyze(self, frame: pd.DataFrame) -> MarketRegimeResult:
        if frame is None or frame.empty:
            return self._fallback("YETERSİZ VERİ", "Piyasa verisi bulunamadı.")

        normalized = self._normalize_columns(frame)
        missing = self.REQUIRED_COLUMNS.difference(normalized.columns)
        if missing:
            return self._fallback("YETERSİZ VERİ", "Eksik kolonlar: " + ", ".join(sorted(missing)))

        clean = normalized.replace([np.inf, -np.inf], np.nan).dropna(subset=list(self.REQUIRED_COLUMNS))
        if len(clean) < 20:
            return self._fallback("YETERSİZ VERİ", f"En az 20 geçerli mum gerekli; mevcut={len(clean)}.")

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

        ema20_slope_pct = ((ema20 / float(previous["ema20"]) - 1.0) * 100.0) if float(previous["ema20"]) else 0.0
        atr_pct = atr / close * 100.0 if close > 0 else 0.0
        volatility_level = self._volatility_level(atr_pct)
        liquidity_score = self._liquidity_score(clean)

        score = 0.0
        reasons: list[str] = []
        if ema50 > ema200:
            score += 22; reasons.append("EMA50, EMA200 üzerinde.")
        else:
            reasons.append("EMA50, EMA200 altında.")
        if close > ema50:
            score += 14; reasons.append("Fiyat EMA50 üzerinde.")
        else:
            reasons.append("Fiyat EMA50 altında.")
        if ema20 > ema50:
            score += 10; reasons.append("EMA20, EMA50 üzerinde.")
        if ema20_slope_pct > 0.25:
            score += 12; reasons.append("EMA20 eğimi güçlü pozitif.")
        elif ema20_slope_pct > 0:
            score += 6; reasons.append("EMA20 eğimi pozitif.")
        else:
            reasons.append("EMA20 eğimi negatif.")
        if 50 <= rsi <= 68:
            score += 14; reasons.append("RSI yükseliş bölgesinde.")
        elif 42 <= rsi < 50:
            score += 7; reasons.append("RSI toparlanma bölgesinde.")
        elif rsi < 35:
            reasons.append("RSI zayıf bölgede.")
        if macd_hist > 0:
            score += 12; reasons.append("MACD histogram pozitif.")
        else:
            reasons.append("MACD histogram negatif.")
        if adx >= 25:
            score += 10; reasons.append("ADX güçlü trend gösteriyor.")
        elif adx >= 18:
            score += 6; reasons.append("ADX kabul edilebilir trend gösteriyor.")
        else:
            reasons.append("ADX trend gücü düşük.")
        if atr_pct <= 2.5:
            score += 6; reasons.append("Volatilite kontrollü.")
        elif atr_pct >= 5.0:
            score -= 8; reasons.append("Volatilite yüksek.")

        score = max(0.0, min(100.0, score))
        regime = self._classify(score)
        confidence = self._confidence(score, adx, liquidity_score)
        policy = self._policy(regime, volatility_level)
        momentum_score = self._momentum_score(rsi, macd_hist, ema20_slope_pct)
        trend_strength = max(0.0, min(100.0, adx * 2.5))
        recommendation = self._recommendation(regime, volatility_level, confidence)

        return MarketRegimeResult(
            regime=regime,
            score=round(score, 2),
            confidence=round(confidence, 2),
            allow_new_positions=bool(policy["allow_new_positions"]),
            risk_multiplier=float(policy["risk_multiplier"]),
            max_positions_multiplier=float(policy["max_positions_multiplier"]),
            cash_target_pct=float(policy["cash_target_pct"]),
            reasons=tuple(reasons),
            volatility_level=volatility_level,
            volatility_pct=round(atr_pct, 2),
            trend_strength=round(trend_strength, 2),
            momentum_score=round(momentum_score, 2),
            liquidity_score=round(liquidity_score, 2),
            recommendation=recommendation,
        )

    @staticmethod
    def _normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
        aliases = {
            "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume",
            "EMA20": "ema20", "EMA50": "ema50", "EMA200": "ema200", "RSI": "rsi", "ADX": "adx",
            "MACD_HIST": "macd_hist", "MACD Hist": "macd_hist", "ATR": "atr",
        }
        return frame.rename(columns=aliases).copy()

    @staticmethod
    def _rsi(close: pd.Series, length: int) -> pd.Series:
        delta = close.diff(); gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
        avg_loss = loss.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int) -> pd.Series:
        previous = close.shift(1)
        tr = pd.concat([(high-low).abs(), (high-previous).abs(), (low-previous).abs()], axis=1).max(axis=1)
        return tr.ewm(alpha=1/length, adjust=False, min_periods=length).mean()

    @staticmethod
    def _adx(high: pd.Series, low: pd.Series, close: pd.Series, length: int) -> pd.Series:
        up = high.diff(); down = -low.diff()
        plus_dm = up.where((up > down) & (up > 0), 0.0)
        minus_dm = down.where((down > up) & (down > 0), 0.0)
        atr = MarketRegimeEngine._atr(high, low, close, length).replace(0, np.nan)
        plus_di = 100 * plus_dm.ewm(alpha=1/length, adjust=False).mean() / atr
        minus_di = 100 * minus_dm.ewm(alpha=1/length, adjust=False).mean() / atr
        dx = ((plus_di-minus_di).abs() / (plus_di+minus_di).replace(0, np.nan)) * 100
        return dx.ewm(alpha=1/length, adjust=False, min_periods=length).mean()

    @staticmethod
    def _liquidity_score(frame: pd.DataFrame) -> float:
        if "volume" not in frame.columns:
            return 50.0
        volume = pd.to_numeric(frame["volume"], errors="coerce").dropna()
        if len(volume) < 5 or float(volume.tail(20).mean()) <= 0:
            return 25.0
        baseline = float(volume.tail(20).mean())
        recent = float(volume.tail(5).mean())
        return max(0.0, min(100.0, 50.0 + (recent / baseline - 1.0) * 50.0))

    @staticmethod
    def _momentum_score(rsi: float, macd_hist: float, slope_pct: float) -> float:
        rsi_part = max(0.0, min(100.0, (rsi - 30.0) / 40.0 * 100.0))
        macd_part = 70.0 if macd_hist > 0 else 30.0
        slope_part = max(0.0, min(100.0, 50.0 + slope_pct * 100.0))
        return rsi_part * 0.45 + macd_part * 0.30 + slope_part * 0.25

    @staticmethod
    def _volatility_level(atr_pct: float) -> str:
        if atr_pct < 1.5: return "LOW"
        if atr_pct < 3.5: return "MEDIUM"
        if atr_pct < 5.0: return "HIGH"
        return "EXTREME"

    @staticmethod
    def _classify(score: float) -> str:
        if score >= 80: return "BULL"
        if score >= 65: return "RECOVERY"
        if score >= 45: return "SIDEWAYS"
        if score >= 25: return "WEAK"
        return "BEAR"

    @staticmethod
    def _confidence(score: float, adx: float = 0.0, liquidity_score: float = 50.0) -> float:
        boundaries = [0, 25, 45, 65, 80, 100]
        distance = min(abs(score - boundary) for boundary in boundaries)
        base = min(90.0, 50.0 + distance * 2.5)
        quality = min(10.0, max(0.0, adx - 15.0) * 0.35 + max(0.0, liquidity_score - 50.0) * 0.08)
        return min(100.0, base + quality)

    @staticmethod
    def _policy(regime: str, volatility_level: str = "MEDIUM") -> dict[str, float | bool]:
        policies = {
            "BULL": (True, 1.00, 1.00, 15.0), "RECOVERY": (True, 0.80, 0.80, 25.0),
            "SIDEWAYS": (True, 0.60, 0.60, 40.0), "WEAK": (True, 0.35, 0.40, 60.0),
            "BEAR": (False, 0.00, 0.00, 85.0),
        }
        allow, risk, positions, cash = policies[regime]
        if volatility_level == "HIGH": risk *= 0.75; positions *= 0.80
        elif volatility_level == "EXTREME": risk *= 0.40; positions *= 0.50; cash = max(cash, 70.0)
        return {"allow_new_positions": allow, "risk_multiplier": round(risk, 3),
                "max_positions_multiplier": round(positions, 3), "cash_target_pct": cash}

    @staticmethod
    def _recommendation(regime: str, volatility_level: str, confidence: float) -> str:
        if confidence < 55: return "VERİ BEKLE"
        if regime == "BEAR" or volatility_level == "EXTREME": return "SAVUNMACI"
        if regime in {"WEAK", "SIDEWAYS"} or volatility_level == "HIGH": return "TEMKİNLİ"
        return "NORMAL"

    @staticmethod
    def _fallback(regime: str, reason: str) -> MarketRegimeResult:
        return MarketRegimeResult(regime=regime, score=0.0, confidence=0.0, allow_new_positions=False,
            risk_multiplier=0.0, max_positions_multiplier=0.0, cash_target_pct=100.0,
            reasons=(reason,), recommendation="VERİ BEKLE")
