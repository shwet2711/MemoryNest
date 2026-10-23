$ErrorActionPreference = "Stop"
Set-Location "D:\MemoryNest"

$python = "D:\MemoryNest\.venv\Scripts\python.exe"
$log = "D:\MemoryNest\logs\notification_worker.log"

while ($true) {
    "[$(Get-Date -Format o)] Starting notification worker." |
        Out-File -FilePath $log -Append -Encoding utf8

    & $python -u -m app.scripts.notification_delivery_worker `
        --watch --interval-seconds 30 --batch-size 25 *>> $log

    $exitCode = $LASTEXITCODE
    "[$(Get-Date -Format o)] Worker exited with code $exitCode. Restarting in 15 seconds." |
        Out-File -FilePath $log -Append -Encoding utf8

    Start-Sleep -Seconds 15
}
