# Building the PC Checker Extreme Windows Installer

## Prerequisites (developer machine only)

| Tool | Where to get it |
|------|----------------|
| **Inno Setup 6** | https://jrsoftware.org/isdl.php |
| **Python 3.x** on `PATH` | https://python.org (only for `collectstatic`; end users don't need it) |
| Internet access | pip downloads packages during the build |

---

## One-command build

From the project root in PowerShell:

```powershell
.\installer\build_installer.ps1
```

The script will:
1. Download **Python 3.12 embeddable** (x64) from python.org
2. Bootstrap **pip** inside that embeddable Python
3. `pip install` everything in `requirements.txt` into the embedded Python
4. Run `manage.py collectstatic` to snapshot static assets
5. Compile `installer\PCCheckerExtreme.iss` with Inno Setup
6. Output `installer\dist\PCCheckerExtreme-Setup.exe`

Build time: ~5–10 minutes depending on download speed.
Installer size: roughly 80–120 MB (LZMA-compressed).

---

## App icon (required before first public release)

The installer references **`installer\icon.ico`**.

- The build script auto-creates a placeholder (Python's exe icon) so the build doesn't fail.
- Before shipping, replace it with your real icon:
  - Recommended size: 256×256 (multi-resolution `.ico` preferred)
  - Free converter: https://convertico.com/

---

## Customising the installer

Edit `installer\PCCheckerExtreme.iss`:

| Field | Where in .iss |
|-------|---------------|
| App name | `#define AppName` |
| Version | `#define AppVersion` (or pass `/DAppVersion=x.y.z` to ISCC) |
| Publisher | `#define AppPublisher` |
| Website | `#define AppURL` |
| Unique GUID | `AppId` in `[Setup]` — **change this if you fork/brand** |

---

## What the installer does on the end-user machine

1. Extracts all files to `%LOCALAPPDATA%\PC Checker Extreme\`
   - No UAC / admin rights required
2. Generates a fresh `SECRET_KEY` in `.env`
3. Runs `manage.py migrate` to create the SQLite database
4. Offers to launch the app immediately

### Shortcuts created
- Start Menu → PC Checker Extreme
- Start Menu → Stop PC Checker Extreme
- Desktop shortcut (optional, user chooses during setup)
- Startup folder entry (optional, user chooses during setup)

### Uninstall
Control Panel → Programs → PC Checker Extreme → Uninstall  
(Removes the app, `.env`, and database.)

---

## Distributing the installer

The output `PCCheckerExtreme-Setup.exe` is self-contained.  
Send it to customers — they double-click, click through the wizard, done.

### Code signing (recommended before broad release)
An unsigned installer triggers SmartScreen on Windows 10/11.  
Sign with `signtool.exe` after the build:

```powershell
signtool sign /tr http://timestamp.digicert.com /td sha256 /fd sha256 `
  /f "YourCert.pfx" /p "YourPassword" `
  installer\dist\PCCheckerExtreme-Setup.exe
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ISCC.exe not found` | Install Inno Setup 6 and re-run |
| `pip install` fails | Check internet connection; try `pip install --retries 5` |
| `collectstatic` fails | Ensure the project's own `.venv` is activated first |
| Installer won't start on target machine | Check Windows version ≥ 10 (64-bit) |
| SmartScreen blocks installer | Sign the exe, or have user click "More info → Run anyway" |
