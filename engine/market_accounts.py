from __future__ import annotations

MARKET_ACCOUNTS = {
    "BIST": {"account_id": "bist_main", "currency": "TRY", "starting_balance": 1_000_000.0, "label": "BIST"},
    "KRIPTO": {"account_id": "crypto_main", "currency": "USDT", "starting_balance": 100_000.0, "label": "Kripto"},
    "EMTIA": {"account_id": "commodity_main", "currency": "USD", "starting_balance": 100_000.0, "label": "Emtia"},
}


def normalize_market(value: str) -> str:
    text = str(value or "BIST").strip().upper()
    if text in {"KRİPTO", "CRYPTO"}:
        return "KRIPTO"
    if text in {"EMTİA", "COMMODITY"}:
        return "EMTIA"
    return "BIST" if text not in MARKET_ACCOUNTS else text


def account_for_market(value: str) -> dict:
    return dict(MARKET_ACCOUNTS[normalize_market(value)])
