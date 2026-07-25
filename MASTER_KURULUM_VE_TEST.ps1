param([switch]$SkipInstall)
$ErrorActionPreference = "Stop"
Write-Host "AlphaScan PRO Master 10.30 doğrulaması" -ForegroundColor Cyan
if (-not (Test-Path ".\\engine") -or -not (Test-Path ".\\app.py")) {
    throw "Script proje ana klasöründe çalıştırılmalıdır."
}
if (-not $SkipInstall) {
    Write-Host "Bağımlılıklar kuruluyor/güncelleniyor..." -ForegroundColor Cyan
    py -3.13 -m pip install -r .\\requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "Bağımlılık kurulumu başarısız." }
}
Write-Host "Python kaynakları derleniyor..." -ForegroundColor Cyan
py -3.13 -c "from pathlib import Path; import py_compile; files=[p for p in Path('.').rglob('*.py') if not any(x in p.parts for x in ('__pycache__','.git','.pytest_cache'))]; [py_compile.compile(str(p), doraise=True) for p in files]; print(f'{len(files)} Python dosyası doğrulandı.')"
if ($LASTEXITCODE -ne 0) { throw "Python derleme kontrolü başarısız." }
Write-Host "Tüm testler çalıştırılıyor..." -ForegroundColor Cyan
py -3.13 -m pytest .\\tests -q
if ($LASTEXITCODE -ne 0) { throw "Testler başarısız oldu. Çıktıyı paylaşın." }
Write-Host "MASTER 10.30 BAŞARIYLA DOĞRULANDI" -ForegroundColor Green
