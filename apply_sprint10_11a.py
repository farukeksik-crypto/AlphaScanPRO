from __future__ import annotations

import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SPRINT = "10.11A"
PAGE_FILE = Path("ui/advanced_chart_page.py")


def fail(message: str) -> None:
    print(f"[HATA] {message}")
    raise SystemExit(1)


def ensure_project_root(root: Path) -> None:
    required = [root / "app.py", root / "engine", root / "ui", root / "requirements.txt"]
    missing = [str(path.name) for path in required if not path.exists()]
    if missing:
        fail("Bu dosya AlphaScanPRO proje ana klasöründe çalıştırılmalı. Eksik: " + ", ".join(missing))


def backup(root: Path, paths: list[Path]) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = root / "backups" / f"sprint10_11a_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    for relative in paths:
        source = root / relative
        if source.exists():
            target = backup_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    return backup_dir


def patch_app(app_text: str) -> str:
    import_line = "from ui.advanced_chart_page import render_advanced_chart\n"
    if import_line not in app_text:
        anchor = "from ui.financial_analysis_page import render_financial_analysis\n"
        if anchor not in app_text:
            fail("app.py içinde grafik importu için beklenen bağlantı noktası bulunamadı.")
        app_text = app_text.replace(anchor, anchor + import_line, 1)

    menu_line = '        "Gelişmiş Grafik",\n'
    if menu_line not in app_text:
        anchor = '        "Emtia",\n'
        if anchor not in app_text:
            fail("app.py menüsünde 'Emtia' satırı bulunamadı.")
        app_text = app_text.replace(anchor, anchor + menu_line, 1)

    route_block = (
        'elif page == "Gelişmiş Grafik":\n'
        '    render_advanced_chart(data_engine, watchlists)\n\n'
    )
    if route_block not in app_text:
        anchor = 'elif page == "Bilanço ve Yapay Zekâ Analizi":\n'
        if anchor not in app_text:
            fail("app.py içinde sayfa yönlendirme bağlantı noktası bulunamadı.")
        app_text = app_text.replace(anchor, route_block + anchor, 1)

    return app_text


def ensure_requirement(root: Path) -> None:
    requirements = root / "requirements.txt"
    lines = requirements.read_text(encoding="utf-8").splitlines()
    normalized = {line.strip().lower().split("==")[0].split(">=")[0] for line in lines if line.strip()}
    if "plotly" not in normalized:
        lines.append("plotly")
        requirements.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def ensure_plotly() -> None:
    try:
        import plotly  # noqa: F401
        print("[OK] plotly hazır.")
        return
    except ImportError:
        print("[BİLGİ] plotly bulunamadı; kuruluyor...")
    result = subprocess.run([sys.executable, "-m", "pip", "install", "plotly"], check=False)
    if result.returncode != 0:
        fail("plotly kurulamadı. İnternet bağlantısını kontrol edip 'py -3.13 -m pip install plotly' çalıştırın.")


def update_changelog(root: Path) -> None:
    changelog = root / "CHANGELOG.md"
    entry = (
        "\n## Sprint 10.11A - Gelişmiş Grafik\n"
        "- Kripto, BIST ve emtia için gelişmiş grafik sayfası eklendi.\n"
        "- Mum grafik, EMA20/50/200 ve hacim görünümü eklendi.\n"
        "- Zaman dilimi, sembol seçimi, yakınlaştırma ve veri yenileme desteği eklendi.\n"
        "- Robot işlem işaretleri Sprint 10.11B için ayrıldı.\n"
    )
    existing = changelog.read_text(encoding="utf-8") if changelog.exists() else "# AlphaScan PRO Değişiklik Günlüğü\n"
    if "## Sprint 10.11A - Gelişmiş Grafik" not in existing:
        changelog.write_text(existing.rstrip() + "\n" + entry, encoding="utf-8")


def main() -> None:
    root = Path.cwd()
    package_root = Path(__file__).resolve().parent
    ensure_project_root(root)

    backup_dir = backup(
        root,
        [Path("app.py"), Path("requirements.txt"), Path("CHANGELOG.md"), PAGE_FILE],
    )
    print(f"[OK] Yedek oluşturuldu: {backup_dir}")

    payload_page = package_root / "payload" / PAGE_FILE
    if not payload_page.exists():
        fail(f"Paket dosyası eksik: {payload_page}")

    target_page = root / PAGE_FILE
    target_page.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(payload_page, target_page)
    print(f"[OK] Yazıldı: {PAGE_FILE}")

    app_path = root / "app.py"
    patched = patch_app(app_path.read_text(encoding="utf-8"))
    app_path.write_text(patched, encoding="utf-8")
    print("[OK] app.py menü ve yönlendirme bağlantıları eklendi.")

    ensure_requirement(root)
    print("[OK] requirements.txt güncellendi.")
    ensure_plotly()
    update_changelog(root)
    print("[OK] CHANGELOG.md güncellendi.")

    print("\nSprint 10.11A uygulandı.")
    print("Şimdi çalıştırın: py -3.13 .\\verify_sprint10_11a.py")


if __name__ == "__main__":
    main()
