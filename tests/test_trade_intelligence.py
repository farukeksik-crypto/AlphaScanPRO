from engine.trade_intelligence import analyze_closed_trade


def test_profitable_trade_produces_metrics():
    result = analyze_closed_trade(
        entry_price=100.0,
        exit_price=108.0,
        quantity=10.0,
        total_profit=77.0,
        opened_at="2026-07-20T10:00:00",
        closed_at="2026-07-20T14:00:00",
        highest_price=110.0,
        lowest_price=98.0,
        stop_price=95.0,
        target_price=110.0,
        technical_score=85.0,
        confidence_score=80.0,
    )

    assert result.profit_pct == 7.7
    assert result.holding_minutes == 240.0
    assert result.mfe_pct == 10.0
    assert result.mae_pct == -2.0
    assert result.risk_reward == 2.0
    assert result.entry_efficiency == 60.0
    assert result.exit_efficiency == 80.0
    assert result.trade_grade in {"A+", "A", "B", "C", "D"}


def test_invalid_entry_price_raises():
    try:
        analyze_closed_trade(
            entry_price=0.0,
            exit_price=10.0,
            quantity=1.0,
            total_profit=0.0,
            opened_at=None,
            closed_at=None,
        )
    except ValueError as exc:
        assert "entry_price" in str(exc)
    else:
        raise AssertionError("ValueError bekleniyordu.")
