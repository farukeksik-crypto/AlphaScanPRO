from __future__ import annotations

import py_compile
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "payload"
FILES = [
    Path("engine/trade_journal_pro.py"),
    Path("engine/robot_engine.py"),
    Path("tests/test_trade_journal_pro_10_13a.py"),
]


def main() -> None:
    for required in (ROOT / "engine", ROOT / "tests", PAYLOAD):
        if not required.exists():
            raise SystemExit(f"[HATA] Gerekli yol bulunamadı: {required}")

    backup = ROOT / "backups" / f"sprint10_13a_{datetime.now():%Y%m%d_%H%M%S}"
    backup.mkdir(parents=True, exist_ok=True)
    print(f"[OK] Yedek oluşturuldu: {backup}")

    for relative in FILES:
        source = PAYLOAD / relative
        target = ROOT / relative
        if not source.exists():
            raise SystemExit(f"[HATA] Paket dosyası bulunamadı: {source}")
        if target.exists():
            destination = backup / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        print(f"[OK] Yazıldı: {relative}")

    changelog = ROOT / "CHANGELOG.md"
    note = """

## Sprint 10.13A - Trade Journal PRO
- Ayrıntılı işlem olay günlüğü eklendi.
- Tam ve kısmi çıkışlar ayrı kayıtlanıyor.
- Giriş/çıkış puanı, Smart Exit kararı ve onay sayısı tutuluyor.
- Break-even, ATR trailing ve TP aşaması kaydediliyor.
- MFE, MAE, işlem süresi ve metadata saklanıyor.
- Hesap bazlı özet metriği eklendi.
"""
    current = changelog.read_text(encoding="utf-8") if changelog.exists() else "# CHANGELOG\n"
    if "## Sprint 10.13A - Trade Journal PRO" not in current:
        changelog.write_text(current.rstrip() + note + "\n", encoding="utf-8")
        print("[OK] CHANGELOG.md güncellendi.")

    for relative in FILES:
        py_compile.compile(str(ROOT / relative), doraise=True)
        print(f"[OK] Sözdizimi temiz: {relative}")

    print("\nSprint 10.13A uygulandı.")
    print("Şimdi çalıştırın: py -3.13 .\\verify_sprint10_13a.py")


if __name__ == "__main__":
    main()
