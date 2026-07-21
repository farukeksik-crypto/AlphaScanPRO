from __future__ import annotations

import py_compile
import shutil
from datetime import datetime
from pathlib import Path

SPRINT = "10.12B"
FILES = (
    Path("engine/position_management.py"),
    Path("engine/robot_engine.py"),
    Path("tests/test_atr_trailing_engine_10_12b.py"),
)


def main() -> None:
    root = Path(__file__).resolve().parent
    payload = root / "payload"
    missing = [str(path) for path in FILES if not (payload / path).exists()]
    if missing:
        raise FileNotFoundError(f"Payload eksik: {', '.join(missing)}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = root / "backups" / f"sprint10_12b_{stamp}"
    backup.mkdir(parents=True, exist_ok=True)

    for relative in FILES:
        target = root / relative
        if target.exists():
            backup_target = backup / relative
            backup_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup_target)
    print(f"[OK] Yedek oluşturuldu: {backup}")

    for relative in FILES:
        source = payload / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        print(f"[OK] Yazıldı: {relative}")

    changelog = root / "CHANGELOG.md"
    note = """

## Sprint 10.12B — ATR Trailing Stop
- ATR tabanlı dinamik takip eden stop eklendi.
- ATR mesafesi minimum ve maksimum yüzde sınırlarıyla güvenli aralıkta tutuldu.
- Trailing stop yalnızca break-even sonrasında devreye giriyor.
- Stop hiçbir zaman geriye taşınmıyor.
- ATR modu, mesafe, eski stop ve yeni stop günlükleniyor.
"""
    existing = changelog.read_text(encoding="utf-8") if changelog.exists() else "# CHANGELOG\n"
    if "## Sprint 10.12B — ATR Trailing Stop" not in existing:
        changelog.write_text(existing.rstrip() + note + "\n", encoding="utf-8")
        print("[OK] CHANGELOG.md güncellendi.")
    else:
        print("[OK] CHANGELOG.md zaten güncel.")

    for relative in FILES:
        py_compile.compile(str(root / relative), doraise=True)
        print(f"[OK] Sözdizimi temiz: {relative}")

    print("\nSprint 10.12B uygulandı.")
    print("Şimdi çalıştırın: py -3.13 .\\verify_sprint10_12b.py")


if __name__ == "__main__":
    main()
