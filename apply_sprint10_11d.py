from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SPRINT = "10.11D"
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
        fail("Gelişmiş grafik sayfası bulunamadı.")
    if not source_page.exists():
        fail("Paket içeriği eksik: payload\\ui\\advanced_chart_page.py")

    current_text = target_page.read_text(encoding="utf-8")
    required_previous = ["def _build_analysis", "def _render_analysis_panel", "_add_robot_overlays"]
    missing = [item for item in required_previous if item not in current_text]
    if missing:
        fail("Sprint 10.11C ön koşulu eksik: " + ", ".join(missing))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = TARGET / "backups" / f"sprint10_11d_{stamp}"
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
        "\n## Sprint 10.11D — Göstergeler ve Çizim Araçları\n"
        "- EMA20, EMA50 ve EMA200 ayrı ayrı açılıp kapatılabilir hale getirildi.\n"
        "- Bollinger Bands ve otomatik destek/direnç katmanları eklendi.\n"
        "- Hacim, RSI, MACD, ADX/+DI/-DI ve ATR için seçilebilir alt paneller eklendi.\n"
        "- Trend çizgisi, serbest çizgi, dikdörtgen, daire ve şekil silme araçları etkinleştirildi.\n"
        "- Temel görünüm ve analiz görünümü hazır ayarları ile oturum içi gösterge tercihleri eklendi.\n"
        "- Robot işlem katmanı ve açıklamalı 10.11C analiz paneli korundu.\n"
    )
    existing = changelog.read_text(encoding="utf-8") if changelog.exists() else "# CHANGELOG\n"
    if "## Sprint 10.11D — Göstergeler ve Çizim Araçları" not in existing:
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

    print("\nSprint 10.11D uygulandı.")
    print("Şimdi çalıştırın: py -3.13 .\\verify_sprint10_11d.py")


if __name__ == "__main__":
    main()
