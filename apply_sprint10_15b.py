from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / "payload"
BACKUP = ROOT / ".sprint_backups" / "10_15b"


def copy_payload() -> None:
    for source in PAYLOAD.rglob("*"):
        if not source.is_file():
            continue
        relative = source.relative_to(PAYLOAD)
        target = ROOT / relative
        if target.exists():
            backup = BACKUP / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        print(f"Uygulandı: {relative}")


def patch_app() -> None:
    path = ROOT / "app.py"
    text = path.read_text(encoding="utf-8")
    import_line = "from ui.portfolio_risk_page import render_portfolio_risk\n"
    if import_line not in text:
        anchor = "from ui.performance_analytics_page import render_performance_analytics\n"
        if anchor not in text:
            raise RuntimeError("app.py import noktası bulunamadı.")
        text = text.replace(anchor, anchor + import_line)
    menu_line = '        "Portföy Risk Merkezi",\n'
    if menu_line not in text:
        anchor = '        "Performans Analizi PRO",\n'
        if anchor not in text:
            raise RuntimeError("app.py menü noktası bulunamadı.")
        text = text.replace(anchor, anchor + menu_line)
    route = 'elif page == "Portföy Risk Merkezi":\n    render_portfolio_risk(database)\n\n'
    if route not in text:
        anchor = 'elif page == "Performans Analizi PRO":\n    render_performance_analytics(database)\n\n'
        if anchor not in text:
            raise RuntimeError("app.py yönlendirme noktası bulunamadı.")
        text = text.replace(anchor, anchor + route)
    path.write_text(text, encoding="utf-8")
    print("Güncellendi: app.py")


if __name__ == "__main__":
    BACKUP.mkdir(parents=True, exist_ok=True)
    copy_payload()
    patch_app()
    print("Sprint 10.15B başarıyla uygulandı.")
