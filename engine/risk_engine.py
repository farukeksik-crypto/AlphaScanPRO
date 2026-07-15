from __future__ import annotations

from typing import Any


def calculate_risk_levels(price: float, atr_value: float) -> dict[str, Any]:
    """
    ATR kullanarak stop, hedefler ve risk/kazanç oranlarını hesaplar.
    """

    if price <= 0 or atr_value <= 0:
        return {
            "stop": round(price, 4),
            "target1": round(price, 4),
            "target2": round(price, 4),
            "risk_reward1": 0.0,
            "risk_reward2": 0.0,
        }

    stop = price - atr_value * 2
    target1 = price + atr_value * 2
    target2 = price + atr_value * 4

    risk = price - stop
    reward1 = target1 - price
    reward2 = target2 - price

    risk_reward1 = reward1 / risk if risk > 0 else 0.0
    risk_reward2 = reward2 / risk if risk > 0 else 0.0

    return {
        "stop": round(stop, 4),
        "target1": round(target1, 4),
        "target2": round(target2, 4),
        "risk_reward1": round(risk_reward1, 2),
        "risk_reward2": round(risk_reward2, 2),
    }