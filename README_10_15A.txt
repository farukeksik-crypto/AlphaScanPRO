AlphaScan PRO - Sprint 10.15A Portfolio & Risk Manager Core

Eklenenler:
- Stop mesafesi ve işlem başına risk yüzdesine göre miktar hesaplama
- Risk bütçesi oluşturma
- İşlem planı (plan_trade / plan_execution)
- Portföy limitleri nedeniyle otomatik miktar azaltma veya reddetme
- Açık pozisyonları risk yöneticisine senkronlama
- Hesap özkaynağı, gün başlangıcı ve günlük gerçekleşen PnL senkronlama
- Limit ve kullanım oranlarını içeren risk dashboard verisi
- Geriye dönük uyumlu PortfolioRuntimeBridge entegrasyonu

Çalıştırma:
py -3.13 .\apply_sprint10_15a.py
py -3.13 .\verify_sprint10_15a.py

Commit:
git add .
git commit -m "Sprint 10.15A portfolio and risk manager core"
