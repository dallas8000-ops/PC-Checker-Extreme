# PC Checker Extreme

AI-powered PC diagnostics built with **Django**. Scans Windows hardware by manufacturer (WMI), checks system health, finds outdated applications via **winget**, and generates an interactive AI review with prioritized suggestions.

## Features

- **Hardware identification** — CPU, GPU, RAM, storage, motherboard, network (manufacturer + model via WMI)
- **Health checks** — Memory, disk space, pending updates, uptime
- **Software inventory** — Installed programs from registry
- **Outdated apps** — `winget upgrade` parsing for available updates
- **Windows updates** — Pending update count via Windows Update API
- **AI analysis** — OpenAI-powered component reviews, priority actions, upgrade suggestions, expandable interactive sections
- **Scan history** — SQLite-backed reports you can revisit

## Deploy on Render

See **[RENDER.md](RENDER.md)** for hosting the web UI on [Render](https://render.com) (PostgreSQL, Gunicorn, Blueprint). Full WMI/winget scans still require running on **Windows locally**.

## Hybrid API and Alert Spec

See **[API_V1_SPEC.md](API_V1_SPEC.md)** for the implementation-ready contract for:

- device enrollment and check-ins
- incident triggers and severity thresholds
- AI enrichment boundaries
- fleet digests and notifications

## Requirements

- Windows 10/11 (full hardware/update features)
- Python 3.11+
- [Windows Package Manager (winget)](https://learn.microsoft.com/en-us/windows/package-manager/winget/) for app update detection (optional but recommended)

## Quick start (Cursor / VS Code — same as your other Django projects)

1. Open this folder in **Cursor** or **VS Code**
2. Select the Python interpreter: `.venv\Scripts\python.exe` (Command Palette → `Python: Select Interpreter`)
3. One-time setup in the **integrated terminal** (`Ctrl+`` `):

```powershell
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
```

4. **Run the app** (pick one):
   - **Terminal → Run Build Task** (`Ctrl+Shift+B`) — starts server in the **bottom panel** and opens the browser
   - Or integrated terminal: `python manage.py runserver` then open http://127.0.0.1:8000/

The server runs in Cursor’s **integrated terminal** (a tab at the bottom of the editor)—not a separate PowerShell window on your desktop.

### Debug / Run menu

- **Run and Debug** (`F5`) → choose **Django: PC Checker Extreme** (uses integrated terminal)

> **Tip:** Run Cursor as Administrator for the most complete WMI and update data.

## Features

- **Background scan** with progress bar (`/scan/<id>/progress/`)
- **Export** HTML / PDF from report page
- **Compare scans** at `/compare/`
- **SMART disk health**, temperatures, security (Defender/firewall), startup programs
- **Benchmark** CPU/disk micro-score
- **Driver update links**, duplicate driver flags, **copy winget commands**
- **AI**: plain-English summary, fix-this steps, upgrade advisor
- **Light/dark theme** (THEME button in header)
- **REST API**: `GET /api/scan/<uuid>/` (optional `PCC_API_KEY` header)
- **Scheduled scan**: `python manage.py run_scheduled_scan` (Task Scheduler)

```powershell
pip install -r requirements.txt
python manage.py migrate
```

### Optional: desktop shortcut (no editor)

Double-click **`Launch PC Checker Extreme.vbs`** if you want to start without opening Cursor.

## Configuration

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | Enables AI review (without it, local fallback analysis is used) |
| `OPENAI_MODEL` | Model id (default: `gpt-4o-mini`) |
| `DJANGO_SECRET_KEY` | Secret key for production |
| `DJANGO_DEBUG` | `true` for development |

## API

- `GET /api/health/` — Health check
- `GET /api/scan/<uuid>/` — Full scan report JSON
- `GET /api/driver-lookup/?vendor=Dell&model=Latitude` — Official support/driver source suggestions

## Project structure

```
pc_checker_extreme/     # Django project settings
diagnostics/
  services/
    hardware_collector.py   # WMI + psutil
    software_collector.py   # Registry, winget, Windows Update
    health_checks.py
    ai_analyzer.py
    scanner.py
  templates/              # Interactive report UI
  models.py               # ScanReport
```

## License

MIT (add your own license if needed)
