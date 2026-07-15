from pathlib import Path
import json

BASE_DIR = Path(__file__).resolve().parents[1]
CACHE_DIR = BASE_DIR / "cache"
LOG_DIR = BASE_DIR / "logs"
DATABASE_DIR = BASE_DIR / "database"
WATCHLIST_FILE = BASE_DIR / "config" / "watchlists.json"

CACHE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_FILE = DATABASE_DIR / "alphascan.db"

DIAGNOSTIC_SYMBOLS = {
    "BIMAS": {
        "provider": "yahoo",
        "symbol": "BIMAS.IS",
        "period": "2y",
        "interval": "1d",
    },
    "ALTIN": {
        "provider": "yahoo",
        "symbol": "GC=F",
        "period": "2y",
        "interval": "1d",
    },
    "BTC/USDT": {
        "provider": "binance",
        "symbol": "BTC/USDT",
        "timeframe": "1h",
        "limit": 1000,
    },
}


def load_watchlists() -> dict:
    if not WATCHLIST_FILE.exists():
        return {"arindirma_0": []}
    with WATCHLIST_FILE.open("r", encoding="utf-8") as handle:
        return json.load(handle)
