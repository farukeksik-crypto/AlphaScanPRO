from __future__ import annotations

from datetime import datetime

from database.db import Database
from engine.robot_intelligence import build_robot_intelligence_snapshot
from engine.trade_journal_pro import TradeJournalProEvent, record_trade_event


def add_event(connection, symbol, pnl, *, action="FULL_EXIT", be=False, trailing=False, event_type="FULL_EXIT"):
    record_trade_event(connection, TradeJournalProEvent(
        position_id=1, account_id="paper", market="KRIPTO", symbol=symbol,
        event_type=event_type, side="LONG", quantity=1, entry_price=100,
        exit_price=100+pnl, gross_pnl=pnl, commission=0, net_pnl=pnl,
        exit_action=action, closed_at=datetime.now().isoformat(timespec="seconds"),
        holding_minutes=60, break_even_active=be, trailing_active=trailing,
    ))


def test_empty_snapshot(tmp_path):
    db=Database(tmp_path/'a.db')
    with db.connect() as c:
        snap=build_robot_intelligence_snapshot(c)
    assert snap.recent_trade_count == 0
    assert snap.open_position_count == 0
    assert any(a['code']=='NO_RECENT_TRADES' for a in snap.alerts)


def test_metrics_and_rankings(tmp_path):
    db=Database(tmp_path/'a.db')
    with db.connect() as c:
        add_event(c,'BTCUSDT',20,be=True,trailing=True)
        add_event(c,'ETHUSDT',-10)
        add_event(c,'BTCUSDT',5,event_type='PARTIAL_EXIT',action='PARTIAL_EXIT')
        c.commit()
        snap=build_robot_intelligence_snapshot(c)
    assert snap.recent_trade_count == 3
    assert snap.recent_net_pnl == 15
    assert snap.recent_profit_factor == 2.5
    assert snap.best_symbol == 'BTCUSDT'
    assert snap.worst_symbol == 'ETHUSDT'
    assert snap.partial_exit_usage_pct > 0


def test_open_position_market_value(tmp_path):
    db=Database(tmp_path/'a.db')
    with db.connect() as c:
        c.execute("INSERT INTO positions(symbol,quantity,entry_price,opened_at,status) VALUES('BTC',2,100,datetime('now'),'OPEN')")
        c.commit()
        snap=build_robot_intelligence_snapshot(c)
    assert snap.open_position_count == 1
    assert snap.open_market_value == 200


def test_invalid_arguments(tmp_path):
    db=Database(tmp_path/'a.db')
    with db.connect() as c:
        try: build_robot_intelligence_snapshot(c, lookback_days=0)
        except ValueError: pass
        else: raise AssertionError('ValueError bekleniyordu')
