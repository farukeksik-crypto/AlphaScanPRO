from __future__ import annotations
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
PROJECT = Path.cwd()
PAYLOAD = ROOT / 'payload'


def main() -> None:
    required = [PROJECT / 'app.py', PROJECT / 'engine', PROJECT / 'ui', PROJECT / 'tests']
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise SystemExit('Proje kökünde çalıştırın. Eksik: ' + ', '.join(missing))
    for source in PAYLOAD.rglob('*'):
        if source.is_file():
            target = PROJECT / source.relative_to(PAYLOAD)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    print('Sprint 10.13C Robot Intelligence Dashboard uygulandı.')
    print('- Canlı robot durumu ve bakiye')
    print('- Açık pozisyon yükü')
    print('- Son dönem Win Rate / Profit Factor / PnL')
    print('- Sembol ve çıkış kararı performansı')
    print('- Break-even, trailing ve kısmi çıkış kullanım oranları')
    print('- Risk ve örneklem uyarıları')

if __name__ == '__main__':
    main()
