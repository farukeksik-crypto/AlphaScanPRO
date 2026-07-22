from __future__ import annotations

from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "payload"
FILES = (
    "engine/paper_trading_mode.py",
    "paper_trading_control.py",
    "tests/test_paper_trading_mode_10_17b.py",
)

for relative in FILES:
    source = PAYLOAD / relative
    target = ROOT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    print(f"Uygulandı: {relative}")

print("Sprint 10.17B başarıyla uygulandı.")
print("Başlatma: py -3.13 .\\paper_trading_control.py start")
print("Durum:    py -3.13 .\\paper_trading_control.py status")
