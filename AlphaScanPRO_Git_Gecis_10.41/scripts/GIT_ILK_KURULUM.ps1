param(
    [string]$RemoteUrl = "https://github.com/farukeksik-crypto/AlphaScanPRO.git",
    [string]$Branch = "main"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "AlphaScan PRO Git ilk kurulumu" -ForegroundColor Cyan

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git bulunamadı. Önce Git for Windows kurulmalıdır."
}
if (-not (Test-Path ".\engine") -or -not (Test-Path ".\app.py")) {
    throw "Script proje ana klasöründe çalıştırılmalıdır."
}

if (-not (Test-Path ".git")) {
    git init
    if ($LASTEXITCODE -ne 0) { throw "git init başarısız oldu." }
}

git branch -M $Branch
if ($LASTEXITCODE -ne 0) { throw "Ana dal ayarlanamadı." }

$origin = git remote get-url origin 2>$null
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($origin)) {
    git remote add origin $RemoteUrl
    if ($LASTEXITCODE -ne 0) { throw "GitHub bağlantısı eklenemedi." }
} elseif ($origin -ne $RemoteUrl) {
    Write-Host "Mevcut origin: $origin" -ForegroundColor Yellow
    Write-Host "Beklenen origin: $RemoteUrl" -ForegroundColor Yellow
    throw "Güvenlik için uzak depo otomatik değiştirilmedi."
}

git add -A
if ($LASTEXITCODE -ne 0) { throw "Dosyalar Git'e eklenemedi." }

$hasCommit = git rev-parse --verify HEAD 2>$null
if ($LASTEXITCODE -ne 0) {
    git commit -m "AlphaScan PRO v10.41 Git baseline"
    if ($LASTEXITCODE -ne 0) {
        throw "İlk commit oluşturulamadı. Git kullanıcı adı/e-posta ayarı gerekebilir."
    }
} else {
    $changes = git status --porcelain
    if ($changes) {
        git commit -m "AlphaScan PRO v10.41 Git transition"
        if ($LASTEXITCODE -ne 0) { throw "Geçiş commit'i oluşturulamadı." }
    }
}

Write-Host "" 
Write-Host "Yerel Git kurulumu tamamlandı." -ForegroundColor Green
Write-Host "Uzak depoya ilk gönderim için:" -ForegroundColor Cyan
Write-Host "  git push -u origin $Branch" -ForegroundColor White
Write-Host "" 
Write-Host "Not: GitHub deposunda farklı bir geçmiş varsa push reddedilebilir; bu durumda zorla gönderim yapmayın." -ForegroundColor Yellow
