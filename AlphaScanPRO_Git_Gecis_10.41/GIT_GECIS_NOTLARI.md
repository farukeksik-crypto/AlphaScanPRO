# AlphaScan PRO 10.41 — Git Geçiş Paketi

Bu paket, doğrulanmış 10.40 klasörünü tek ana Git projesine dönüştürür.

## Bir defalık kurulum

Paketteki dosyaları `AlphaScanPRO_Master_10.40` klasörüne kopyalayın ve:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\GIT_ILK_KURULUM.ps1
```

İlk commit sonrası GitHub'a göndermek için:

```powershell
git push -u origin main
```

## Sonraki güncellemeler

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\GIT_GUNCELLE_VE_TEST.ps1 -SkipInstall
```

veya `GUNCELLE_VE_TEST.cmd` dosyasına çift tıklayın.

## Güvenlik

- Güncelleme yalnızca `git pull --ff-only` kullanır.
- Yerel değişiklik varken güncelleme yapmaz.
- Otomatik force-push veya otomatik merge yapmaz.
- Runtime veritabanları, loglar ve gizli ayarlar Git'e eklenmez.
