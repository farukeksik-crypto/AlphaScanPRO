from __future__ import annotations

from datetime import datetime
from pathlib import Path
import shutil
import sys


SPRINT = "10.19A"
FILES = [
    "app.py",
    "background_worker.py",
    "config/background_settings.py",
    "engine/background_orchestrator.py",
    "engine/universe_manager.py",
    "ui/universe_manager_page.py",
    "tests/test_universe_manager_10_19a.py",
    "tests/test_background_multi_universe_10_19a.py",
]


def main() -> int:
    project = Path.cwd()
    payload = Path(__file__).resolve().parent / "payload"
    required = project / "app.py"
    if not required.exists():
        raise RuntimeError(
            "Bu komut AlphaScanPRO_Git_Temiz proje klasöründe çalıştırılmalıdır."
        )
    if not payload.exists():
        raise RuntimeError("Sprint payload klasörü bulunamadı.")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = project / "backups" / f"sprint10_19a_{stamp}"
    copied = 0

    for relative in FILES:
        source = payload / relative
        target = project / relative
        if not source.exists():
            raise RuntimeError(f"Paket dosyası eksik: {relative}")
        if target.exists():
            backup = backup_root / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied += 1

    # Kayıt dosyasını ilk çalıştırmada mevcut watchlists.json ve Katılım Tüm
    # listesinden oluşturur. Var olan kayıt dosyasına dokunmaz.
    sys.path.insert(0, str(project))
    from engine.universe_manager import UniverseManager

    manager = UniverseManager()
    summaries = manager.list_universes()
    print(f"Sprint {SPRINT} uygulandı. {copied} dosya güncellendi.")
    for summary in summaries:
        print(f"- {summary.name}: {summary.active_count} aktif sembol")
    print(f"Yedek: {backup_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
