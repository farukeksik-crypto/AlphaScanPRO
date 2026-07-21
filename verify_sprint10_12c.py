from __future__ import annotations
import py_compile, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
FILES=[Path('engine/position_management.py'),Path('tests/test_partial_take_profit_engine_10_12c.py')]

def main():
    failed=False
    for rel in FILES:
        try: py_compile.compile(str(ROOT/rel),doraise=True); print(f'[OK] Sözdizimi: {rel}')
        except Exception as e: print(f'[HATA] Sözdizimi: {rel}: {e}'); failed=True
    text=(ROOT/'engine/position_management.py').read_text(encoding='utf-8')
    for token in ['enable_multi_stage_take_profit','take_profit_levels','take_profit_ratios','partial_stage','tp_stage']:
        if token in text: print(f'[OK] İçerik: {token}')
        else: print(f'[EKSİK] İçerik: {token}'); failed=True
    if failed: raise SystemExit(1)
    print('[BİLGİ] İlgili testler çalıştırılıyor...')
    result=subprocess.run([sys.executable,'-m','pytest','tests/test_partial_take_profit_engine_10_12c.py','tests/test_break_even_engine_10_12a.py','tests/test_atr_trailing_engine_10_12b.py','-q'],cwd=ROOT)
    if result.returncode: raise SystemExit(result.returncode)
    print('\nSPRINT 10.12C DOĞRULAMA BAŞARILI')
if __name__=='__main__': main()
