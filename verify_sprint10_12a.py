from __future__ import annotations

import ast
import py_compile
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"[HATA] {message}")
    print(f"[OK] {message}")


def main() -> None:
    robot = ROOT / "engine" / "robot_engine.py"
    manager = ROOT / "engine" / "position_management.py"
    test_file = ROOT / "tests" / "test_break_even_engine_10_12a.py"

    require((ROOT / "app.py").exists(), "app.py bulundu.")
    require(robot.exists(), "Robot motoru bulundu.")
    require(manager.exists(), "Pozisyon yönetim motoru bulundu.")
    require(test_file.exists(), "10.12A test dosyası bulundu.")

    robot_text = robot.read_text(encoding="utf-8")
    manager_text = manager.read_text(encoding="utf-8")

    for token in (
        "slippage_rate",
        "break_even_extra_buffer_pct",
        "break_even_include_costs",
        "effective_break_even_buffer_pct",
        "işlem maliyetleri güvenceye alındı",
    ):
        require(token in robot_text, f"Robot kapsam kontrolü: {token}")

    for token in (
        "cost_buffer_pct",
        "effective_offset_pct",
        'position.metadata["break_even"]',
        "stop işlem maliyetleri dahil güvenli maliyet seviyesine taşındı",
    ):
        require(token in manager_text, f"Pozisyon motoru kapsam kontrolü: {token}")

    ast.parse(robot_text)
    ast.parse(manager_text)
    print("[OK] 10.12A değişiklikleri AST ile doğrulandı.")

    for file in (robot, manager, test_file):
        py_compile.compile(str(file), doraise=True)
        print(f"[OK] Sözdizimi temiz: {file.relative_to(ROOT)}")

    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "tests/test_break_even_engine_10_12a.py",
        "tests/test_position_management.py",
        "tests/test_smart_position_manager.py",
        "tests/test_smart_exit.py",
    ]
    result = subprocess.run(command, cwd=ROOT, text=True)
    require(result.returncode == 0, "Break-even ve mevcut çıkış testleri geçti.")

    print("\n" + "=" * 58)
    print("SPRINT 10.12A DOĞRULAMA BAŞARILI")
    print("Sonraki adım: Sprint 10.12B — ATR Trailing Stop")


if __name__ == "__main__":
    main()
