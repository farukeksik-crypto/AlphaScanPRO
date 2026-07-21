from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

PAGE_FILE = Path("ui/advanced_chart_page.py")


def fail(message: str) -> None:
    print(f"[HATA] {message}")
    raise SystemExit(1)


def ensure_project_root(root: Path) -> None:
    required = [root / "app.py", root / "engine", root / "ui", root / "database"]
    missing = [path.name for path in required if not path.exists()]
    if missing:
        fail("Bu dosya AlphaScanPRO proje ana klasöründe çalıştırılmalı. Eksik: " + ", ".join(missing))


def backup(root: Path, paths: list[Path]) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = root / "backups" / f"sprint10_11b_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    for relative in paths:
        source = root / relative
        if source.exists():
            target = backup_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    return backup_dir


def patch_app(app_text: str) -> str:
    old = "render_advanced_chart(data_engine, watchlists)"
    new = "render_advanced_chart(data_engine, watchlists, database)"
    if new in app_text:
        return app_text
    if old not in app_text:
        fail("app.py içinde Sprint 10.11A grafik yönlendirmesi bulunamadı.")
    return app_text.replace(old, new, 1)


def update_changelog(root: Path) -> None:
    changelog = root / "CHANGELOG.md"
    entry = (
        "\n## Sprint 10.11B - Robot İşlemleri Grafik Üzerinde\n"
        "- Robot BUY ve SELL işlemleri gelişmiş grafik üzerine eklendi.\n"
        "- Açık pozisyonların STOP, TP1 ve TP2 seviyeleri gösterildi.\n"
        "- Aynı pozisyona ait giriş ve çıkışlar bağlantı çizgisiyle eşleştirildi.\n"
        "- Hover açıklamalarına işlem nedeni, fiyat ve kâr/zarar bilgileri eklendi.\n"
        "- Seçili sembol için robot işlem özeti ve son 50 işlem tablosu eklendi.\n"
    )
    existing = changelog.read_text(encoding="utf-8") if changelog.exists() else "# AlphaScan PRO Değişiklik Günlüğü\n"
    if "## Sprint 10.11B - Robot İşlemleri Grafik Üzerinde" not in existing:
        changelog.write_text(existing.rstrip() + "\n" + entry, encoding="utf-8")


def main() -> None:
    root = Path.cwd()
    package_root = Path(__file__).resolve().parent
    ensure_project_root(root)

    target_page = root / PAGE_FILE
    if not target_page.exists():
        fail("ui/advanced_chart_page.py bulunamadı. Önce Sprint 10.11A uygulanmalı.")

    backup_dir = backup(root, [Path("app.py"), PAGE_FILE, Path("CHANGELOG.md")])
    print(f"[OK] Yedek oluşturuldu: {backup_dir}")

    payload_page = package_root / "payload" / PAGE_FILE
    if not payload_page.exists():
        fail(f"Paket dosyası eksik: {payload_page}")

    shutil.copy2(payload_page, target_page)
    print(f"[OK] Yazıldı: {PAGE_FILE}")

    app_path = root / "app.py"
    app_path.write_text(patch_app(app_path.read_text(encoding="utf-8")), encoding="utf-8")
    print("[OK] app.py veritabanı bağlantısı güncellendi.")

    update_changelog(root)
    print("[OK] CHANGELOG.md güncellendi.")

    print("\nSprint 10.11B uygulandı.")
    print("Şimdi çalıştırın: py -3.13 .\\verify_sprint10_11b.py")


if __name__ == "__main__":
    main()
