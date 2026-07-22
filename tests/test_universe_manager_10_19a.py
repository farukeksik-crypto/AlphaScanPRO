from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from engine.universe_manager import UniverseManager


def _manager(tmp_path: Path) -> UniverseManager:
    watchlist = tmp_path / "watchlists.json"
    watchlist.write_text(
        json.dumps(
            {
                "arindirma_0": [
                    {"kod": "BIMAS", "ad": "BİM"},
                    {"kod": "ALBRK", "ad": "Albaraka Türk"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return UniverseManager(
        registry_path=tmp_path / "universe_registry.json",
        change_log_path=tmp_path / "universe_changes.jsonl",
        watchlist_path=watchlist,
    )


def test_bootstrap_imports_legacy_arindirma_zero(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    assert [item["kod"] for item in manager.get_items("arindirma_0")] == ["ALBRK", "BIMAS"]


def test_bootstrap_contains_full_katilim_master(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    items = manager.get_items("Katılım Tüm")
    assert len(items) > 100
    assert any(item["kod"] == "BIMAS" for item in items)


def test_add_symbol_normalizes_code_and_yahoo_symbol(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    item = manager.add_or_update("Arındırma 0", code="  cwene ", name="CW Enerji", arindirma=0)
    assert item["kod"] == "CWENE"
    assert item["sembol"] == "CWENE.IS"
    assert any(row["kod"] == "CWENE" for row in manager.get_items("arindirma_0"))


def test_deactivate_hides_symbol_but_preserves_record(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    assert manager.deactivate("arindirma_0", "BIMAS") is True
    assert not any(row["kod"] == "BIMAS" for row in manager.get_items("arindirma_0"))
    all_items = manager.get_items("arindirma_0", active_only=False)
    preserved = next(row for row in all_items if row["kod"] == "BIMAS")
    assert preserved["active"] is False


def test_readding_inactive_symbol_reactivates_it(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.deactivate("arindirma_0", "BIMAS")
    manager.add_or_update("arindirma_0", code="BIMAS", name="BİM Yeni")
    item = next(row for row in manager.get_items("arindirma_0") if row["kod"] == "BIMAS")
    assert item["active"] is True
    assert item["ad"] == "BİM Yeni"
    assert manager.recent_changes(1)[0]["action"] == "REACTIVATED"


def test_duplicate_add_updates_without_creating_second_record(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.add_or_update("arindirma_0", code="BIMAS", name="BİM Güncel")
    matches = [row for row in manager.get_items("arindirma_0", active_only=False) if row["kod"] == "BIMAS"]
    assert len(matches) == 1
    assert matches[0]["ad"] == "BİM Güncel"


def test_invalid_empty_code_is_rejected(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    try:
        manager.add_or_update("arindirma_0", code="   ")
    except ValueError as exc:
        assert "hisse kodu" in str(exc)
    else:
        raise AssertionError("Boş kod reddedilmeliydi")


def test_katilim_sync_adds_and_deactivates(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    result = manager.synchronize_katilim_master(
        [
            {"kod": "BIMAS", "ad": "BİM"},
            {"kod": "TESTX", "ad": "Test Şirketi"},
        ]
    )
    assert result["added"] == 1
    assert result["deactivated"] > 0
    active_codes = {row["kod"] for row in manager.get_items("katilim_tum")}
    assert active_codes == {"BIMAS", "TESTX"}


def test_summary_reports_active_and_total_counts(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.deactivate("arindirma_0", "BIMAS")
    summary = next(row for row in manager.list_universes() if row.key == "arindirma_0")
    assert summary.active_count == 1
    assert summary.total_count == 2


def test_change_log_is_newest_first(tmp_path: Path) -> None:
    manager = _manager(tmp_path)
    manager.add_or_update("arindirma_0", code="AAA", name="A")
    manager.add_or_update("arindirma_0", code="BBB", name="B")
    changes = manager.recent_changes(2)
    assert [row["symbol"] for row in changes] == ["BBB", "AAA"]
