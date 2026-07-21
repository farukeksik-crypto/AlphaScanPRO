from __future__ import annotations

import py_compile
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "payload"
FILES = (
    Path("engine/performance_analytics.py"),
    Path("ui/performance_analytics_page.py"),
    Path("app.py"),
    Path("tests/test_performance_analytics_10_13b.py"),
)


def main() -> None:
    missing = [str(path) for path in FILES if not (PAYLOAD / path).exists()]
    if missing:
        raise SystemExit("Payload dosyaları eksik: " + ", ".join(missing))

    backup = ROOT / "backups" / (
        "sprint10_13b_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    )
    backup.mkdir(parents=True, exist_ok=True)

    for relative in FILES:
        target = ROOT / relative
        if target.exists():
            backup_target = backup / relative
            backup_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup_target)
    print(f"[OK] Yedek oluşturuldu: {backup}")

    for relative in FILES:
        source = PAYLOAD / relative
        target = ROOT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        print(f"[OK] Yazıldı: {relative}")

    changelog = ROOT / "CHANGELOG.md"
    marker = "## Sprint 10.13B - Performance Analytics PRO"
    entry = (
        "\n\n## Sprint 10.13B - Performance Analytics PRO\n"
        "- Trade Journal PRO için Win Rate, Profit Factor ve Expectancy eklendi.\n"
        "- Equity Curve, Max Drawdown ve dönemsel PnL hesaplandı.\n"
        "- Sembol, piyasa ve çıkış aksiyonu bazlı performans analizi eklendi.\n"
        "- Streamlit menüsüne Performance Analytics PRO sayfası eklendi.\n"
        "- Eski PerformanceAnalytics API'si geriye dönük uyumlu tutuldu.\n"
    )
    current = changelog.read_text(encoding="utf-8") if changelog.exists() else "# CHANGELOG\n"
    if marker not in current:
        changelog.write_text(current.rstrip() + entry + "\n", encoding="utf-8")
        print("[OK] CHANGELOG.md güncellendi.")
    else:
        print("[BİLGİ] CHANGELOG.md kaydı zaten mevcut.")

    for relative in FILES:
        py_compile.compile(str(ROOT / relative), doraise=True)
        print(f"[OK] Sözdizimi temiz: {relative}")

    print("\nSprint 10.13B uygulandı.")
    print(r"Şimdi çalıştırın: py -3.13 .\verify_sprint10_13b.py")


if __name__ == "__main__":
    main()
