from __future__ import annotations

from engine.trade_intelligence import TradeIntelligenceLogger


def test_open_trade_is_logged(tmp_path) -> None:
    logger = TradeIntelligenceLogger(tmp_path / "trades.jsonl")
    trade = logger.open_trade(
        symbol="BTC/USDT",
        market="crypto",
        side="BUY",
        entry_price=100,
        quantity=2,
        entry_reason="AI BUY",
        ai_score=82,
    )

    events = logger.read_events()

    assert trade.status == "OPEN"
    assert len(events) == 1
    assert events[0]["event_type"] == "OPEN"
    assert events[0]["payload"]["symbol"] == "BTC/USDT"


def test_close_trade_calculates_profit(tmp_path) -> None:
    logger = TradeIntelligenceLogger(tmp_path / "trades.jsonl")
    trade = logger.open_trade(
        symbol="THYAO",
        market="bist",
        side="BUY",
        entry_price=100,
        quantity=10,
        entry_reason="NET AL",
        entry_time="2026-07-21T10:00:00+00:00",
    )

    closed = logger.close_trade(
        trade,
        exit_price=110,
        exit_reason="HEDEF",
        exit_time="2026-07-21T11:30:00+00:00",
    )

    assert closed.status == "CLOSED"
    assert closed.pnl == 100
    assert closed.pnl_pct == 10
    assert closed.duration_minutes == 90


def test_short_trade_profit(tmp_path) -> None:
    logger = TradeIntelligenceLogger(tmp_path / "trades.jsonl")
    trade = logger.open_trade(
        symbol="TEST",
        market="paper",
        side="SHORT",
        entry_price=100,
        quantity=5,
        entry_reason="TEST",
    )

    closed = logger.close_trade(
        trade,
        exit_price=90,
        exit_reason="TARGET",
    )

    assert closed.pnl == 50
    assert closed.pnl_pct == 10


def test_latest_and_closed_trade_state(tmp_path) -> None:
    logger = TradeIntelligenceLogger(tmp_path / "trades.jsonl")
    trade = logger.open_trade(
        symbol="XAUUSD",
        market="commodity",
        side="BUY",
        entry_price=2000,
        quantity=1,
        entry_reason="TREND",
    )
    logger.close_trade(
        trade,
        exit_price=2025,
        exit_reason="TRAILING STOP",
    )

    latest = logger.latest_trade_state(trade.trade_id)
    closed = logger.closed_trades()

    assert latest is not None
    assert latest["status"] == "CLOSED"
    assert len(closed) == 1
