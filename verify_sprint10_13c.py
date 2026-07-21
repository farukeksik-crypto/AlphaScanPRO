from __future__ import annotations
from pathlib import Path
import py_compile
import subprocess
import sys

ROOT = Path.cwd()
FILES = [
    ROOT/'engine'/'robot_intelligence.py',
    ROOT/'ui'/'robot_intelligence_page.py',
    ROOT/'tests'/'test_robot_intelligence_10_13c.py',
    ROOT/'app.py',
]

def main() -> None:
    missing=[str(p) for p in FILES if not p.exists()]
    if missing: raise SystemExit('Eksik dosyalar:\n'+'\n'.join(missing))
    for path in FILES: py_compile.compile(str(path), doraise=True)
    app=(ROOT/'app.py').read_text(encoding='utf-8')
    assert 'Robot Intelligence' in app
    assert 'render_robot_intelligence' in app
    result=subprocess.run([sys.executable,'-m','pytest','tests/test_robot_intelligence_10_13c.py','-q'], cwd=ROOT)
    if result.returncode: raise SystemExit(result.returncode)
    print('Sprint 10.13C doğrulandı.')

if __name__ == '__main__': main()
