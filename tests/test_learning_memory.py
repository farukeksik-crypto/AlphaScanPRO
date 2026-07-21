from __future__ import annotations

from engine.learning_memory import LearningMemoryEngine


def test_version_creation_and_activation(tmp_path) -> None:
    engine = LearningMemoryEngine(tmp_path / "learning.json")

    first = engine.create_version(
        {"ai_minimum_trade_score": 60},
        source="MANUAL",
        status="CANDIDATE",
        metrics={"expectancy": 8.0, "sample_size": 30},
    )
    active = engine.activate_version(first.version_id)

    assert active.status == "ACTIVE"
    assert engine.get_active_version() is not None
    assert engine.get_active_version().version_id == first.version_id


def test_compare_versions_accepts_improvement(tmp_path) -> None:
    engine = LearningMemoryEngine(tmp_path / "learning.json")

    baseline = engine.create_version(
        {"ai_minimum_trade_score": 60},
        metrics={"expectancy": 10.0, "sample_size": 30},
    )
    candidate = engine.create_version(
        {"ai_minimum_trade_score": 70},
        metrics={"expectancy": 12.0, "sample_size": 30},
        parent_version_id=baseline.version_id,
    )

    decision = engine.compare_versions(
        baseline.version_id,
        candidate.version_id,
        minimum_improvement_pct=10.0,
        minimum_sample_size=20,
    )

    assert decision.accepted is True
    assert decision.action == "ACCEPT"
    assert round(decision.improvement_pct, 6) == 20.0


def test_compare_versions_rejects_low_samples(tmp_path) -> None:
    engine = LearningMemoryEngine(tmp_path / "learning.json")

    baseline = engine.create_version(
        {"adx_threshold": 18},
        metrics={"expectancy": 10.0, "sample_size": 5},
    )
    candidate = engine.create_version(
        {"adx_threshold": 25},
        metrics={"expectancy": 15.0, "sample_size": 7},
    )

    decision = engine.compare_versions(
        baseline.version_id,
        candidate.version_id,
        minimum_sample_size=20,
    )

    assert decision.accepted is False
    assert "yeterli örnek" in decision.reason.lower()


def test_apply_decision_and_rollback(tmp_path) -> None:
    engine = LearningMemoryEngine(tmp_path / "learning.json")

    baseline = engine.create_version(
        {"rsi_min": 42, "rsi_max": 65},
        metrics={"expectancy": 5.0, "sample_size": 40},
    )
    engine.activate_version(baseline.version_id)

    candidate = engine.create_version(
        {"rsi_min": 50, "rsi_max": 60},
        metrics={"expectancy": 7.0, "sample_size": 40},
    )

    decision = engine.compare_versions(
        baseline.version_id,
        candidate.version_id,
        minimum_improvement_pct=10,
    )
    engine.apply_decision(
        decision,
        activate_if_accepted=True,
    )

    assert engine.get_active_version().version_id == candidate.version_id

    rolled_back = engine.rollback()
    assert rolled_back.version_id == baseline.version_id
    assert engine.get_active_version().version_id == baseline.version_id


def test_learning_report_and_export(tmp_path) -> None:
    engine = LearningMemoryEngine(tmp_path / "learning.json")

    version = engine.create_version(
        {"ai_minimum_trade_score": 65},
        note="Test sürümü",
    )
    engine.activate_version(version.version_id)

    report = engine.learning_report()
    output = engine.export_report(tmp_path / "learning_report.json")

    assert report["total_versions"] == 1
    assert report["active_version_id"] == version.version_id
    assert report["total_events"] >= 2
    assert output.exists()
    assert '"total_versions": 1' in output.read_text(encoding="utf-8")
