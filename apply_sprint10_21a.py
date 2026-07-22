from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "payload"
BACKUP = ROOT / "backups" / f"sprint10_21a_{datetime.now():%Y%m%d_%H%M%S}"
FILES = [
    "engine/fundamental_quality.py",
    "ui/financial_analysis_page.py",
    "tests/test_fundamental_quality_10_21a.py",
]

for relative in FILES:
    source = PAYLOAD / relative
    target = ROOT / relative
    if not source.exists():
        raise FileNotFoundError(f"Paket dosyası eksik: {source}")
    if target.exists():
        backup = BACKUP / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)

print("Sprint 10.21A uygulandı: Açıklanabilir Finansal Kalite Motoru eklendi.")
print("Bilanço ve Yapay Zekâ Analizi ekranını yenileyerek kontrol edebilirsin.")
print("Robotun mevcut giriş/çıkış kuralları bu sprintte değiştirilmedi.")
