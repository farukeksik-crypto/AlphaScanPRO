from __future__ import annotations

from pathlib import Path
import py_compile
import subprocess
import sys


FILES = [
    "app.py",
    "background_worker.py",
    "config/background_settings.py",
    "engine/background_orchestrator.py",
    "engine/universe_manager.py",
    "ui/universe_manager_page.py",
]


def main() -> int:
    project = Path.cwd()
    missing = [relative for relative in FILES if not (project / relative).exists()]
    if missing:
        raise RuntimeError("Eksik Sprint 10.19A dosyaları: " + ", ".join(missing))

    for relative in FILES:
        py_compile.compile(str(project / relative), doraise=True)

    from engine.universe_manager import UniverseManager

    manager = UniverseManager()
    zero_count = len(manager.get_items("arindirma_0"))
    participation_count = len(manager.get_items("katilim_tum"))
    if zero_count < 1:
        raise RuntimeError("Arındırma 0 evreni boş.")
    if participation_count < 100:
        raise RuntimeError("Katılım Tüm evreni beklenenden küçük.")

    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_universe_manager_10_19a.py",
        "tests/test_background_multi_universe_10_19a.py",
        "-q",
    ]
    completed = subprocess.run(command, cwd=project, check=False)
    if completed.returncode != 0:
        return completed.returncode

    print(
        f"Sprint 10.19A doğrulandı. Arındırma 0: {zero_count} · "
        f"Katılım Tüm: {participation_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
