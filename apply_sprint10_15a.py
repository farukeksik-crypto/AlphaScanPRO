from __future__ import annotations

from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "payload"


def main() -> int:
    project = Path.cwd()
    required = project / "engine" / "portfolio_risk_manager.py"
    if not required.exists():
        print("HATA: Bu dosyayı AlphaScan PRO proje ana klasöründe çalıştırın.")
        return 1

    files = [
        (PAYLOAD / "engine" / "portfolio_risk_manager.py", project / "engine" / "portfolio_risk_manager.py"),
        (PAYLOAD / "tests" / "test_portfolio_risk_manager_10_15a.py", project / "tests" / "test_portfolio_risk_manager_10_15a.py"),
    ]

    backup_dir = project / ".sprint_backups" / "10_15a"
    backup_dir.mkdir(parents=True, exist_ok=True)

    for source, target in files:
        if target.exists():
            relative = target.relative_to(project)
            backup = backup_dir / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        print(f"Uygulandı: {target.relative_to(project)}")

    print("Sprint 10.15A başarıyla uygulandı.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
