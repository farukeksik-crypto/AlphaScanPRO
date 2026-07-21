from __future__ import annotations

import importlib.util
import py_compile
import sys
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
    requirements = root / "requirements.txt"

    check(app.exists(), "app.py bulundu.", "app.py bulunamadı.", errors)
    check(page.exists(), "Gelişmiş grafik sayfası bulundu.", "ui/advanced_chart_page.py bulunamadı.", errors)

    if app.exists():
        app_text = app.read_text(encoding="utf-8")
        check(
            "from ui.advanced_chart_page import render_advanced_chart" in app_text,
            "Grafik importu bağlı.",
            "app.py grafik importu eksik.",
            errors,
        )
        check(
            '"Gelişmiş Grafik"' in app_text,
            "Gelişmiş Grafik menüde.",
            "Gelişmiş Grafik menü kaydı eksik.",
            errors,
        )
        check(
            'elif page == "Gelişmiş Grafik":' in app_text
            and "render_advanced_chart(data_engine, watchlists)" in app_text,
            "Sayfa yönlendirmesi bağlı.",
            "Gelişmiş Grafik yönlendirmesi eksik.",
            errors,
        )

    if requirements.exists():
        req_text = requirements.read_text(encoding="utf-8").lower()
        check("plotly" in req_text, "plotly gereksinimi kayıtlı.", "requirements.txt içinde plotly yok.", errors)

    check(importlib.util.find_spec("plotly") is not None, "plotly kurulmuş.", "plotly kurulu değil.", errors)

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

    if page.exists():
        page_text = page.read_text(encoding="utf-8")
        required_tokens = [
            "go.Candlestick",
            '"EMA20"',
            '"EMA50"',
            '"EMA200"',
            "st.plotly_chart",
            "COMMODITY_SYMBOLS",
            "CRYPTO_SYMBOLS",
        ]
        missing = [token for token in required_tokens if token not in page_text]
        check(not missing, "Grafik kapsam kontrolleri geçti.", "Eksik grafik bileşenleri: " + ", ".join(missing), errors)

    print("\n" + "=" * 58)
    if errors:
        print(f"SPRINT 10.11A DOĞRULAMA BAŞARISIZ — {len(errors)} hata")
        for item in errors:
            print(f"- {item}")
        raise SystemExit(1)

    print("SPRINT 10.11A DOĞRULAMA BAŞARILI")
    print("Uygulamayı açın: py -3.13 -m streamlit run app.py")
    print("Sonraki adım: Sprint 10.11B — robot BUY/SELL/STOP/TP işaretleri")


if __name__ == "__main__":
    main()
