' PC Checker Extreme - Application Launcher
' -------------------------------------------------------
' Starts the Django server in the background (no console
' window) and opens the browser. Safe to double-click
' again while the server is already running.

Option Explicit

Const APP_NAME  = "PC Checker Extreme"
Const APP_PORT  = "8000"
Const APP_HOST  = "127.0.0.1"
Const APP_URL   = "http://127.0.0.1:8000/"
Const WAIT_MS   = 3500   ' milliseconds to wait for server start

Dim fso, WshShell, appDir, pythonExe, manageScript

Set fso      = CreateObject("Scripting.FileSystemObject")
Set WshShell = CreateObject("WScript.Shell")

appDir      = fso.GetParentFolderName(WScript.ScriptFullName)
pythonExe   = appDir & "\python\python.exe"
manageScript = appDir & "\manage.py"

' ----- Sanity checks -----
If Not fso.FileExists(pythonExe) Then
    MsgBox "Python runtime not found." & vbCrLf & vbCrLf & _
           "Expected: " & pythonExe & vbCrLf & vbCrLf & _
           "Try reinstalling " & APP_NAME & ".", _
           vbCritical, APP_NAME
    WScript.Quit 1
End If

If Not fso.FileExists(manageScript) Then
    MsgBox "Application files are missing." & vbCrLf & vbCrLf & _
           "Expected: " & manageScript & vbCrLf & vbCrLf & _
           "Try reinstalling " & APP_NAME & ".", _
           vbCritical, APP_NAME
    WScript.Quit 1
End If

' ----- Check whether the server is already running -----
If IsPortListening(APP_HOST, CInt(APP_PORT)) Then
    ' Already up - just open the browser
    WshShell.Run APP_URL, 1, False
    WScript.Quit 0
End If

' ----- Start Django server (hidden, no console window) -----
Dim cmd
cmd = "cmd /c cd /d """ & appDir & """ && " & _
      """" & pythonExe & """ """ & manageScript & """ runserver " & _
      APP_HOST & ":" & APP_PORT & " --noreload"
WshShell.Run cmd, 0, False      ' windowStyle 0 = hidden; bWaitOnReturn False

' ----- Wait for the server to be ready -----
WScript.Sleep WAIT_MS

' ----- Open the browser -----
WshShell.Run APP_URL, 1, False

WScript.Quit 0

' ===================================================================
' Helper: returns True if something is already listening on host:port
' Uses a raw TCP connect via WinHttp as the lightest available method.
' ===================================================================
Function IsPortListening(host, port)
    Dim http
    On Error Resume Next
    Set http = CreateObject("WinHttp.WinHttpRequest.5.1")
    http.SetTimeouts 800, 800, 800, 800
    http.Open "GET", "http://" & host & ":" & port & "/", False
    http.Send
    IsPortListening = (Err.Number = 0 And http.Status > 0)
    Err.Clear
    On Error GoTo 0
End Function
