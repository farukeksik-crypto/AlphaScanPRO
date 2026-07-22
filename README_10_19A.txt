AlphaScan PRO — Sprint 10.19A
BIST Evren Yöneticisi ve Çoklu BIST Arka Plan Taraması

Bu sprint:
- Mevcut Arındırma 0 listesini kalıcı evren kayıt sistemine aktarır.
- Katılım Tüm evrenini tek merkezden yönetir.
- Arındırma 0 hisselerini arayüzden ekleme ve pasif yapma imkânı verir.
- Silinen hisselerin geçmiş işlem kayıtlarını korur.
- Evren değişikliklerini database/universe_changes.jsonl dosyasına kaydeder.
- Background Worker'ın aynı seans döngüsünde Arındırma 0 ve Katılım Tüm
  evrenlerini ayrı ayrı taramasını sağlar.
- Robotun sanal işlem mantığını ve filtre eşiklerini değiştirmez.

Kurulum:
1. ZIP içeriğini AlphaScanPRO_Git_Temiz klasörüne çıkar.
2. PowerShell:
   py -3.13 .\apply_sprint10_19a.py
   py -3.13 .\verify_sprint10_19a.py
3. Background Worker'ı yeniden başlat.
4. Streamlit ekranında Evren Yöneticisi sayfasını kontrol et.

Not:
Bu sprint resmi internet kaynağından otomatik veri indirmez. Mevcut proje
listesini güvenli bir kayıt sistemine taşır ve kullanıcıya ekleme/çıkarma
kontrolü verir. Resmî kaynak senkronizasyonu sonraki sprintte eklenecektir.
