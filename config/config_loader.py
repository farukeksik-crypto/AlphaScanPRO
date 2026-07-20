from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


BASE_DIR = Path(__file__).resolve().parent
TECHNICAL_SCORE_FILE = BASE_DIR / "technical_score.yaml"


DEFAULT_CONFIG: dict[str, Any] = {
    "technical_score": {
        "maximum_score": 100,
        "trend": {
            "ema50_above_ema200": {
                "enabled": True,
                "points": 24,
                "description": "EMA50 > EMA200",
            },
            "price_above_ema50": {
                "enabled": True,
                "points": 14,
                "description": "Fiyat EMA50 üstünde",
            },
            "ema20_above_ema50": {
                "enabled": True,
                "points": 10,
                "description": "Kısa trend güçlü",
            },
        },
        "momentum": {
            "rsi_optimal": {
                "enabled": True,
                "points": 16,
                "minimum": 42,
                "maximum": 65,
                "description": "RSI uygun",
            },
            "macd_positive": {
                "enabled": True,
                "points": 14,
                "description": "MACD pozitif",
            },
        },
        "trend_strength": {
            "adx_confirmation": {
                "enabled": True,
                "points": 12,
                "minimum_adx": 18,
                "require_positive_di": True,
                "description": "ADX yön onayı",
            }
        },
        "volume": {
            "volume_confirmation": {
                "enabled": True,
                "points": 10,
                "minimum_ratio": 0.85,
                "description": "Hacim yeterli",
            }
        },
    },
    "decision_levels": {
        "net_al": {
            "minimum_score": 80,
            "label": "NET AL",
        },
        "al_aday": {
            "minimum_score": 65,
            "label": "AL ADAY",
        },
        "izle": {
            "minimum_score": 50,
            "label": "İZLE",
        },
        "bekle": {
            "minimum_score": 0,
            "label": "BEKLE",
        },
    },
    "independent_modules": {
        "financial_score_affects_technical_score": False,
        "participation_status_affects_technical_score": False,
        "purification_rate_affects_technical_score": False,
        "news_score_affects_technical_score": False,
    },
}


def _deep_merge(
    base: dict[str, Any],
    override: dict[str, Any],
) -> dict[str, Any]:
    """
    Varsayılan ayarlar ile YAML dosyasındaki ayarları birleştirir.

    YAML dosyasında eksik bir alan varsa varsayılan değer korunur.
    """

    result = deepcopy(base)

    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value

    return result


def load_technical_score_config() -> dict[str, Any]:
    """
    technical_score.yaml dosyasını okur.

    Dosya bulunamazsa veya okunamazsa sistemin durmaması için
    varsayılan ayarlar döndürülür.
    """

    if not TECHNICAL_SCORE_FILE.exists():
        return deepcopy(DEFAULT_CONFIG)

    try:
        with TECHNICAL_SCORE_FILE.open(
            "r",
            encoding="utf-8",
        ) as file:
            loaded_config = yaml.safe_load(file) or {}

        if not isinstance(loaded_config, dict):
            return deepcopy(DEFAULT_CONFIG)

        return _deep_merge(
            DEFAULT_CONFIG,
            loaded_config,
        )

    except (OSError, yaml.YAMLError):
        return deepcopy(DEFAULT_CONFIG)


def get_technical_score_settings() -> dict[str, Any]:
    config = load_technical_score_config()
    return config["technical_score"]


def get_decision_levels() -> dict[str, Any]:
    config = load_technical_score_config()
    return config["decision_levels"]


def get_independent_module_settings() -> dict[str, bool]:
    config = load_technical_score_config()
    settings = config["independent_modules"]

    return {
        key: bool(value)
        for key, value in settings.items()
    }


def validate_independent_modules() -> bool:
    """
    Teknik puanı etkilememesi gereken dış modülleri kontrol eder.

    Tüm değerler False ise True döndürür.
    """

    settings = get_independent_module_settings()
    return not any(settings.values())