' Double-click to start the app (no visible terminal) and open the browser.
Set WshShell = CreateObject("WScript.Shell")
projectDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)

pythonExe = projectDir & "\.venv\Scripts\python.exe"
If Not CreateObject("Scripting.FileSystemObject").FileExists(pythonExe) Then
  MsgBox "Virtual environment not found." & vbCrLf & vbCrLf & "Run in terminal:" & vbCrLf & "python -m venv .venv" & vbCrLf & "pip install -r requirements.txt", vbCritical, "PC Checker Extreme"
  WScript.Quit 1
End If

' Start Django hidden (window style 0 = no console)
cmd = "cmd /c cd /d """ & projectDir & """ && """ & pythonExe & """ manage.py runserver 127.0.0.1:8000"
WshShell.Run cmd, 0, False

' Wait for server, then open browser
WScript.Sleep 3500
WshShell.Run "http://127.0.0.1:8000/", 1, False
