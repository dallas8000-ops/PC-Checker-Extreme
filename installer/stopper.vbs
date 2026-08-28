' PC Checker Extreme - Server Stopper
' Finds and kills any running Django manage.py runserver process
' for this application, then notifies the user.

Option Explicit

Const APP_NAME = "PC Checker Extreme"

Dim WshShell, ps
Set WshShell = CreateObject("WScript.Shell")

' Use PowerShell to find python.exe processes whose command line
' contains both manage.py and runserver, then stop them.
ps = "powershell -NoProfile -NonInteractive -WindowStyle Hidden -Command """ & _
     "Get-CimInstance Win32_Process -Filter 'Name=''python.exe''' | " & _
     "Where-Object { $_.CommandLine -like '*manage.py*runserver*' } | " & _
     "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" & _
     """"

WshShell.Run ps, 0, True    ' wait for PowerShell to finish

MsgBox APP_NAME & " has been stopped.", vbInformation, APP_NAME
