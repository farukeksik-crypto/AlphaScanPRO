from __future__ import annotations

import py_compile
import sqlite3
from pathlib import Path


def check(condition: bool, success: str, failure: str, errors: list[str]) -> None:
    if condition:
        print(f"[OK] {success}")
    else:
        print(f"[HATA] {failure}")
        errors.append(failure)


def main() -> None:
    root = Path.cwd()
    errors: list[str] = []
    app = root / "app.py"
    page = root / "ui" / "advanced_chart_page.py"
    db_file = root / "database" / "alphascan.db"

    check(app.exists(), "app.py bulundu.", "app.py bulunamadı.", errors)
    check(page.exists(), "Gelişmiş grafik sayfası bulundu.", "ui/advanced_chart_page.py bulunamadı.", errors)

    if app.exists():
        text = app.read_text(encoding="utf-8")
        check(
            "render_advanced_chart(data_engine, watchlists, database)" in text,
            "Grafik sayfasına veritabanı bağlantısı veriliyor.",
            "app.py grafik yönlendirmesinde database parametresi eksik.",
            errors,
        )

    if page.exists():
        text = page.read_text(encoding="utf-8")
        required = [
            "def _load_robot_overlay",
            "trade_history",
            "FROM positions",
            'name="Robot BUY"',
            'name="Robot SELL"',
            'annotation_text=f"{label}',
            '"STOP"',
            '"TP1"',
            '"TP2"',
            "İşlem Bağlantısı",
            "Robot işlem ayrıntıları",
            "render_advanced_chart(data_engine, watchlists: dict | None = None, database=None)",
        ]
        missing = [token for token in required if token not in text]
        check(not missing, "Robot grafik kapsam kontrolleri geçti.", "Eksik bileşenler: " + ", ".join(missing), errors)

    for relative in [Path("app.py"), Path("ui/advanced_chart_page.py")]:
        target = root / relative
        if target.exists():
            try:
                py_compile.compile(str(target), doraise=True)
                print(f"[OK] Sözdizimi temiz: {relative}")
            except Exception as exc:
                message = f"Sözdizimi hatası ({relative}): {exc}"
                print(f"[HATA] {message}")
                errors.append(message)

    if db_file.exists():
        try:
            with sqlite3.connect(db_file) as connection:
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                check("trade_history" in tables, "trade_history tablosu hazır.", "trade_history tablosu eksik.", errors)
                check("positions" in tables, "positions tablosu hazır.", "positions tablosu eksik.", errors)
        except Exception as exc:
            errors.append(f"Veritabanı kontrolü başarısız: {exc}")
            print(f"[HATA] Veritabanı kontrolü başarısız: {exc}")
    else:
        print("[BİLGİ] database/alphascan.db henüz yok; uygulama ilk çalışmada oluşturabilir.")

    print("\n" + "=" * 58)
    if errors:
        print(f"SPRINT 10.11B DOĞRULAMA BAŞARISIZ — {len(errors)} hata")
        for item in errors:
            print(f"- {item}")
        raise SystemExit(1)

    print("SPRINT 10.11B DOĞRULAMA BAŞARILI")
    print("Uygulamayı açın: py -3.13 -m streamlit run app.py")
    print("Sonraki adım: Sprint 10.11C — Grafik Analiz Paneli")


if __name__ == "__main__":
    main()
