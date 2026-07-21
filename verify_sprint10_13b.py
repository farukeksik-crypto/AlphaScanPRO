from __future__ import annotations

import py_compile
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILES = (
    Path("engine/performance_analytics.py"),
    Path("ui/performance_analytics_page.py"),
    Path("app.py"),
    Path("tests/test_performance_analytics_10_13b.py"),
)


def main() -> None:
    for relative in FILES:
        target = ROOT / relative
        if not target.exists():
            raise SystemExit(f"[HATA] Dosya bulunamadı: {relative}")
        py_compile.compile(str(target), doraise=True)
        print(f"[OK] Sözdizimi: {relative}")

    app_text = (ROOT / "app.py").read_text(encoding="utf-8")
    required = (
        "render_performance_analytics",
        '"Performans Analizi PRO"',
        'elif page == "Performans Analizi PRO":',
    )
    for marker in required:
        if marker not in app_text:
            raise SystemExit(f"[HATA] app.py entegrasyonu eksik: {marker}")
    print("[OK] Streamlit menü entegrasyonu doğrulandı.")

    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_performance_analytics.py",
        "tests/test_performance_analytics_10_13b.py",
        "-q",
    ]
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)

    print("\n[BAŞARILI] Sprint 10.13B doğrulandı.")
    print("Sonraki adım: Streamlit'i açıp Performance Analytics PRO sayfasını kontrol edin.")


if __name__ == "__main__":
    main()
