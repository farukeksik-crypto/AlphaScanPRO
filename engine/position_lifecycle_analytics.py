from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _flag(value: Any) -> bool:
    try:
        return bool(int(value or 0))
    except (TypeError, ValueError):
        return bool(value)


def _age_minutes(value: Any, now: datetime | None = None) -> float:
    opened = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(opened):
        return 0.0
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return max(0.0, (reference - opened.to_pydatetime()).total_seconds() / 60.0)


def lifecycle_frame(positions: pd.DataFrame | None, now: datetime | None = None) -> pd.DataFrame:
    """Açık pozisyonları yaşam döngüsü ve çıkış yönetimi açısından zenginleştirir."""
    if positions is None or positions.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for _, row in positions.iterrows():
        item = row.to_dict()
        entry = _num(item.get("entry_price"))
        stop = _num(item.get("stop_price"))
        target1 = _num(item.get("target1"))
        target2 = _num(item.get("target2"))
        highest = _num(item.get("highest_price"), entry) or entry
        lowest = _num(item.get("lowest_price"), entry) or entry
        quantity = _num(item.get("quantity"))
        initial_quantity = _num(item.get("initial_quantity"), quantity) or quantity

        mfe_pct = ((highest - entry) / entry * 100.0) if entry > 0 else 0.0
        mae_pct = ((lowest - entry) / entry * 100.0) if entry > 0 else 0.0
        stop_distance_pct = ((entry - stop) / entry * 100.0) if entry > 0 and stop > 0 else 0.0
        target1_distance_pct = ((target1 - entry) / entry * 100.0) if entry > 0 and target1 > 0 else 0.0
        target2_distance_pct = ((target2 - entry) / entry * 100.0) if entry > 0 and target2 > 0 else 0.0
        remaining_pct = quantity / initial_quantity * 100.0 if initial_quantity > 0 else 0.0

        target1_completed = _flag(item.get("target1_completed"))
        break_even_active = _flag(item.get("break_even_active"))
        trailing_active = _flag(item.get("trailing_active"))

        if trailing_active:
            stage = "TRAILING STOP"
            why_open = "Fiyat, aktif trailing stop ile takip ediliyor."
        elif break_even_active:
            stage = "BAŞA BAŞ KORUMA"
            why_open = "Stop başa baş seviyesine taşındı; trend devamı bekleniyor."
        elif target1_completed:
            stage = "HEDEF 1 TAMAMLANDI"
            why_open = "İlk hedef tamamlandı; kalan miktar ikinci hedef/çıkış sinyali için açık."
        elif highest >= target1 > 0:
            stage = "HEDEF 1 GÖRÜLDÜ"
            why_open = "Fiyat ilk hedef bölgesini gördü; yönetim kaydı güncellenmeyi bekliyor."
        elif stop > 0 and lowest <= stop:
            stage = "STOP GÖRÜLDÜ"
            why_open = "Fiyat stop seviyesini gördü; worker çıkış döngüsü kontrol edilmeli."
        else:
            stage = "İLK HEDEF BEKLENİYOR"
            why_open = "Stop veya hedef tetiklenmedi; pozisyon normal izleme aşamasında."

        item.update(
            {
                "holding_minutes": _age_minutes(item.get("opened_at"), now),
                "mfe_pct_live": mfe_pct,
                "mae_pct_live": mae_pct,
                "stop_distance_pct_live": stop_distance_pct,
                "target1_distance_pct": target1_distance_pct,
                "target2_distance_pct": target2_distance_pct,
                "remaining_quantity_pct": remaining_pct,
                "lifecycle_stage": stage,
                "why_still_open": why_open,
                "target1_seen": bool(target1 > 0 and highest >= target1),
                "target2_seen": bool(target2 > 0 and highest >= target2),
                "stop_seen": bool(stop > 0 and lowest <= stop),
                "break_even_active": break_even_active,
                "trailing_active": trailing_active,
                "target1_completed": target1_completed,
            }
        )
        rows.append(item)

    return pd.DataFrame(rows)


def lifecycle_summary(positions: pd.DataFrame | None, now: datetime | None = None) -> dict[str, Any]:
    frame = lifecycle_frame(positions, now=now)
    if frame.empty:
        return {
            "open_positions": 0,
            "target1_completed": 0,
            "break_even_active": 0,
            "trailing_active": 0,
            "average_holding_minutes": 0.0,
            "average_mfe_pct": 0.0,
            "average_mae_pct": 0.0,
        }
    return {
        "open_positions": int(len(frame)),
        "target1_completed": int(frame["target1_completed"].sum()),
        "break_even_active": int(frame["break_even_active"].sum()),
        "trailing_active": int(frame["trailing_active"].sum()),
        "average_holding_minutes": float(frame["holding_minutes"].mean()),
        "average_mfe_pct": float(frame["mfe_pct_live"].mean()),
        "average_mae_pct": float(frame["mae_pct_live"].mean()),
    }
