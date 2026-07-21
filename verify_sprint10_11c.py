from __future__ import annotations

import ast
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def ok(message: str) -> None:
    print(f"[OK] {message}")


def fail(message: str) -> None:
    print(f"[HATA] {message}")
    raise SystemExit(1)


def main() -> None:
    app_file = ROOT / "app.py"
    page_file = ROOT / "ui" / "advanced_chart_page.py"

    if not app_file.exists():
        fail("app.py bulunamadı.")
    ok("app.py bulundu.")

    if not page_file.exists():
        fail("ui\\advanced_chart_page.py bulunamadı.")
    ok("Gelişmiş grafik sayfası bulundu.")

    text = page_file.read_text(encoding="utf-8")
    checks = {
        "Analiz hesaplama motoru": "def _build_analysis",
        "Analiz paneli": "def _render_analysis_panel",
        "Destek/direnç hesabı": "def _support_resistance",
        "Trend değerlendirmesi": '"Bileşen": "Trend"',
        "RSI değerlendirmesi": '"Bileşen": "RSI"',
        "MACD değerlendirmesi": '"Bileşen": "MACD"',
        "ADX/yön değerlendirmesi": '"Bileşen": "ADX / Yön"',
        "Hacim değerlendirmesi": '"Bileşen": "Hacim"',
        "Momentum değerlendirmesi": '"Bileşen": "Kısa Momentum"',
        "Karar eşikleri": 'decision = "NET AL"',
        "Puan gerekçesi tablosu": '"Neden":',
        "Robot katmanı korunmuş": "_add_robot_overlays",
        "Yeni genişlik kullanımı": 'width="stretch"',
    }
    missing = [name for name, marker in checks.items() if marker not in text]
    if missing:
        fail("Grafik analiz kapsamı eksik: " + ", ".join(missing))
    ok("Grafik analiz paneli kapsam kontrolleri geçti.")

    if "use_container_width=True" in text:
        fail("Gelişmiş grafik sayfasında eski use_container_width=True kullanımı kaldı.")
    ok("Streamlit genişlik uyarısı temizlendi.")

    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        fail(f"AST sözdizimi hatası: {exc}")
    function_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    required_functions = {"_build_analysis", "_render_analysis_panel", "_support_resistance"}
    if not required_functions.issubset(function_names):
        fail("Gerekli analiz fonksiyonları AST içinde bulunamadı.")
    ok("Analiz fonksiyonları AST ile doğrulandı.")

    for file in (app_file, page_file):
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(file)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            fail(f"Sözdizimi hatası: {file.name}\n{result.stderr or result.stdout}")
        ok(f"Sözdizimi temiz: {file.relative_to(ROOT)}")

    db_file = ROOT / "database" / "alphascan.db"
    if db_file.exists():
        try:
            with sqlite3.connect(db_file) as conn:
                names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "trade_history" not in names or "positions" not in names:
                fail("Robot tabloları eksik; 10.11B kurulumu doğrulanamadı.")
            ok("10.11B robot tabloları korunmuş.")
        except sqlite3.Error as exc:
            fail(f"Veritabanı kontrolü başarısız: {exc}")
    else:
        print("[UYARI] database\\alphascan.db bulunamadı; veritabanı kontrolü atlandı.")

    print("\n" + "=" * 58)
    print("SPRINT 10.11C DOĞRULAMA BAŞARILI")
    print("Uygulamayı açın: py -3.13 -m streamlit run app.py")
    print("Sonraki adım: Sprint 10.11D — göstergeler ve çizim araçları")


if __name__ == "__main__":
    main()
