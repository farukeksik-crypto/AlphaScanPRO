from __future__ import annotations

import py_compile
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "payload"
FILES = (
    Path("engine/smart_exit.py"),
    Path("engine/robot_engine.py"),
    Path("tests/test_smart_exit_engine_10_12d.py"),
)


def main() -> None:
    missing = [str(path) for path in FILES if not (PAYLOAD / path).exists()]
    if missing:
        raise SystemExit("Payload dosyaları eksik: " + ", ".join(missing))

    backup = ROOT / "backups" / (
        "sprint10_12d_" + datetime.now().strftime("%Y%m%d_%H%M%S")
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
    marker = "## Sprint 10.12D - Smart Exit Decision"
    entry = (
        "\n\n## Sprint 10.12D - Smart Exit Decision\n"
        "- HOLD / TRAIL / PARTIAL_EXIT / FULL_EXIT karar katmanı eklendi.\n"
        "- RSI, MACD, EMA20, hacim ve ADX zayıflaması birlikte puanlanıyor.\n"
        "- Break-even, ATR trailing ve TP1 sonrası kâr koruma bağlamı skora katılıyor.\n"
        "- Eski Smart Exit API davranışı geriye dönük uyumlu tutuldu.\n"
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

    print("\nSprint 10.12D uygulandı.")
    print("Şimdi çalıştırın: py -3.13 .\\verify_sprint10_12d.py")


if __name__ == "__main__":
    main()
