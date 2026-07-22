from __future__ import annotations

from types import SimpleNamespace

from engine.background_orchestrator import BackgroundOrchestrator


def test_run_bist_scans_all_configured_universes(monkeypatch) -> None:
    orchestrator = object.__new__(BackgroundOrchestrator)
    orchestrator.watchlists = {
        "arindirma_0": [{"kod": "BIMAS"}],
        "Katılım Tüm": [{"kod": "ASELS"}, {"kod": "BIMAS"}],
        "katilim_tum": [{"kod": "ASELS"}, {"kod": "BIMAS"}],
    }
    orchestrator.settings = SimpleNamespace(
        bist_universes=["arindirma_0", "Katılım Tüm"],
        bist_universe="arindirma_0",
        bist=SimpleNamespace(robot_enabled=True),
    )
    orchestrator.data_engine = object()
    orchestrator.logger = SimpleNamespace(warning=lambda *args, **kwargs: None)
    calls = []

    def fake_execute(market, universe, scan_callable, robot_enabled):
        calls.append((market, universe, robot_enabled))
        rows, failures = scan_callable()
        return {"ok": True, "rows": len(rows), "failures": len(failures), "actions": []}

    orchestrator._execute = fake_execute

    def fake_scan(_data_engine, items, workers=4):
        return ([{"Kod": row["kod"]} for row in items], [])

    monkeypatch.setattr("engine.background_orchestrator.scan_yahoo_items", fake_scan)
    result = orchestrator.run_bist()

    assert result["ok"] is True
    assert result["rows"] == 3
    assert [call[1] for call in calls] == ["arindirma_0", "Katılım Tüm"]


def test_run_bist_skips_empty_universe(monkeypatch) -> None:
    orchestrator = object.__new__(BackgroundOrchestrator)
    orchestrator.watchlists = {"arindirma_0": [{"kod": "BIMAS"}]}
    orchestrator.settings = SimpleNamespace(
        bist_universes=["arindirma_0", "Boş Evren"],
        bist_universe="arindirma_0",
        bist=SimpleNamespace(robot_enabled=True),
    )
    orchestrator.data_engine = object()
    orchestrator.logger = SimpleNamespace(warning=lambda *args, **kwargs: None)
    orchestrator._execute = lambda market, universe, scan_callable, robot_enabled: {
        "ok": True,
        "rows": len(scan_callable()[0]),
        "failures": 0,
        "actions": [],
    }
    monkeypatch.setattr(
        "engine.background_orchestrator.scan_yahoo_items",
        lambda _data_engine, items, workers=4: ([{"Kod": row["kod"]} for row in items], []),
    )

    result = orchestrator.run_bist()
    assert result["ok"] is False
    assert result["rows"] == 1
    assert result["universes"][1]["error"] == "Evren boş"
