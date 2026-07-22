from __future__ import annotations

from database.db import Database
from database.background_migrations import ensure_background_schema
from database.robot_migrations import migrate_database_object
from engine.universe_performance import UniversePerformanceAnalytics


def test_universe_performance_combines_scan_and_trade_data(tmp_path):
    db = Database(tmp_path / "test.db")
    ensure_background_schema(db)
    migrate_database_object(db)
    with db.connect() as con:
        con.execute("INSERT INTO background_runs(market, universe, started_at, finished_at, status, scanned_count, failure_count, action_count) VALUES ('BIST','Arındırma 0',datetime('now'),datetime('now'),'SUCCESS',25,2,3)")
        con.execute("INSERT INTO positions(symbol,quantity,entry_price,opened_at,status,market,universe) VALUES ('AAA',1,10,datetime('now'),'OPEN','BIST','Arındırma 0')")
        con.execute("INSERT INTO trade_history(symbol,side,quantity,price,profit,created_at,market,universe,profit_pct) VALUES ('BBB','SELL',1,12,200,datetime('now'),'BIST','Arındırma 0',2.5)")
        con.commit()
    row = UniversePerformanceAnalytics(db).rows(30)[0]
    assert row.scanned == 25
    assert row.robot_actions == 3
    assert row.open_positions == 1
    assert row.closed_trades == 1
    assert row.win_rate == 100.0
    assert row.net_profit == 200.0


def test_summary_totals_multiple_universes(tmp_path):
    db = Database(tmp_path / "test.db")
    ensure_background_schema(db)
    migrate_database_object(db)
    with db.connect() as con:
        for universe, count in [("Arındırma 0", 25), ("Katılım Tüm", 241)]:
            con.execute("INSERT INTO background_runs(market, universe, started_at, finished_at, status, scanned_count) VALUES ('BIST',?,datetime('now'),datetime('now'),'SUCCESS',?)", (universe, count))
        con.commit()
    summary = UniversePerformanceAnalytics(db).summary(30)
    assert summary["universe_count"] == 2
    assert summary["scanned"] == 266
