from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

SPRINT = "10_17a"
ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "payload"
BACKUP = ROOT / ".sprint_backups" / SPRINT
FILES = (
    Path("engine/production_readiness.py"),
    Path("tests/test_production_readiness_10_17a.py"),
    Path("paper_trading_readiness.py"),
)
IGNORE_LINES = (".sprint_backups/", "payload/")


def main() -> int:
    if not (ROOT / "engine").is_dir() or not (ROOT / "tests").is_dir():
        raise SystemExit("Bu dosyayı AlphaScan PRO proje ana klasöründe çalıştırın.")

    BACKUP.mkdir(parents=True, exist_ok=True)
    for relative in FILES:
        source = PAYLOAD / relative
        target = ROOT / relative
        if not source.exists():
            raise SystemExit(f"Payload dosyası eksik: {source}")
        if target.exists():
            backup_target = BACKUP / relative
            backup_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup_target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        print(f"Uygulandı: {relative}")

    gitignore = ROOT / ".gitignore"
    current = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    additions = [line for line in IGNORE_LINES if line not in current.splitlines()]
    if additions:
        with gitignore.open("a", encoding="utf-8", newline="\n") as handle:
            if current and not current.endswith("\n"):
                handle.write("\n")
            handle.write("\n# Sprint paketleri ve yerel geri dönüş yedekleri\n")
            handle.write("\n".join(additions) + "\n")
        print("Güncellendi: .gitignore")

    marker = BACKUP / "applied_at.txt"
    marker.write_text(datetime.now().isoformat(timespec="seconds"), encoding="utf-8")
    print("Sprint 10.17A başarıyla uygulandı.")
    print("Not: Daha önce Git'e eklenmiş .sprint_backups/ ve payload/ dosyaları otomatik silinmez.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
