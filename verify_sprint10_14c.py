from __future__ import annotations
import subprocess, sys
from pathlib import Path

def main():
    root=Path(__file__).resolve().parent
    required=[
        root/'engine/ai/strategy_acceptance.py',
        root/'ui/strategy_lab_page.py',
        root/'tests/test_strategy_acceptance_10_14c.py',
    ]
    missing=[str(p.relative_to(root)) for p in required if not p.exists()]
    if missing:
        raise SystemExit('Eksik dosyalar: '+', '.join(missing))
    cmd=[sys.executable,'-m','pytest','tests/test_walk_forward_10_14a.py','tests/test_walk_forward_10_14b.py','tests/test_strategy_acceptance_10_14c.py','-q']
    result=subprocess.run(cmd,cwd=root)
    if result.returncode:
        raise SystemExit(result.returncode)
    print('Sprint 10.14C doğrulandı.')

if __name__=='__main__':
    main()
