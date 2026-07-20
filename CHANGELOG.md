# AlphaScan PRO Değişiklik Günlüğü

## Sprint 5 — Background Platform (18.07.2026)

- Streamlit'ten bağımsız `background_worker.py` eklendi.
- BIST, kripto ve emtia için ayrı zamanlama altyapısı eklendi.
- Kripto 7/24; BIST piyasa saati kontrollü; emtia periyodik çalışır.
- Arka plan tarama sonuçları ve çalışma geçmişi SQLite'a kaydedilir.
- Sanal robot, arka plan tarama sonuçlarıyla bağlantı kurar.
- Aynı worker'ın iki kez açılmasını engelleyen kilit sistemi eklendi.
- Dönen log dosyaları ve Windows Görev Zamanlayıcı betikleri eklendi.
- Streamlit'e `Arka Plan Platformu` izleme sayfası eklendi.
- Bu sürümde gerçek emir gönderimi yoktur.

# AlphaScan PRO - Değişiklik Günlüğü

Bu dosyada AlphaScan PRO projesinde yapılan önemli geliştirmeler sprint bazında kayıt altına alınır.

---

## [Sprint 2] - Backtest Sistemi

### Tamamlananlar

- Backtest motoru oluşturuldu.
- Alım ve satım işlemleri simüle edildi.
- Başlangıç sermayesi desteği eklendi.
- Komisyon hesaplaması eklendi.
- Stop-loss desteği eklendi.
- Take-profit desteği eklendi.
- İşlem geçmişi oluşturuldu.
- Net kâr ve zarar hesaplaması eklendi.
- Kazanan ve kaybeden işlem sayıları hesaplandı.
- Başarı oranı hesaplandı.
- Profit Factor hesaplaması eklendi.
- Equity Curve verisi oluşturuldu.
- Backtest sayfası oluşturuldu.

### Devam Edenler

- Maksimum Drawdown hesaplaması
- Drawdown grafiği
- Aylık performans tablosu
- Backtest işlem geçmişi tablosu
- Equity Curve grafiği
- Sharpe Ratio
- İşlem tekrar inceleme ekranı

---

## [Sprint 1] - Temel Uygulama

### Tamamlananlar

- Streamlit tabanlı ana arayüz oluşturuldu.
- BIST hisseleri için veri çekme sistemi oluşturuldu.
- Mum grafik eklendi.
- EMA20 göstergesi eklendi.
- EMA50 göstergesi eklendi.
- EMA200 göstergesi eklendi.
- RSI göstergesi eklendi.
- MACD göstergesi eklendi.
- ADX göstergesi eklendi.
- ATR göstergesi eklendi.
- Hacim analizi eklendi.
- Teknik skorlama sistemi oluşturuldu.
- Al, sat ve izle sinyalleri oluşturuldu.
- Sanal portföy sistemi eklendi.
- İşlem geçmişi eklendi.
- Katılım hisseleri listesi oluşturuldu.