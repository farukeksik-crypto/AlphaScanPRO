from __future__ import annotations

import py_compile
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILES = [
    Path("engine/trade_journal_pro.py"),
    Path("engine/robot_engine.py"),
    Path("tests/test_trade_journal_pro_10_13a.py"),
]
TOKENS = {
    Path("engine/trade_journal_pro.py"): [
        "class TradeJournalProEvent",
        "CREATE TABLE IF NOT EXISTS trade_journal_pro",
        "def record_trade_event",
        "def journal_summary",
        "break_even_active",
        "trailing_active",
        "tp_stage",
    ],
    Path("engine/robot_engine.py"): [
        "from engine.trade_journal_pro import",
        "ensure_trade_journal_pro(connection)",
        "TradeJournalProEvent(",
        'event_type="FULL_EXIT"',
        'event_type="PARTIAL_EXIT"',
        "exit_score=smart_exit.score",
    ],
}


def main() -> None:
    for relative in FILES:
        target = ROOT / relative
        if not target.exists():
            raise SystemExit(f"[HATA] Dosya bulunamadı: {relative}")
        py_compile.compile(str(target), doraise=True)
        print(f"[OK] Sözdizimi: {relative}")

    for relative, tokens in TOKENS.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        for token in tokens:
            if token not in text:
                raise SystemExit(f"[HATA] İçerik eksik: {relative} -> {token}")
            print(f"[OK] İçerik: {token}")

    tests = [
        "tests/test_trade_journal_pro_10_13a.py",
        "tests/test_smart_exit_engine_10_12d.py",
        "tests/test_atr_trailing_engine_10_12b.py",
        "tests/test_break_even_engine_10_12a.py",
    ]
    existing = [item for item in tests if (ROOT / item).exists()]
    print("[BİLGİ] İlgili testler çalıştırılıyor...")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *existing, "-q"],
        cwd=ROOT,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit("[HATA] Testler başarısız.")

    print("\nSPRINT 10.13A DOĞRULAMA BAŞARILI")


if __name__ == "__main__":
    main()
