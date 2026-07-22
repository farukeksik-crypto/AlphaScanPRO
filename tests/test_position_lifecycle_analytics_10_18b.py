from datetime import datetime, timezone

import pandas as pd

from engine.position_lifecycle_analytics import lifecycle_frame, lifecycle_summary


def _positions():
    return pd.DataFrame([
        {
            "symbol": "SUI", "quantity": 50, "initial_quantity": 100,
            "entry_price": 10, "stop_price": 9, "target1": 11, "target2": 12,
            "opened_at": "2026-07-22T10:00:00+00:00", "highest_price": 11.2,
            "lowest_price": 9.7, "target1_completed": 1,
            "break_even_active": 1, "trailing_active": 1,
        },
        {
            "symbol": "LTC", "quantity": 10, "initial_quantity": 10,
            "entry_price": 100, "stop_price": 95, "target1": 105, "target2": 110,
            "opened_at": "2026-07-22T11:00:00+00:00", "highest_price": 103,
            "lowest_price": 97, "target1_completed": 0,
            "break_even_active": 0, "trailing_active": 0,
        },
    ])


def test_lifecycle_frame_calculates_live_metrics():
    frame = lifecycle_frame(_positions(), now=datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc))
    sui = frame[frame.symbol == "SUI"].iloc[0]
    assert sui["holding_minutes"] == 120
    assert round(sui["mfe_pct_live"], 2) == 12.0
    assert round(sui["mae_pct_live"], 2) == -3.0
    assert sui["remaining_quantity_pct"] == 50.0
    assert sui["lifecycle_stage"] == "TRAILING STOP"
    assert bool(sui["target1_seen"]) is True


def test_normal_open_position_explains_why_open():
    frame = lifecycle_frame(_positions(), now=datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc))
    ltc = frame[frame.symbol == "LTC"].iloc[0]
    assert ltc["lifecycle_stage"] == "İLK HEDEF BEKLENİYOR"
    assert "normal izleme" in ltc["why_still_open"]


def test_summary_counts_management_flags():
    summary = lifecycle_summary(_positions(), now=datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc))
    assert summary["open_positions"] == 2
    assert summary["target1_completed"] == 1
    assert summary["break_even_active"] == 1
    assert summary["trailing_active"] == 1
    assert summary["average_holding_minutes"] == 90


def test_empty_input_is_safe():
    assert lifecycle_frame(pd.DataFrame()).empty
    assert lifecycle_summary(None)["open_positions"] == 0
