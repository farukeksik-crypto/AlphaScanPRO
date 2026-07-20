from __future__ import annotations

from engine.models.decision import Decision


def test_decision_to_dict_preserves_legacy_keys() -> None:
    decision = Decision(
        ok=True,
        action="NET AL",
        quality="A+",
        score=90.0,
        reason="Test",
        price=100.0,
        stop=95.0,
        target1=105.0,
        target2=110.0,
        risk_reward1=1.0,
        risk_reward2=2.0,
        rsi=55.0,
        adx=25.0,
    )

    result = decision.to_dict()

    assert result["decision"] == "NET AL"
    assert "action" not in result
    assert result["score"] == 90.0
    assert decision.decision == "NET AL"
