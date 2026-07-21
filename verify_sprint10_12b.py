from __future__ import annotations

import py_compile
import subprocess
import sys
from pathlib import Path

FILES = (
    Path("engine/position_management.py"),
    Path("engine/robot_engine.py"),
    Path("tests/test_atr_trailing_engine_10_12b.py"),
)

MARKERS = {
    Path("engine/position_management.py"): (
        "atr_trailing_enabled",
        "atr_trailing_multiplier",
        "trailing_requires_break_even",
        'position.metadata["atr_trailing"]',
    ),
    Path("engine/robot_engine.py"): (
        "atr_trailing_min_pct",
        "atr_trailing_max_pct",
        "stop yalnızca kâr yönünde sıkılaştırıldı",
    ),
}


def main() -> None:
    root = Path(__file__).resolve().parent
    errors: list[str] = []

    for relative in FILES:
        path = root / relative
        if not path.exists():
            errors.append(f"Dosya eksik: {relative}")
            continue
        try:
            py_compile.compile(str(path), doraise=True)
            print(f"[OK] Sözdizimi: {relative}")
        except Exception as exc:
            errors.append(f"Sözdizimi hatası {relative}: {exc}")

    for relative, markers in MARKERS.items():
        path = root / relative
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                errors.append(f"İşaret bulunamadı: {relative} -> {marker}")
        print(f"[OK] İçerik kontrolü: {relative}")

    if errors:
        print("\nSPRINT 10.12B DOĞRULAMA BAŞARISIZ")
        for error in errors:
            print(f"[HATA] {error}")
        raise SystemExit(1)

    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_break_even_engine_10_12a.py",
        "tests/test_atr_trailing_engine_10_12b.py",
        "-q",
    ]
    print("[BİLGİ] İlgili testler çalıştırılıyor...")
    result = subprocess.run(command, cwd=root, check=False)
    if result.returncode != 0:
        print("SPRINT 10.12B DOĞRULAMA BAŞARISIZ")
        raise SystemExit(result.returncode)

    print("\nSPRINT 10.12B DOĞRULAMA BAŞARILI")


if __name__ == "__main__":
    main()
