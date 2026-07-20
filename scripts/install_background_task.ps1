$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $PSScriptRoot
$Python = (Get-Command py).Source
$TaskName = "AlphaScanPRO Background Worker"
$Worker = Join-Path $ProjectDir "background_worker.py"
$LogDir = Join-Path $ProjectDir "logs\background"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$Action = New-ScheduledTaskAction `
    -Execute $Python `
    -Argument "-3.13 `"$Worker`"" `
    -WorkingDirectory $ProjectDir

$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "AlphaScan PRO BIST, Kripto ve Emtia arka plan tarama motoru" `
    -Force

Start-ScheduledTask -TaskName $TaskName
Write-Host "Kuruldu ve başlatıldı: $TaskName" -ForegroundColor Green
