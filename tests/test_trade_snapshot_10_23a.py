from __future__ import annotations

import pytest

from engine.models.trade_snapshot import TradeSnapshot


def build_snapshot() -> TradeSnapshot:
    return TradeSnapshot.open(
        trade_id="trade-001",
        timestamp="2026-07-25T10:00:00+00:00",
        market="kripto",
        universe="Hepsi",
        symbol="btc/usdt",
        decision="net al",
        score=88,
        confidence=76,
        probability=72,
        risk_level="Orta",
        entry_price=100.0,
        stop_loss=96.0,
        take_profit=108.0,
        take_profit2=112.0,
        atr=2.5,
        quantity=10,
        strategy_name="momentum",
        strategy_version="1.0",
        robot_version="10.23A",
        market_regime="TREND",
        entry_reason="Trend ve momentum uyumlu.",
        metadata={"rsi": 54.2},
    )


def test_open_snapshot_normalizes_core_fields() -> None:
    snapshot = build_snapshot()

    assert snapshot.market == "KRIPTO"
    assert snapshot.symbol == "BTC/USDT"
    assert snapshot.decision == "NET AL"
    assert snapshot.status == "OPEN"
    assert snapshot.metadata["rsi"] == 54.2


def test_close_snapshot_calculates_result_without_mutating_original() -> None:
    opened = build_snapshot()
    closed = opened.close(
        exit_price=110.0,
        exit_reason="TARGET_REACHED",
        exit_type="TAKE_PROFIT",
        closed_at="2026-07-25T12:00:00+00:00",
        holding_minutes=120,
    )

    assert opened.status == "OPEN"
    assert opened.exit_price is None
    assert closed.status == "CLOSED"
    assert closed.pnl == pytest.approx(100.0)
    assert closed.pnl_percent == pytest.approx(10.0)
    assert closed.holding_minutes == 120


def test_round_trip_dictionary() -> None:
    original = build_snapshot().with_metadata(adx=31.5)
    restored = TradeSnapshot.from_dict(original.to_dict())

    assert restored == original
    assert restored.metadata["adx"] == 31.5


def test_closed_trade_cannot_be_closed_twice() -> None:
    closed = build_snapshot().close(
        exit_price=105,
        exit_reason="SMART_EXIT",
    )

    with pytest.raises(ValueError, match="zaten kapalı"):
        closed.close(exit_price=106, exit_reason="SECOND_CLOSE")
