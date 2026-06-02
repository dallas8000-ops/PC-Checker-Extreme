' Stops the Django development server.
Set WshShell = CreateObject("WScript.Shell")
ps = "powershell -NoProfile -WindowStyle Hidden -Command ""Get-CimInstance Win32_Process -Filter ""Name='python.exe'"" | Where-Object { $_.CommandLine -like '*manage.py*runserver*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue}"""
WshShell.Run ps, 0, True
MsgBox "PC Checker Extreme server stopped (if it was running).", vbInformation, "PC Checker Extreme"
