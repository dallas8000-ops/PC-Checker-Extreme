Set-Location $PSScriptRoot
& ".\.venv\Scripts\Activate.ps1"
Stop-Process -Name PCCheckerExtreme -Force -ErrorAction SilentlyContinue
Write-Host "Starting PC Checker Extreme at http://127.0.0.1:8000/" -ForegroundColor Cyan
Write-Host "Keep this window open. Press Ctrl+C to stop.`n"
python manage.py runserver 127.0.0.1:8000
