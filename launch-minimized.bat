@echo off
title PC Checker Extreme (background)
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run: python -m venv .venv  then  pip install -r requirements.txt
  pause
  exit /b 1
)
start /min "PC Checker Extreme Server" cmd /c ".venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000"
timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:8000/"
