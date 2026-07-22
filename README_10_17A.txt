AlphaScan PRO - Sprint 10.17A Production Readiness

Kurulum:
  py -3.13 .\apply_sprint10_17a.py
  py -3.13 .\verify_sprint10_17a.py

Paper trading hazırlık raporu:
  py -3.13 .\paper_trading_readiness.py

Background Worker mutlaka çalışıyor olmalı kontrolü:
  py -3.13 .\paper_trading_readiness.py --require-worker

JSON raporu:
  py -3.13 .\paper_trading_readiness.py --json --output runtime\readiness.json

Kontroller:
- Python sürümü
- Python bağımlılıkları
- Çekirdek AlphaScan modülleri
- Cache/log/runtime/database yazma izinleri
- SQLite erişimi ve temel tablolar
- Boş disk alanı
- Background Worker heartbeat/watchdog
- .sprint_backups ve payload Git hijyeni

Not:
.gitignore yeni sprint yedeklerini ve payload klasörünü dışarıda bırakır. Daha önce commit
edilmiş dosyalar Git geçmişinden otomatik kaldırılmaz.
