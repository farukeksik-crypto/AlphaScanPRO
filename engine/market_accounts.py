from __future__ import annotations

import re
import unicodedata

# Sprint 10.20B — piyasa/evren bazlı bağımsız sanal hesaplar.
# BIST evrenleri birbirinin nakit, pozisyon ve performansını etkilemez.
ACCOUNT_PROFILES = {
    "BIST_MAIN": {
        "account_id": "bist_main",
        "market": "BIST",
        "universe": "Genel",
        "currency": "TRY",
        "starting_balance": 25_000_000.0,
        "label": "BIST Genel (Eski Hesap)",
    },
    "BIST_KATILIM": {
        "account_id": "bist_katilim",
        "market": "BIST",
        "universe": "Katılım Tüm",
        "currency": "TRY",
        "starting_balance": 10_000_000.0,
        "label": "BIST Katılım",
    },
    "BIST_ARINDIRMA0": {
        "account_id": "bist_arindirma0",
        "market": "BIST",
        "universe": "Arındırma 0",
        "currency": "TRY",
        "starting_balance": 10_000_000.0,
        "label": "BIST Arındırma 0",
    },
    "BIST_ALL": {
        "account_id": "bist_all",
        "market": "BIST",
        "universe": "Tüm BIST",
        "currency": "TRY",
        "starting_balance": 25_000_000.0,
        "label": "Tüm BIST",
    },
    "KRIPTO": {
        "account_id": "crypto_main",
        "market": "KRIPTO",
        "universe": "Hepsi",
        "currency": "USDT",
        "starting_balance": 1_000_000.0,
        "label": "Kripto",
    },
    "EMTIA": {
        "account_id": "commodity_main",
        "market": "EMTIA",
        "universe": "Hepsi",
        "currency": "USD",
        "starting_balance": 1_000_000.0,
        "label": "Emtia",
    },
}

# Geriye dönük uyumluluk: Sprint 10.20A testleri ve eski modüller ana piyasa
# profillerine MARKET_ACCOUNTS["BIST"/"KRIPTO"/"EMTIA"] ile erişebilir.
MARKET_ACCOUNTS = {
    **ACCOUNT_PROFILES,
    "BIST": ACCOUNT_PROFILES["BIST_MAIN"],
}



def _ascii_key(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.upper().replace("İ", "I")
    return re.sub(r"[^A-Z0-9]+", " ", text).strip()


def normalize_market(value: str) -> str:
    text = _ascii_key(value)
    if text in {"KRIPTO", "CRYPTO"}:
        return "KRIPTO"
    if text in {"EMTIA", "COMMODITY"}:
        return "EMTIA"
    return "BIST"


def normalize_universe(value: str) -> str:
    text = _ascii_key(value)
    if "ARINDIRMA" in text and ("0" in text or "SIFIR" in text):
        return "ARINDIRMA_0"
    if "KATILIM" in text:
        return "KATILIM_TUM"
    if text in {"TUM BIST", "BIST TUM", "ALL BIST", "BIST ALL"} or (
        "BIST" in text and "TUM" in text
    ):
        return "TUM_BIST"
    return "GENEL"


def account_key_for_context(market: str, universe: str = "") -> str:
    normalized_market = normalize_market(market)
    if normalized_market == "KRIPTO":
        return "KRIPTO"
    if normalized_market == "EMTIA":
        return "EMTIA"

    normalized_universe = normalize_universe(universe)
    if normalized_universe == "ARINDIRMA_0":
        return "BIST_ARINDIRMA0"
    if normalized_universe == "KATILIM_TUM":
        return "BIST_KATILIM"
    if normalized_universe == "TUM_BIST":
        return "BIST_ALL"
    return "BIST_MAIN"


def account_for_context(market: str, universe: str = "") -> dict:
    return dict(ACCOUNT_PROFILES[account_key_for_context(market, universe)])


def account_for_market(value: str) -> dict:
    """Geriye dönük uyumluluk: evren verilmezse ana piyasa hesabını döndürür."""
    return account_for_context(value, "")


def all_account_profiles() -> list[dict]:
    return [dict(profile) for profile in ACCOUNT_PROFILES.values()]
