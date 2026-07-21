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

## Sprint 10.11A - Gelişmiş Grafik
- Kripto, BIST ve emtia için gelişmiş grafik sayfası eklendi.
- Mum grafik, EMA20/50/200 ve hacim görünümü eklendi.
- Zaman dilimi, sembol seçimi, yakınlaştırma ve veri yenileme desteği eklendi.
- Robot işlem işaretleri Sprint 10.11B için ayrıldı.

## Sprint 10.11B - Robot İşlemleri Grafik Üzerinde
- Robot BUY ve SELL işlemleri gelişmiş grafik üzerine eklendi.
- Açık pozisyonların STOP, TP1 ve TP2 seviyeleri gösterildi.
- Aynı pozisyona ait giriş ve çıkışlar bağlantı çizgisiyle eşleştirildi.
- Hover açıklamalarına işlem nedeni, fiyat ve kâr/zarar bilgileri eklendi.
- Seçili sembol için robot işlem özeti ve son 50 işlem tablosu eklendi.

## Sprint 10.11C — Grafik Analiz Paneli
- Açıklamalı 100 puanlık teknik analiz paneli eklendi.
- Trend, RSI, MACD, ADX/yön, hacim, momentum ve destek/direnç ayrı gerekçelerle değerlendiriliyor.
- NET AL / AL ADAY / İZLE / BEKLE kararı ve her puanın nedeni gösteriliyor.
- Streamlit use_container_width uyarıları bu sayfada width='stretch' kullanımına geçirildi.

## Sprint 10.11D — Göstergeler ve Çizim Araçları
- EMA20, EMA50 ve EMA200 ayrı ayrı açılıp kapatılabilir hale getirildi.
- Bollinger Bands ve otomatik destek/direnç katmanları eklendi.
- Hacim, RSI, MACD, ADX/+DI/-DI ve ATR için seçilebilir alt paneller eklendi.
- Trend çizgisi, serbest çizgi, dikdörtgen, daire ve şekil silme araçları etkinleştirildi.
- Temel görünüm ve analiz görünümü hazır ayarları ile oturum içi gösterge tercihleri eklendi.
- Robot işlem katmanı ve açıklamalı 10.11C analiz paneli korundu.

## Sprint 10.12A — Maliyet Korumalı Break-even
- Break-even stop seviyesi çift yön komisyon, slipaj ve ek güvenlik tamponunu kapsayacak şekilde hesaplanır.
- Stop seviyesi hiçbir zaman geriye taşınmaz ve her pozisyonda yalnızca bir kez etkinleşir.
- Aktivasyon nedeni, eski/yeni stop ve maliyet tamponu robot sistem olaylarına ve pozisyon metadata alanına kaydedilir.
- Yeni hedefli testler: `tests/test_break_even_engine_10_12a.py`.

## Sprint 10.12B — ATR Trailing Stop
- ATR tabanlı dinamik takip eden stop eklendi.
- ATR mesafesi minimum ve maksimum yüzde sınırlarıyla güvenli aralıkta tutuldu.
- Trailing stop yalnızca break-even sonrasında devreye giriyor.
- Stop hiçbir zaman geriye taşınmıyor.
- ATR modu, mesafe, eski stop ve yeni stop günlükleniyor.


## Sprint 10.12C — Multi-stage Partial Take Profit
- TP1/TP2 kısmi satış ve TP3 nihai çıkış eklendi.
- Satış oranları başlangıç miktarı üzerinden hesaplanır.
- Her fiyat güncellemesinde en fazla bir TP kademesi çalışır.
- LONG/SHORT uyumu ve aşama günlüğü eklendi.

## Sprint 10.12D - Smart Exit Decision
- HOLD / TRAIL / PARTIAL_EXIT / FULL_EXIT karar katmanı eklendi.
- RSI, MACD, EMA20, hacim ve ADX zayıflaması birlikte puanlanıyor.
- Break-even, ATR trailing ve TP1 sonrası kâr koruma bağlamı skora katılıyor.
- Eski Smart Exit API davranışı geriye dönük uyumlu tutuldu.

## Sprint 10.13A - Trade Journal PRO
- Ayrıntılı işlem olay günlüğü eklendi.
- Tam ve kısmi çıkışlar ayrı kayıtlanıyor.
- Giriş/çıkış puanı, Smart Exit kararı ve onay sayısı tutuluyor.
- Break-even, ATR trailing ve TP aşaması kaydediliyor.
- MFE, MAE, işlem süresi ve metadata saklanıyor.
- Hesap bazlı özet metriği eklendi.

