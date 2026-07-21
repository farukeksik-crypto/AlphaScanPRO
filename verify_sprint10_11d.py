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
        "Ek gösterge hazırlığı": "def _ensure_extra_indicators",
        "Gösterge kontrol paneli": "def _render_indicator_controls",
        "Bollinger üst bandı": '"BB_UPPER"',
        "Bollinger alt bandı": '"BB_LOWER"',
        "ATR hesabı": '"ATR14_PANEL"',
        "RSI paneli": '"show_rsi"',
        "MACD paneli": '"show_macd"',
        "ADX paneli": '"show_adx"',
        "ATR paneli": '"show_atr"',
        "Destek/direnç seçeneği": '"show_support_resistance"',
        "Trend çizgisi aracı": '"drawline"',
        "Serbest çizgi aracı": '"drawopenpath"',
        "Dikdörtgen aracı": '"drawrect"',
        "Daire aracı": '"drawcircle"',
        "Şekil silme aracı": '"eraseshape"',
        "Düzenlenebilir şekiller": '"shapePosition": True',
        "Temel görünüm": '"Temel görünüm"',
        "Analiz görünümü": '"Analiz görünümü"',
        "Robot katmanı": "_add_robot_overlays",
        "Analiz paneli": "_render_analysis_panel",
    }
    missing = [name for name, marker in checks.items() if marker not in text]
    if missing:
        fail("10.11D kapsamı eksik: " + ", ".join(missing))
    ok("Gösterge ve çizim araçları kapsam kontrolleri geçti.")

    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        fail(f"AST sözdizimi hatası: {exc}")
    function_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    required = {"_ensure_extra_indicators", "_render_indicator_controls", "_build_figure", "_build_analysis"}
    if not required.issubset(function_names):
        fail("Gerekli 10.11D fonksiyonları AST içinde bulunamadı.")
    ok("10.11D fonksiyonları AST ile doğrulandı.")

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
                fail("Robot tabloları eksik; 10.11B katmanı doğrulanamadı.")
            ok("Robot işlem tabloları korunmuş.")
        except sqlite3.Error as exc:
            fail(f"Veritabanı kontrolü başarısız: {exc}")
    else:
        print("[UYARI] database\\alphascan.db bulunamadı; veritabanı kontrolü atlandı.")

    print("\n" + "=" * 58)
    print("SPRINT 10.11D DOĞRULAMA BAŞARILI")
    print("Uygulamayı açın: py -3.13 -m streamlit run app.py")
    print("Sonraki adım: Sprint 10.12 — Akıllı Çıkış Motoru")


if __name__ == "__main__":
    main()
