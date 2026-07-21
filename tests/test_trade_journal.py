from datetime import datetime, timezone
import csv
import sqlite3
import pytest

from engine.trade_journal import TradeJournal, TradeRecord


def dt(day, hour=12):
    return datetime(2026, 7, day, hour, tzinfo=timezone.utc)


def trade(tid, exit=110, day=1, side="LONG", commission=0, slippage=0, symbol="BTCUSDT"):
    entry = 100
    gross = (exit-entry) if side == "LONG" else (entry-exit)
    return TradeRecord(
        trade_id=tid, symbol=symbol, side=side, quantity=1,
        entry_price=entry, exit_price=exit,
        opened_at=dt(day, 10), closed_at=dt(day, 12),
        gross_pnl=gross, commission=commission,
        slippage_cost=slippage, strategy="alpha"
    )


def test_validation_side():
    with pytest.raises(ValueError):
        trade("1", side="BUY")


def test_validation_quantity():
    item = trade("1")
    item.quantity = 0
    with pytest.raises(ValueError):
        item.__post_init__()


def test_net_pnl():
    assert trade("1", commission=1, slippage=2).net_pnl == 7


def test_return_pct():
    assert trade("1").return_pct == 10


def test_duration():
    assert trade("1").duration_seconds == 7200


def test_results():
    assert trade("1").result == "WIN"
    assert trade("2", exit=90).result == "LOSS"
    assert trade("3", exit=100).result == "BREAKEVEN"


def test_add_duplicate():
    journal = TradeJournal()
    item = trade("1")
    journal.add_trade(item)
    journal.add_trade(item)
    assert len(journal.trades()) == 1


def test_create_long():
    journal = TradeJournal()
    item = journal.create_trade(
        symbol="BTCUSDT", side="LONG", quantity=2,
        entry_price=100, exit_price=120,
        opened_at=dt(1,10), closed_at=dt(1,12)
    )
    assert item.gross_pnl == 40


def test_create_short():
    journal = TradeJournal()
    item = journal.create_trade(
        symbol="BTCUSDT", side="SHORT", quantity=2,
        entry_price=120, exit_price=100,
        opened_at=dt(1,10), closed_at=dt(1,12)
    )
    assert item.gross_pnl == 40


def test_get_missing():
    with pytest.raises(KeyError):
        TradeJournal().get_trade("x")


def test_filters():
    journal = TradeJournal()
    journal.add_trades([trade("1"), trade("2", symbol="ETHUSDT"), trade("3", exit=90)])
    assert len(journal.trades(symbol="ethusdt")) == 1
    assert len(journal.trades(result="LOSS")) == 1
    assert len(journal.trades(strategy="alpha")) == 3


def test_stats_empty():
    assert TradeJournal().stats().trade_count == 0


def test_stats_counts():
    journal = TradeJournal()
    journal.add_trades([trade("1"), trade("2", exit=90), trade("3", exit=100)])
    stats = journal.stats()
    assert (stats.winning_trades, stats.losing_trades, stats.breakeven_trades) == (1,1,1)


def test_win_rate():
    journal = TradeJournal()
    journal.add_trades([trade("1"), trade("2"), trade("3", exit=90)])
    assert journal.stats().win_rate == pytest.approx(200/3)


def test_profit_factor():
    journal = TradeJournal()
    journal.add_trades([trade("1", exit=120), trade("2", exit=90)])
    assert journal.stats().profit_factor == 2


def test_average_win_loss():
    journal = TradeJournal()
    journal.add_trades([trade("1", exit=120), trade("2", exit=110), trade("3", exit=90)])
    stats = journal.stats()
    assert stats.average_win == 15
    assert stats.average_loss == 10


def test_cost_totals():
    journal = TradeJournal()
    journal.add_trade(trade("1", commission=1, slippage=2))
    stats = journal.stats()
    assert stats.total_commission == 1
    assert stats.total_slippage_cost == 2


def test_summaries():
    journal = TradeJournal()
    journal.add_trades([trade("1", day=1), trade("2", day=1), trade("3", day=2)])
    assert len(journal.summarize("daily")) == 2
    assert len(journal.summarize("weekly")) == 1
    assert journal.summarize("monthly")[0].period == "2026-07"


def test_invalid_period():
    journal = TradeJournal()
    journal.add_trade(trade("1"))
    with pytest.raises(ValueError):
        journal.summarize("yearly")


def test_csv(tmp_path):
    journal = TradeJournal()
    journal.add_trade(trade("1"))
    path = journal.export_csv(tmp_path / "trades.csv")
    with path.open(encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["symbol"] == "BTCUSDT"


def test_sqlite_roundtrip(tmp_path):
    journal = TradeJournal()
    journal.add_trade(trade("1"))
    path = journal.export_sqlite(tmp_path / "trades.db")
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM trades").fetchone()[0] == 1
    loaded = TradeJournal.load_sqlite(path)
    assert loaded.get_trade("1").net_pnl == 10


def test_load_missing(tmp_path):
    assert TradeJournal.load_sqlite(tmp_path / "missing.db").trades() == []


def test_dashboard():
    journal = TradeJournal()
    journal.add_trades([trade("1", day=1), trade("2", day=2)])
    data = journal.dashboard()
    assert data["stats"]["trade_count"] == 2
    assert data["latest_trades"][0]["trade_id"] == "2"
