from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json

from config.settings import BASE_DIR


BACKGROUND_CONFIG_FILE = BASE_DIR / "config" / "background_config.json"
RUNTIME_DIR = BASE_DIR / "runtime"
BACKGROUND_LOG_DIR = BASE_DIR / "logs" / "background"

RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
BACKGROUND_LOG_DIR.mkdir(parents=True, exist_ok=True)


DEFAULT_COMMODITIES = {
    "Altın": "GC=F",
    "Gümüş": "SI=F",
    "Platin": "PL=F",
    "Paladyum": "PA=F",
    "Bakır": "HG=F",

    "WTI Petrol": "CL=F",
    "Brent Petrol": "BZ=F",
    "Doğalgaz": "NG=F",
    "Kalorifer Yakıtı": "HO=F",
    "RBOB Benzin": "RB=F",

    "Mısır": "ZC=F",
    "Buğday": "ZW=F",
    "Soya Fasulyesi": "ZS=F",
    "Soya Küspesi": "ZM=F",
    "Soya Yağı": "ZL=F",
    "Pirinç": "ZR=F",

    "Kahve": "KC=F",
    "Şeker": "SB=F",
    "Pamuk": "CT=F",
    "Kakao": "CC=F",
    "Portakal Suyu": "OJ=F",

    "Canlı Sığır": "LE=F",
    "Yağsız Domuz": "HE=F",
    "Besi Sığırı": "GF=F",

    "Kereste": "LBS=F",
    "Yulaf": "ZO=F",
}


@dataclass
class MarketJob:
    enabled: bool
    interval_minutes: int
    robot_enabled: bool = True


@dataclass
class BackgroundSettings:
    timezone: str = "Europe/Istanbul"
    loop_seconds: int = 30

    bist: MarketJob = field(
        default_factory=lambda: MarketJob(
            enabled=True,
            interval_minutes=30,
            robot_enabled=True,
        )
    )

    crypto: MarketJob = field(
        default_factory=lambda: MarketJob(
            enabled=True,
            interval_minutes=60,
            robot_enabled=True,
        )
    )

    commodity: MarketJob = field(
        default_factory=lambda: MarketJob(
            enabled=True,
            interval_minutes=240,
            robot_enabled=True,
        )
    )

    bist_universe: str = "arindirma_0"
    # Birden fazla BIST evrenini aynı seans döngüsünde tarar.
    bist_universes: list[str] = field(
        default_factory=lambda: ["arindirma_0", "Katılım Tüm"]
    )
    crypto_group: str = "Hepsi"

    commodities: dict[str, str] = field(
        default_factory=lambda: DEFAULT_COMMODITIES.copy()
    )

    bist_market_start: str = "09:45"
    bist_market_end: str = "18:15"

    max_saved_rows_per_run: int = 500

    # Worker başladığında bildirim/log oluşturur.
    notify_worker_start: bool = False

    # İşlem açılmazsa bildirim oluşturur.
    notify_no_action: bool = False


def _job(payload: dict, default: MarketJob) -> MarketJob:
    return MarketJob(
        enabled=bool(
            payload.get(
                "enabled",
                default.enabled,
            )
        ),
        interval_minutes=max(
            1,
            int(
                payload.get(
                    "interval_minutes",
                    default.interval_minutes,
                )
            ),
        ),
        robot_enabled=bool(
            payload.get(
                "robot_enabled",
                default.robot_enabled,
            )
        ),
    )


def load_background_settings(
    path: Path = BACKGROUND_CONFIG_FILE,
) -> BackgroundSettings:
    defaults = BackgroundSettings()

    if not path.exists():
        save_background_settings(defaults, path)
        return defaults

    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)

    return BackgroundSettings(
        timezone=str(
            raw.get(
                "timezone",
                defaults.timezone,
            )
        ),
        loop_seconds=max(
            10,
            int(
                raw.get(
                    "loop_seconds",
                    defaults.loop_seconds,
                )
            ),
        ),
        bist=_job(
            raw.get("bist", {}),
            defaults.bist,
        ),
        crypto=_job(
            raw.get("crypto", {}),
            defaults.crypto,
        ),
        commodity=_job(
            raw.get("commodity", {}),
            defaults.commodity,
        ),
        bist_universe=str(
            raw.get(
                "bist_universe",
                defaults.bist_universe,
            )
        ),
        bist_universes=[
            str(item)
            for item in raw.get(
                "bist_universes",
                [raw.get("bist_universe", defaults.bist_universe)],
            )
            if str(item).strip()
        ],
        crypto_group=str(
            raw.get(
                "crypto_group",
                defaults.crypto_group,
            )
        ),
        commodities={
            **defaults.commodities,
            **dict(raw.get("commodities", {})),
        },
        bist_market_start=str(
            raw.get(
                "bist_market_start",
                defaults.bist_market_start,
            )
        ),
        bist_market_end=str(
            raw.get(
                "bist_market_end",
                defaults.bist_market_end,
            )
        ),
        max_saved_rows_per_run=max(
            50,
            int(
                raw.get(
                    "max_saved_rows_per_run",
                    defaults.max_saved_rows_per_run,
                )
            ),
        ),
        notify_worker_start=bool(
            raw.get(
                "notify_worker_start",
                defaults.notify_worker_start,
            )
        ),
        notify_no_action=bool(
            raw.get(
                "notify_no_action",
                defaults.notify_no_action,
            )
        ),
    )


def save_background_settings(
    settings: BackgroundSettings,
    path: Path = BACKGROUND_CONFIG_FILE,
) -> None:
    payload = {
        "timezone": settings.timezone,
        "loop_seconds": settings.loop_seconds,
        "bist": vars(settings.bist),
        "crypto": vars(settings.crypto),
        "commodity": vars(settings.commodity),
        "bist_universe": settings.bist_universe,
        "bist_universes": settings.bist_universes,
        "crypto_group": settings.crypto_group,
        "commodities": settings.commodities,
        "bist_market_start": settings.bist_market_start,
        "bist_market_end": settings.bist_market_end,
        "max_saved_rows_per_run": settings.max_saved_rows_per_run,
        "notify_worker_start": settings.notify_worker_start,
        "notify_no_action": settings.notify_no_action,
    }

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open("r", encoding="utf-8-sig") as handle:
        json.dump(
            payload,
            handle,
            ensure_ascii=False,
            indent=2,
        )