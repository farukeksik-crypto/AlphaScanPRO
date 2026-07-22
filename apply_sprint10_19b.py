from __future__ import annotations
from datetime import datetime
from pathlib import Path
import shutil

FILES = [
    "engine/universe_performance.py",
    "ui/universe_manager_page.py",
    "tests/test_universe_performance_10_19b.py",
]

def main() -> int:
    project = Path.cwd()
    payload = Path(__file__).resolve().parent / "payload"
    if not (project / "app.py").exists():
        raise RuntimeError("Bu komut AlphaScanPRO_Git_Temiz proje klasöründe çalıştırılmalıdır.")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = project / "backups" / f"sprint10_19b_{stamp}"
    for relative in FILES:
        source, target = payload / relative, project / relative
        if not source.exists():
            raise RuntimeError(f"Paket dosyası eksik: {relative}")
        if target.exists():
            backup = backup_root / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    print("Sprint 10.19B uygulandı: Evren Performans Merkezi eklendi.")
    print(f"Yedek: {backup_root}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
