from __future__ import annotations

import py_compile
import shutil
from datetime import datetime
from pathlib import Path

SPRINT = "10.12A"
ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "payload"
FILES = (
    Path("engine/position_management.py"),
    Path("engine/robot_engine.py"),
    Path("tests/test_break_even_engine_10_12a.py"),
)


def main() -> None:
    app_file = ROOT / "app.py"
    if not app_file.exists():
        raise SystemExit("[HATA] Paket proje ana klasöründe değil: app.py bulunamadı.")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = ROOT / "backups" / f"sprint10_12a_{stamp}"
    backup_root.mkdir(parents=True, exist_ok=True)
    print(f"[OK] Yedek oluşturuldu: {backup_root}")

    for relative in FILES:
        source = PAYLOAD / relative
        target = ROOT / relative
        if not source.exists():
            raise SystemExit(f"[HATA] Payload dosyası eksik: {source}")
        if target.exists():
            backup = backup_root / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        print(f"[OK] Yazıldı: {relative}")

    changelog = ROOT / "CHANGELOG.md"
    marker = "## Sprint 10.12A — Maliyet Korumalı Break-even"
    entry = f"""\n{marker}\n- Break-even stop seviyesi çift yön komisyon, slipaj ve ek güvenlik tamponunu kapsayacak şekilde hesaplanır.\n- Stop seviyesi hiçbir zaman geriye taşınmaz ve her pozisyonda yalnızca bir kez etkinleşir.\n- Aktivasyon nedeni, eski/yeni stop ve maliyet tamponu robot sistem olaylarına ve pozisyon metadata alanına kaydedilir.\n- Yeni hedefli testler: `tests/test_break_even_engine_10_12a.py`.\n"""
    existing = changelog.read_text(encoding="utf-8") if changelog.exists() else "# AlphaScan PRO Changelog\n"
    if marker not in existing:
        changelog.write_text(existing.rstrip() + "\n" + entry, encoding="utf-8")
        print("[OK] CHANGELOG.md güncellendi.")
    else:
        print("[OK] CHANGELOG.md kaydı zaten mevcut.")

    for relative in FILES:
        if relative.suffix == ".py":
            py_compile.compile(str(ROOT / relative), doraise=True)
            print(f"[OK] Sözdizimi temiz: {relative}")

    print("\nSprint 10.12A uygulandı.")
    print("Şimdi çalıştırın: py -3.13 .\\verify_sprint10_12a.py")


if __name__ == "__main__":
    main()
