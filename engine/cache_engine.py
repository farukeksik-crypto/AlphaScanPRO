from __future__ import annotations

import json
from pathlib import Path
import pandas as pd


class CacheEngine:
    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe(value: str) -> str:
        result = value
        for char in ["/", "\\", ":", "=", "^"]:
            result = result.replace(char, "_")
        return result

    def _data_path(self, provider: str, symbol: str, interval: str) -> Path:
        name = f"{provider}__{self._safe(symbol)}__{self._safe(interval)}.pkl"
        return self.base_dir / name

    def _meta_path(self, provider: str, symbol: str, interval: str) -> Path:
        name = f"{provider}__{self._safe(symbol)}__{self._safe(interval)}.json"
        return self.base_dir / name

    def read(self, provider: str, symbol: str, interval: str) -> pd.DataFrame:
        path = self._data_path(provider, symbol, interval)
        if not path.exists():
            return pd.DataFrame()
        try:
            return pd.read_pickle(path)
        except Exception:
            return pd.DataFrame()

    def write(
        self,
        provider: str,
        symbol: str,
        interval: str,
        frame: pd.DataFrame,
    ) -> None:
        if frame is None or frame.empty:
            return

        frame = frame.copy()
        frame = frame[~frame.index.duplicated(keep="last")].sort_index()

        data_path = self._data_path(provider, symbol, interval)
        temp_path = data_path.with_suffix(".tmp")
        frame.to_pickle(temp_path)
        temp_path.replace(data_path)

        meta = {
            "provider": provider,
            "symbol": symbol,
            "interval": interval,
            "rows": int(len(frame)),
            "first_bar": str(frame.index.min()),
            "last_bar": str(frame.index.max()),
        }
        self._meta_path(provider, symbol, interval).write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def status(self) -> pd.DataFrame:
        rows = []
        for path in sorted(self.base_dir.glob("*.json")):
            try:
                rows.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
        return pd.DataFrame(rows)
