from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Iterable

from config.market_universes import get_bist_universe
from config.settings import BASE_DIR, WATCHLIST_FILE


UNIVERSE_REGISTRY_FILE = BASE_DIR / "config" / "universe_registry.json"
UNIVERSE_CHANGE_LOG_FILE = BASE_DIR / "database" / "universe_changes.jsonl"


@dataclass(frozen=True)
class UniverseSummary:
    key: str
    name: str
    active_count: int
    total_count: int
    updated_at: str


class UniverseManager:
    """Kalıcı BIST evrenlerini yönetir.

    Sprint 10.19A'nın amacı listeyi kod içine gömmek yerine tek bir kayıt
    dosyasından yönetmektir. Kayıtlar silinmez; evrenden çıkarılan semboller
    pasif yapılır. Böylece değişiklik geçmişi ve daha önce açılan sanal
    işlemler korunur.
    """

    VERSION = 1
    DISPLAY_NAMES = {
        "arindirma_0": "Arındırma 0",
        "katilim_tum": "Katılım Tüm",
    }
    ALIASES = {
        "arindirma_0": "arindirma_0",
        "Arındırma 0": "arindirma_0",
        "Arindirma 0": "arindirma_0",
        "katilim_tum": "katilim_tum",
        "Katılım Tüm": "katilim_tum",
        "Katilim Tum": "katilim_tum",
    }

    def __init__(
        self,
        registry_path: Path = UNIVERSE_REGISTRY_FILE,
        change_log_path: Path = UNIVERSE_CHANGE_LOG_FILE,
        watchlist_path: Path = WATCHLIST_FILE,
    ) -> None:
        self.registry_path = Path(registry_path)
        self.change_log_path = Path(change_log_path)
        self.watchlist_path = Path(watchlist_path)
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.change_log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.registry_path.exists():
            self._bootstrap()
        else:
            self._ensure_structure()

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    @classmethod
    def normalize_key(cls, value: str) -> str:
        text = str(value or "").strip()
        return cls.ALIASES.get(text, text)

    @staticmethod
    def _normalize_item(item: dict[str, Any], *, active: bool = True) -> dict[str, Any]:
        code = str(item.get("kod") or item.get("code") or "").strip().upper()
        symbol = str(item.get("sembol") or item.get("symbol") or "").strip().upper()
        if not symbol and code:
            symbol = f"{code}.IS"
        name = str(item.get("ad") or item.get("name") or code).strip()
        arindirma = item.get("arindirma")
        return {
            "kod": code,
            "sembol": symbol,
            "ad": name,
            "arindirma": arindirma,
            "active": bool(item.get("active", active)),
            "updated_at": str(item.get("updated_at") or UniverseManager._now()),
        }

    def _read_watchlist_seed(self) -> list[dict[str, Any]]:
        if not self.watchlist_path.exists():
            return []
        try:
            payload = json.loads(self.watchlist_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return [self._normalize_item(item) for item in payload.get("arindirma_0", [])]

    def _bootstrap(self) -> None:
        now = self._now()
        arindirma_items = self._read_watchlist_seed()
        katilim_items = [self._normalize_item(item) for item in get_bist_universe("Katılım Tüm")]
        payload = {
            "version": self.VERSION,
            "updated_at": now,
            "universes": {
                "arindirma_0": {
                    "name": self.DISPLAY_NAMES["arindirma_0"],
                    "source": "legacy_watchlist_seed",
                    "updated_at": now,
                    "items": arindirma_items,
                },
                "katilim_tum": {
                    "name": self.DISPLAY_NAMES["katilim_tum"],
                    "source": "config_market_universes",
                    "updated_at": now,
                    "items": katilim_items,
                },
            },
        }
        self._write(payload)

    def _read(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Evren kayıt dosyası okunamadı: {self.registry_path}") from exc
        return payload

    def _write(self, payload: dict[str, Any]) -> None:
        payload["version"] = self.VERSION
        payload["updated_at"] = self._now()
        temp_path = self.registry_path.with_suffix(self.registry_path.suffix + ".tmp")
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temp_path.replace(self.registry_path)

    def _ensure_structure(self) -> None:
        payload = self._read()
        changed = False
        universes = payload.setdefault("universes", {})
        if "arindirma_0" not in universes:
            universes["arindirma_0"] = {
                "name": self.DISPLAY_NAMES["arindirma_0"],
                "source": "legacy_watchlist_seed",
                "updated_at": self._now(),
                "items": self._read_watchlist_seed(),
            }
            changed = True
        if "katilim_tum" not in universes:
            universes["katilim_tum"] = {
                "name": self.DISPLAY_NAMES["katilim_tum"],
                "source": "config_market_universes",
                "updated_at": self._now(),
                "items": [self._normalize_item(item) for item in get_bist_universe("Katılım Tüm")],
            }
            changed = True
        if changed:
            self._write(payload)

    def _append_change(self, action: str, universe: str, item: dict[str, Any]) -> None:
        record = {
            "created_at": self._now(),
            "action": action,
            "universe": universe,
            "symbol": item.get("kod", ""),
            "name": item.get("ad", ""),
        }
        with self.change_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def list_universes(self) -> list[UniverseSummary]:
        payload = self._read()
        summaries: list[UniverseSummary] = []
        for key, universe in payload.get("universes", {}).items():
            items = list(universe.get("items", []))
            summaries.append(
                UniverseSummary(
                    key=key,
                    name=str(universe.get("name") or self.DISPLAY_NAMES.get(key, key)),
                    active_count=sum(1 for item in items if item.get("active", True)),
                    total_count=len(items),
                    updated_at=str(universe.get("updated_at") or payload.get("updated_at", "")),
                )
            )
        return summaries

    def get_items(self, universe: str, *, active_only: bool = True) -> list[dict[str, Any]]:
        key = self.normalize_key(universe)
        payload = self._read()
        container = payload.get("universes", {}).get(key, {})
        items = [self._normalize_item(item) for item in container.get("items", [])]
        if active_only:
            items = [item for item in items if item.get("active", True)]
        return sorted(items, key=lambda item: item["kod"])

    def add_or_update(
        self,
        universe: str,
        *,
        code: str,
        name: str = "",
        symbol: str = "",
        arindirma: float | None = None,
    ) -> dict[str, Any]:
        key = self.normalize_key(universe)
        code = str(code or "").strip().upper()
        if not code or not code.replace(".", "").replace("-", "").isalnum():
            raise ValueError("Geçerli bir hisse kodu girilmelidir.")
        payload = self._read()
        universes = payload.setdefault("universes", {})
        container = universes.setdefault(
            key,
            {
                "name": self.DISPLAY_NAMES.get(key, key),
                "source": "manual",
                "updated_at": self._now(),
                "items": [],
            },
        )
        items = container.setdefault("items", [])
        existing = next((item for item in items if str(item.get("kod", "")).upper() == code), None)
        new_item = self._normalize_item(
            {
                "kod": code,
                "sembol": symbol or f"{code}.IS",
                "ad": name or (existing or {}).get("ad") or code,
                "arindirma": arindirma,
                "active": True,
                "updated_at": self._now(),
            }
        )
        if existing is None:
            items.append(new_item)
            action = "ADDED"
        else:
            was_active = bool(existing.get("active", True))
            existing.clear()
            existing.update(new_item)
            action = "UPDATED" if was_active else "REACTIVATED"
        container["updated_at"] = self._now()
        self._write(payload)
        self._append_change(action, key, new_item)
        return new_item

    def deactivate(self, universe: str, code: str) -> bool:
        key = self.normalize_key(universe)
        code = str(code or "").strip().upper()
        payload = self._read()
        container = payload.get("universes", {}).get(key)
        if not container:
            return False
        for item in container.get("items", []):
            if str(item.get("kod", "")).upper() == code and item.get("active", True):
                item["active"] = False
                item["updated_at"] = self._now()
                container["updated_at"] = self._now()
                self._write(payload)
                self._append_change("DEACTIVATED", key, item)
                return True
        return False

    def synchronize_katilim_master(self, items: Iterable[dict[str, Any]] | None = None) -> dict[str, int]:
        incoming = list(items if items is not None else get_bist_universe("Katılım Tüm"))
        normalized = {self._normalize_item(item)["kod"]: self._normalize_item(item) for item in incoming}
        payload = self._read()
        container = payload["universes"]["katilim_tum"]
        existing = {str(item.get("kod", "")).upper(): item for item in container.get("items", [])}
        added = reactivated = deactivated = 0
        for code, item in normalized.items():
            if code not in existing:
                container["items"].append(item)
                self._append_change("ADDED", "katilim_tum", item)
                added += 1
            else:
                was_active = existing[code].get("active", True)
                existing[code].update(item)
                existing[code]["active"] = True
                if not was_active:
                    reactivated += 1
                    self._append_change("REACTIVATED", "katilim_tum", existing[code])
        for code, item in existing.items():
            if code not in normalized and item.get("active", True):
                item["active"] = False
                item["updated_at"] = self._now()
                deactivated += 1
                self._append_change("DEACTIVATED", "katilim_tum", item)
        container["updated_at"] = self._now()
        self._write(payload)
        return {"added": added, "reactivated": reactivated, "deactivated": deactivated}

    def recent_changes(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.change_log_path.exists():
            return []
        records: list[dict[str, Any]] = []
        with self.change_log_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return list(reversed(records[-max(1, int(limit)) :]))
