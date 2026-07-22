from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "payload"
FILES = [
    Path("engine/trade_performance_analytics.py"),
    Path("ui/robot_page.py"),
    Path("tests/test_trade_performance_analytics_10_18a.py"),
]


def main() -> int:
    if not (ROOT / "engine" / "robot_engine.py").exists():
        print("HATA: Paketi AlphaScanPRO_Git_Temiz proje kökünde çalıştırın.")
        return 1
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = ROOT / ".sprint_backups" / f"10_18a_{stamp}"
    for relative in FILES:
        source = PAYLOAD / relative
        target = ROOT / relative
        if not source.exists():
            print(f"HATA: Paket dosyası eksik: {source}")
            return 1
        if target.exists():
            backup_target = backup / relative
            backup_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup_target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        print(f"Uygulandı: {relative}")
    print("Sprint 10.18A Trade Intelligence ve performans analizi başarıyla uygulandı.")
    print("Sonraki komut: py -3.13 .\\verify_sprint10_18a.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
