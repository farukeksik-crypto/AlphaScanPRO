param(
    [Parameter(Mandatory=$true)]
    [string]$Message,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Test-Path ".git")) {
    throw "Bu klasör Git deposu değil."
}

if (-not $SkipTests) {
    powershell -ExecutionPolicy Bypass -File .\MASTER_KURULUM_VE_TEST.ps1 -SkipInstall
    if ($LASTEXITCODE -ne 0) { throw "Testler başarısız; commit gönderilmedi." }
}

git add -A
if ($LASTEXITCODE -ne 0) { throw "git add başarısız oldu." }

$changes = git status --porcelain
if (-not $changes) {
    Write-Host "Commit edilecek değişiklik yok." -ForegroundColor Yellow
    exit 0
}

git commit -m $Message
if ($LASTEXITCODE -ne 0) { throw "git commit başarısız oldu." }

git push
if ($LASTEXITCODE -ne 0) { throw "git push başarısız oldu." }

Write-Host "Değişiklikler test edildi, kaydedildi ve GitHub'a gönderildi." -ForegroundColor Green
