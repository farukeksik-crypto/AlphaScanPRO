from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any

from engine.trade_journal_pro import ensure_trade_journal_pro


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _probability(meta: dict[str, Any]) -> float | None:
    for key in (
        "probability",
        "success_probability",
        "success_probability_pct",
        "predicted_probability",
        "confidence",
        "confidence_pct",
    ):
        value = _number(meta.get(key))
        if value is None:
            continue
        if 0.0 <= value <= 1.0:
            return value
        if 0.0 <= value <= 100.0:
            return value / 100.0
    return None


def _band(probability: float) -> str:
    lower = min(90, int(probability * 100) // 10 * 10)
    upper = 100 if lower == 90 else lower + 9
    return f"%{lower}-{upper}"


@dataclass(slots=True)
class CalibrationBand:
    band: str
    sample_size: int
    predicted_pct: float
    actual_win_rate_pct: float
    gap_pct: float
    brier_score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ConfidenceCalibrationReport:
    generated_at: str
    lookback_days: int
    minimum_sample: int
    eligible_trade_count: int
    skipped_trade_count: int
    average_predicted_pct: float
    actual_win_rate_pct: float
    mean_absolute_calibration_error_pct: float
    brier_score: float
    status: str
    bands: list[CalibrationBand] = field(default_factory=list)

    @property
    def data_ready(self) -> bool:
        return self.eligible_trade_count >= self.minimum_sample

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "data_ready": self.data_ready}


def build_confidence_calibration_report(
    connection: sqlite3.Connection,
    *,
    lookback_days: int = 90,
    minimum_sample: int = 20,
) -> ConfidenceCalibrationReport:
    if lookback_days <= 0:
        raise ValueError("lookback_days pozitif olmalıdır.")
    if minimum_sample < 5:
        raise ValueError("minimum_sample en az 5 olmalıdır.")

    connection.row_factory = sqlite3.Row
    ensure_trade_journal_pro(connection)
    cutoff = (datetime.now() - timedelta(days=lookback_days)).isoformat(timespec="seconds")
    raw_rows = connection.execute(
        "SELECT net_pnl, metadata_json FROM trade_journal_pro "
        "WHERE closed_at >= ? ORDER BY closed_at",
        (cutoff,),
    ).fetchall()

    observations: list[tuple[float, float]] = []
    skipped = 0
    for raw in raw_rows:
        probability = _probability(_metadata(raw["metadata_json"]))
        pnl = _number(raw["net_pnl"])
        if probability is None or pnl is None:
            skipped += 1
            continue
        observations.append((probability, 1.0 if pnl > 0 else 0.0))

    grouped: dict[str, list[tuple[float, float]]] = {}
    for probability, outcome in observations:
        grouped.setdefault(_band(probability), []).append((probability, outcome))

    bands: list[CalibrationBand] = []
    for name, items in sorted(grouped.items()):
        predicted = sum(item[0] for item in items) / len(items)
        actual = sum(item[1] for item in items) / len(items)
        brier = sum((item[0] - item[1]) ** 2 for item in items) / len(items)
        bands.append(
            CalibrationBand(
                band=name,
                sample_size=len(items),
                predicted_pct=predicted * 100.0,
                actual_win_rate_pct=actual * 100.0,
                gap_pct=(actual - predicted) * 100.0,
                brier_score=brier,
            )
        )

    count = len(observations)
    if count:
        avg_predicted = sum(item[0] for item in observations) / count
        actual_rate = sum(item[1] for item in observations) / count
        brier_score = sum((item[0] - item[1]) ** 2 for item in observations) / count
        weighted_error = sum(
            abs(item.actual_win_rate_pct - item.predicted_pct) * item.sample_size
            for item in bands
        ) / count
    else:
        avg_predicted = actual_rate = brier_score = weighted_error = 0.0

    if count < minimum_sample:
        status = "VERİ BİRİKİYOR"
    elif weighted_error <= 5.0 and brier_score <= 0.25:
        status = "İYİ"
    elif weighted_error <= 12.0 and brier_score <= 0.30:
        status = "ORTA"
    else:
        status = "ZAYIF"

    return ConfidenceCalibrationReport(
        generated_at=datetime.now().isoformat(timespec="seconds"),
        lookback_days=lookback_days,
        minimum_sample=minimum_sample,
        eligible_trade_count=count,
        skipped_trade_count=skipped,
        average_predicted_pct=avg_predicted * 100.0,
        actual_win_rate_pct=actual_rate * 100.0,
        mean_absolute_calibration_error_pct=weighted_error,
        brier_score=brier_score,
        status=status,
        bands=bands,
    )
