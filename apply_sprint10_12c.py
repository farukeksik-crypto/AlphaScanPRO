from __future__ import annotations
import py_compile, shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAYLOAD = ROOT / 'payload'
FILES = [Path('engine/position_management.py'), Path('tests/test_partial_take_profit_engine_10_12c.py')]

def main():
    if not (ROOT / 'engine').exists():
        raise SystemExit('[HATA] Betiği AlphaScanPRO proje ana klasöründe çalıştırın.')
    backup = ROOT / 'backups' / f"sprint10_12c_{datetime.now():%Y%m%d_%H%M%S}"
    backup.mkdir(parents=True, exist_ok=True)
    print(f'[OK] Yedek oluşturuldu: {backup}')
    for rel in FILES:
        src, dst = PAYLOAD / rel, ROOT / rel
        if dst.exists():
            b = backup / rel; b.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(dst,b)
        dst.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src,dst)
        print(f'[OK] Yazıldı: {rel}')
    changelog=ROOT/'CHANGELOG.md'
    note='''\n## Sprint 10.12C — Multi-stage Partial Take Profit\n- TP1/TP2 kısmi satış ve TP3 nihai çıkış eklendi.\n- Satış oranları başlangıç miktarı üzerinden hesaplanır.\n- Her fiyat güncellemesinde en fazla bir TP kademesi çalışır.\n- LONG/SHORT uyumu ve aşama günlüğü eklendi.\n'''
    changelog.write_text(changelog.read_text(encoding='utf-8',errors='replace')+note,encoding='utf-8')
    print('[OK] CHANGELOG.md güncellendi.')
    for rel in FILES:
        py_compile.compile(str(ROOT/rel),doraise=True); print(f'[OK] Sözdizimi temiz: {rel}')
    print('\nSprint 10.12C uygulandı.\nŞimdi çalıştırın: py -3.13 .\\verify_sprint10_12c.py')
if __name__=='__main__': main()
