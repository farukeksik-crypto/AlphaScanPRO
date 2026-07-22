from __future__ import annotations

import argparse
from pathlib import Path

from config.settings import DATABASE_FILE
from engine.production_readiness import ProductionReadinessChecker, format_text_report


def main() -> int:
    parser = argparse.ArgumentParser(description="AlphaScan PRO paper trading hazırlık kontrolü")
    parser.add_argument("--require-worker", action="store_true", help="Background Worker çalışmıyorsa kontrolü başarısız say")
    parser.add_argument("--json", action="store_true", help="Raporu JSON biçiminde yazdır")
    parser.add_argument("--output", type=Path, help="Raporu dosyaya da kaydet")
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parent
    checker = ProductionReadinessChecker(base_dir, database_path=DATABASE_FILE)
    report = checker.run(require_worker=args.require_worker)
    rendered = report.to_json() if args.json else format_text_report(report)
    print(rendered)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")

    return 0 if report.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
