$TaskName = "AlphaScanPRO Background Worker"

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Kaldırıldı: $TaskName" -ForegroundColor Yellow
} else {
    Write-Host "Görev bulunamadı: $TaskName"
}
