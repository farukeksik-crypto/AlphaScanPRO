param([switch]$SkipInstall)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Test-Path ".git")) {
    throw "Bu klasör henüz Git deposu değil. Önce scripts\GIT_ILK_KURULUM.ps1 çalıştırın."
}

$dirty = git status --porcelain
if ($dirty) {
    Write-Host "Kaydedilmemiş yerel değişiklikler var:" -ForegroundColor Yellow
    $dirty | ForEach-Object { Write-Host "  $_" }
    throw "Güncellemeden önce değişiklikleri commit edin veya geri alın."
}

Write-Host "GitHub'dan güncellemeler alınıyor..." -ForegroundColor Cyan
git pull --ff-only
if ($LASTEXITCODE -ne 0) { throw "git pull başarısız oldu. Otomatik birleştirme yapılmadı." }

$args = @("-ExecutionPolicy", "Bypass", "-File", ".\MASTER_KURULUM_VE_TEST.ps1")
if ($SkipInstall) { $args += "-SkipInstall" }

Write-Host "Doğrulama başlatılıyor..." -ForegroundColor Cyan
& powershell @args
if ($LASTEXITCODE -ne 0) { throw "Güncelleme sonrası doğrulama başarısız oldu." }

Write-Host "Git güncellemesi ve testler başarıyla tamamlandı." -ForegroundColor Green
