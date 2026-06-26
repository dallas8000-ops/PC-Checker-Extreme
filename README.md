# PC Checker Extreme

**AI-powered Windows PC diagnostics built with Django.** Scans hardware by manufacturer (WMI), checks system health, finds outdated applications via `winget`, and generates an interactive AI review with prioritized suggestions.

| | |
|---|---|
| **Live demo** | https://pc-checker-extreme-production.up.railway.app |
| **Code** | https://github.com/dallas8000-ops/PC-Checker-Extreme |

> **Note on the live demo:** the hosted web UI demonstrates the interface, scan history, report views, and AI review flow. Full hardware/WMI/`winget` scans require running the app **locally on Windows** — a cloud host can't read your machine's hardware. See [Run locally](#run-locally).

---

## Features

**Hardware & system**
- **Windows system information** — CPU, GPU, RAM, storage, motherboard, BIOS (WMI/CIM — same sources as `msinfo32`)
- **Hardware identification** — manufacturer + model via WMI (not Control Panel scraping)
- **Health checks** — memory, disk space, pending updates, uptime
- **SMART disk health**, temperatures, security posture (Defender/firewall), startup programs
- **Benchmark** — CPU/disk micro-score
- **Battery report** — laptop battery status + `powercfg /batteryreport` path when applicable
- **Reliability Monitor** — recent stability records (`Win32_ReliabilityRecords`)
- **Event log digest** — recent Critical/Error/Warning from System & Application logs

**Software & updates**
- **Software inventory** — installed programs from registry
- **Outdated apps** — `winget upgrade` parsing for available updates
- **Windows updates** — pending update count via Windows Update API
- **Driver update links**, duplicate driver flags, copy-ready `winget` commands
- **Startup impact** — high/medium/low ranking for startup entries

**AI & reporting**
- **AI analysis** — OpenAI-powered component reviews, priority actions, upgrade suggestions, expandable interactive sections (plain-English summary, fix-this steps, upgrade advisor)
- **Tools tab** — command playbook (SFC, DISM, winget, disk cleanup), bottleneck analysis, driver gap report, Update Catalog links
- **Segment-aware vendor sources** — OEM-first support/driver/troubleshooting links by customer segment
- **Compare scans** — side-by-side diff at `/compare/` + optional AI summary
- **Scan chat** — ask questions about a completed report (OpenAI + snapshot context)
- **Background scan** with progress bar (`/scan/<id>/progress/`)
- **Export** HTML / PDF from the report page
- **Scan history** — SQLite-backed reports you can revisit
- **Light/dark theme** (THEME button in header)
- **Scheduled scan** — `python manage.py run_scheduled_scan` (Windows Task Scheduler)

---

## Hybrid API and alert spec

See **[API_V1_SPEC.md](API_V1_SPEC.md)** for the implementation-ready contract covering device enrollment and check-ins, incident triggers and severity thresholds, AI enrichment boundaries, and fleet digests and notifications.

---

## Requirements

- Windows 10/11 (full hardware/update features)
- Python 3.11+
- [Windows Package Manager (winget)](https://learn.microsoft.com/en-us/windows/package-manager/winget/) for app update detection (optional but recommended)

---

## Run locally

Same flow as the other Django projects in this portfolio (Cursor / VS Code):

1. Open this folder in **Cursor** or **VS Code**.
2. Select the Python interpreter: `.venv\Scripts\python.exe` (Command Palette → `Python: Select Interpreter`).
3. One-time setup in the integrated terminal:

```powershell
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py seed_driver_sources --segment all
```

4. Run the app (pick one):
   - **Terminal → Run Build Task** (`Ctrl+Shift+B`) — starts the server in the bottom panel and opens the browser, or
   - integrated terminal: `python manage.py runserver`, then open http://127.0.0.1:8000/

The server runs in the editor's **integrated terminal**, not a separate PowerShell window.

**Debug / Run menu:** Run and Debug (`F5`) → choose **Django: PC Checker Extreme**.

> **Tip:** run Cursor/VS Code as Administrator for the most complete WMI and update data.

### Optional: desktop shortcut (no editor)

Double-click **`Launch PC Checker Extreme.vbs`** to start without opening an editor.

---

## Deploy (Railway)

The web UI deploys to Railway as a Django service. Hardware-scan features remain Windows-local
(a cloud host can't inspect your machine), so the hosted deployment is for the interface,
report views, scan history, and AI review flow.

1. Add a **PostgreSQL** plugin (or keep SQLite for a lightweight demo) → set `DATABASE_URL` if using Postgres.
2. Set environment variables:
   - `DJANGO_SECRET_KEY` — long random secret
   - `DJANGO_DEBUG=false`
   - `OPENAI_API_KEY` — optional, enables AI review (local fallback analysis is used without it)
3. Deploy. The repo's `railway.toml` / start command runs migrations and serves via Gunicorn.

---

## Configuration

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | Enables AI review (without it, local fallback analysis is used) |
| `OPENAI_MODEL` | Model id (default: `gpt-4o-mini`) |
| `DJANGO_SECRET_KEY` | Secret key for production |
| `DJANGO_DEBUG` | `true` for development |
| `PCC_API_KEY` | Optional header key to protect the REST API |

---

## API

- `GET /api/health/` — health check
- `GET /api/scan/<uuid>/` — full scan report JSON (optional `PCC_API_KEY` header)
- `GET /api/driver-lookup/?vendor=Dell&model=Latitude` — official support/driver source suggestions
- `GET /api/driver-lookup/?vendor=Dell&model=Latitude&segment=msp` — segment-prioritized source suggestions

---

## Project structure

```
pc_checker_extreme/         # Django project settings
diagnostics/
  services/
    hardware_collector.py   # WMI + psutil
    software_collector.py   # registry, winget, Windows Update
    health_checks.py
    ai_analyzer.py
    scanner.py
  templates/                # interactive report UI
  models.py                 # ScanReport
railway.toml                # Railway deploy config
```

---

## License

MIT (add your own license if needed)
