from __future__ import annotations

from types import SimpleNamespace

from engine.decision_trace import build_decision_trace


class FakeRobot:
    def __init__(self, *, enabled=True, open_symbols=()):
        self.config = SimpleNamespace(
            allowed_decisions=("NET AL", "AL ADAY"),
            minimum_score=70.0,
            minimum_confidence=70.0,
            minimum_probability=70.0,
            allowed_risks=("Düşük", "Orta"),
            high_risk_override_enabled=True,
            high_risk_override_min_score=85.0,
            high_risk_override_min_confidence=70.0,
            high_risk_override_min_probability=70.0,
        )
        self.enabled = enabled
        self.open_symbols = set(open_symbols)

    def get_state(self):
        return {"enabled": self.enabled}

    def has_open_position(self, symbol):
        return symbol in self.open_symbols


def row(**overrides):
    values = {
        "Kod": "BTC/USDT",
        "Karar": "NET AL",
        "Puan": 88,
        "Güven": 76,
        "Başarı Göstergesi %": 72,
        "Risk": "Orta",
        "Fiyat": 100,
    }
    values.update(overrides)
    return values


def test_accepts_normal_candidate():
    trace = build_decision_trace(row(), FakeRobot())
    assert trace.accepted is True
    assert trace.reject_reasons == ()
    assert trace.primary_reason == "accepted"


def test_high_risk_override_matches_robot_rules():
    trace = build_decision_trace(row(Risk="Yüksek"), FakeRobot())
    assert trace.accepted is True
    assert trace.high_risk_override is True
    assert "yüksek risk override" in trace.to_text()


def test_rejects_high_risk_when_override_threshold_is_not_met():
    trace = build_decision_trace(row(Risk="Yüksek", Puan=80), FakeRobot())
    assert trace.accepted is False
    assert "risk" in trace.reject_reasons


def test_records_all_rejection_reasons_in_stable_order():
    trace = build_decision_trace(
        row(Kod="", Fiyat=0, Karar="BEKLE", Puan=40, Güven=30, **{"Başarı Göstergesi %": 20}),
        FakeRobot(enabled=False),
    )
    assert trace.reject_reasons == (
        "robot_disabled",
        "invalid_symbol",
        "invalid_price",
        "decision",
        "score",
        "confidence",
        "probability",
    )


def test_open_position_is_reported():
    trace = build_decision_trace(row(), FakeRobot(open_symbols={"BTC/USDT"}))
    assert trace.accepted is False
    assert trace.reject_reasons == ("open_position",)
