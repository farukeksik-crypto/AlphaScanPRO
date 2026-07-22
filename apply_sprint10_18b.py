from __future__ import annotations
from datetime import datetime
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "payload"
FILES = [
    Path("engine/position_lifecycle_analytics.py"),
    Path("ui/robot_page.py"),
    Path("tests/test_position_lifecycle_analytics_10_18b.py"),
]

def main() -> int:
    if not (ROOT / "engine" / "robot_engine.py").exists():
        print("HATA: Paketi AlphaScanPRO_Git_Temiz proje kökünde çalıştırın.")
        return 1
    if not (ROOT / "engine" / "trade_performance_analytics.py").exists():
        print("HATA: Önce Sprint 10.18A uygulanmalıdır.")
        return 1
    backup = ROOT / ".sprint_backups" / f"10_18b_{datetime.now():%Y%m%d_%H%M%S}"
    for relative in FILES:
        source, target = PAYLOAD / relative, ROOT / relative
        if not source.exists():
            print(f"HATA: Paket dosyası eksik: {source}")
            return 1
        if target.exists():
            destination = backup / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        print(f"Uygulandı: {relative}")
    print("Sprint 10.18B Pozisyon Yaşam Döngüsü başarıyla uygulandı.")
    print("Sonraki komut: py -3.13 .\\verify_sprint10_18b.py")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
