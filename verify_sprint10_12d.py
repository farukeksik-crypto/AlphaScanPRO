from __future__ import annotations

import py_compile
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILES = (
    Path("engine/smart_exit.py"),
    Path("engine/robot_engine.py"),
    Path("tests/test_smart_exit_engine_10_12d.py"),
)
TOKENS = {
    Path("engine/smart_exit.py"): (
        "class SmartExitAction",
        "PARTIAL_EXIT",
        "FULL_EXIT",
        "profit_protection_points",
        "partial_tp_protection_points",
    ),
    Path("engine/robot_engine.py"): (
        "smart_exit_watch_score",
        "smart_exit_full_min_confirmations",
        "SmartExitConfig(",
        "SmartExitAction.FULL_EXIT",
        "break_even_active=break_even_active",
    ),
}


def main() -> None:
    for relative in FILES:
        path = ROOT / relative
        if not path.exists():
            raise SystemExit(f"[HATA] Dosya bulunamadı: {relative}")
        py_compile.compile(str(path), doraise=True)
        print(f"[OK] Sözdizimi: {relative}")

    for relative, tokens in TOKENS.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        for token in tokens:
            if token not in text:
                raise SystemExit(f"[HATA] İçerik eksik: {relative} -> {token}")
            print(f"[OK] İçerik: {token}")

    tests = (
        "tests/test_smart_exit.py",
        "tests/test_smart_exit_engine_10_12d.py",
        "tests/test_break_even_engine_10_12a.py",
        "tests/test_atr_trailing_engine_10_12b.py",
        "tests/test_partial_take_profit_engine_10_12c.py",
    )
    print("[BİLGİ] İlgili testler çalıştırılıyor...")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *tests],
        cwd=ROOT,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)

    print("\nSPRINT 10.12D DOĞRULAMA BAŞARILI")


if __name__ == "__main__":
    main()
