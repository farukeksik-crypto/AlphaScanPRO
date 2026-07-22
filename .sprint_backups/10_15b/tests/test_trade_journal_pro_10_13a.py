from __future__ import annotations

import sqlite3

from engine.trade_journal_pro import (
    TradeJournalProEvent,
    ensure_trade_journal_pro,
    journal_summary,
    record_trade_event,
)


def _event(**overrides):
    values = dict(
        position_id=7,
        account_id="crypto_main",
        market="KRIPTO",
        symbol="BTC/USDT",
        event_type="FULL_EXIT",
        side="LONG",
        quantity=2.0,
        entry_price=100.0,
        exit_price=110.0,
        gross_pnl=20.0,
        commission=1.0,
        net_pnl=19.0,
        entry_score=81.0,
        exit_score=72.0,
        exit_action="FULL_EXIT",
        exit_reason="AKILLI ÇIKIŞ TAM",
        confirmations=3,
        break_even_active=True,
        trailing_active=True,
        tp_stage=1,
        opened_at="2026-07-22T01:00:00",
        closed_at="2026-07-22T02:00:00",
        holding_minutes=60.0,
        mfe_pct=12.0,
        mae_pct=-2.0,
        metadata={"reasons": ["RSI zayıf"]},
    )
    values.update(overrides)
    return TradeJournalProEvent(**values)


def test_schema_is_idempotent():
    connection = sqlite3.connect(":memory:")
    ensure_trade_journal_pro(connection)
    ensure_trade_journal_pro(connection)
    names = {row[1] for row in connection.execute("PRAGMA table_info(trade_journal_pro)")}
    assert {"entry_score", "exit_score", "break_even_active", "tp_stage", "metadata_json"} <= names


def test_record_trade_event_persists_pro_fields():
    connection = sqlite3.connect(":memory:")
    event_id = record_trade_event(connection, _event())
    connection.commit()
    row = connection.execute(
        "SELECT event_type, exit_score, confirmations, break_even_active, trailing_active, tp_stage FROM trade_journal_pro WHERE id=?",
        (event_id,),
    ).fetchone()
    assert row == ("FULL_EXIT", 72.0, 3, 1, 1, 1)


def test_partial_exit_is_recorded_separately():
    connection = sqlite3.connect(":memory:")
    record_trade_event(connection, _event(event_type="PARTIAL_EXIT", exit_action="PARTIAL_EXIT", quantity=0.8))
    record_trade_event(connection, _event(position_id=7, quantity=1.2))
    count = connection.execute("SELECT COUNT(*) FROM trade_journal_pro WHERE position_id=7").fetchone()[0]
    assert count == 2


def test_journal_summary_filters_account():
    connection = sqlite3.connect(":memory:")
    record_trade_event(connection, _event())
    record_trade_event(connection, _event(position_id=8, account_id="bist_main", net_pnl=-5.0, gross_pnl=-4.0))
    summary = journal_summary(connection, account_id="crypto_main")
    assert summary["event_count"] == 1
    assert summary["net_pnl"] == 19.0
    assert summary["win_rate"] == 100.0
    assert summary["break_even_events"] == 1


def test_event_to_dict_does_not_share_metadata():
    event = _event()
    data = event.to_dict()
    data["metadata"]["new"] = True
    assert "new" not in event.metadata
