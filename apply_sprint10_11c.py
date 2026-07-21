from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SPRINT = "10.11C"
ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "payload"
TARGET = ROOT


def ok(message: str) -> None:
    print(f"[OK] {message}")


def fail(message: str) -> None:
    print(f"[HATA] {message}")
    raise SystemExit(1)


def main() -> None:
    app_file = TARGET / "app.py"
    source_page = PAYLOAD / "ui" / "advanced_chart_page.py"
    target_page = TARGET / "ui" / "advanced_chart_page.py"

    if not app_file.exists():
        fail("app.py bulunamadı. Paket proje ana klasöründe çalıştırılmalı.")
    if not target_page.exists():
        fail("Sprint 10.11A/10.11B gelişmiş grafik sayfası bulunamadı.")
    if not source_page.exists():
        fail("Paket içeriği eksik: payload\\ui\\advanced_chart_page.py")

    current_text = target_page.read_text(encoding="utf-8")
    required_previous = ["_load_robot_overlay", "_add_robot_overlays", "Robot işlemlerini grafikte göster"]
    missing = [item for item in required_previous if item not in current_text]
    if missing:
        fail("Sprint 10.11B ön koşulu eksik: " + ", ".join(missing))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = TARGET / "backups" / f"sprint10_11c_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target_page, backup_dir / "advanced_chart_page.py")
    changelog = TARGET / "CHANGELOG.md"
    if changelog.exists():
        shutil.copy2(changelog, backup_dir / "CHANGELOG.md")
    ok(f"Yedek oluşturuldu: {backup_dir}")

    target_page.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_page, target_page)
    ok("Yazıldı: ui\\advanced_chart_page.py")

    changelog_entry = (
        "\n## Sprint 10.11C — Grafik Analiz Paneli\n"
        "- Açıklamalı 100 puanlık teknik analiz paneli eklendi.\n"
        "- Trend, RSI, MACD, ADX/yön, hacim, momentum ve destek/direnç ayrı gerekçelerle değerlendiriliyor.\n"
        "- NET AL / AL ADAY / İZLE / BEKLE kararı ve her puanın nedeni gösteriliyor.\n"
        "- Streamlit use_container_width uyarıları bu sayfada width='stretch' kullanımına geçirildi.\n"
    )
    existing = changelog.read_text(encoding="utf-8") if changelog.exists() else "# CHANGELOG\n"
    if "## Sprint 10.11C — Grafik Analiz Paneli" not in existing:
        changelog.write_text(existing.rstrip() + "\n" + changelog_entry, encoding="utf-8")
        ok("CHANGELOG.md güncellendi.")
    else:
        ok("CHANGELOG.md kaydı zaten mevcut.")

    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(target_page)],
        cwd=TARGET,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        fail("Sözdizimi kontrolü başarısız:\n" + (result.stderr or result.stdout))
    ok("Sözdizimi temiz: ui\\advanced_chart_page.py")

    print("\nSprint 10.11C uygulandı.")
    print("Şimdi çalıştırın: py -3.13 .\\verify_sprint10_11c.py")


if __name__ == "__main__":
    main()
