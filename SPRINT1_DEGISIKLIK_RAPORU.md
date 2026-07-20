# AlphaScan PRO v3.0 — Sprint 1

## Eklenenler
- BIST, Kripto ve Emtia için bağımsız sanal hesaplar.
- BIST hesabı: TRY, başlangıç 1.000.000.
- Kripto hesabı: USDT, başlangıç 100.000.
- Emtia hesabı: USD, başlangıç 100.000.
- Robot ekranında piyasa/hesap seçimi.
- Dashboard'da üç hesabın ayrı gösterimi.
- Sol menüde `Paranın Yönü` sayfası.
- Worker'ın taradığı piyasaya ait hesabı kullanması.

## Veri koruma
- Mevcut `robot_state` kaydı BIST hesabına aktarılır.
- Eski açık pozisyonlar piyasa alanına göre hesaplara bağlanır.
- Piyasa bilgisi boş eski pozisyonlar güvenli varsayımla BIST hesabına atanır.
- Veritabanı silinmez veya sıfırlanmaz.

## Paranın Yönü v1
Bu sürüm gerçek banka/fon girişini doğrudan ölçmez. Son worker taramasındaki teknik puan, güven ve karar dağılımından göreceli bir sermaye yönü göstergesi üretir.

## Testler
- Tüm Python dosyaları: derleme başarılı.
- SQLite migration: başarılı.
- Mevcut BIST bakiyesi ve iki açık pozisyon: korundu.
- Kripto hesabında test pozisyonu: BIST hesabını etkilemedi.
