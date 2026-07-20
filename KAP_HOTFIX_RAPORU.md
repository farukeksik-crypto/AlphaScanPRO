# AlphaScan PRO — KAP Bilanço Hotfix

## Düzeltilen hata

`pd.read_html()` fonksiyonuna ham HTML metni doğrudan verilince Python 3.13 / güncel pandas ortamında HTML içerik dosya yolu gibi yorumlanabiliyordu. Bu nedenle ekranda uzun `<!DOCTYPE html>...` metniyle birlikte `No such file or directory` hatası görünüyordu.

## Yeni yöntem

- Klasik HTML tabloları `StringIO` üzerinden güvenli okunur.
- KAP'ın yeni Next.js yapısında finansal veriler sayfanın `self.__next_f.push(...)` uçuş verisinden ayrıştırılır.
- Finansal Durum ve Kâr/Zarar özet tabloları dönemleriyle birlikte oluşturulur.
- Veri bulunamazsa kullanıcıya kısa ve anlaşılır hata gösterilir; tüm HTML ekrana basılmaz.
- Yahoo Finance geri dönüşü korunur.

## Test

BIMAS KAP sayfasından alınmış gerçek HTML çıktısı ile çevrimdışı test edildi:

- Son dönem: 2026/03
- Sunum birimi: 1000TL
- Finansal Durum tablosu: bulundu
- Kâr/Zarar tablosu: bulundu
