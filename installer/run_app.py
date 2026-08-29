"""
Runtime entry point for the installed PC Checker Extreme app.

Compiled to PCCheckerExtreme.exe via PyInstaller (--onedir, --noconsole).
This IS the app once installed -- there is no separate Python install,
virtual environment, or embedded-Python download on the customer's
machine. Everything it needs ships inside the install folder next to
this executable.

Starts the Django dev server bound to localhost only, writes its own
PID to server.pid next to the executable (so "Stop PC Checker
Extreme.exe" can find and stop it), then opens the default browser.
"""
import os
import sys
import threading
import time
import webbrowser

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pc_checker_extreme.settings")

# In a PyInstaller --onedir build, sys.executable is the real exe sitting
# in the install folder (a stable, writable, per-user location) -- unlike
# --onefile, nothing is re-extracted to a temp dir on every launch, which
# matters here because Django's settings.py computes BASE_DIR (and the
# sqlite database path, and STATIC_ROOT) relative to this location. That
# path has to stay the same across restarts or the app would "forget"
# everything on every launch.
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(APP_DIR)

PID_FILE = os.path.join(APP_DIR, "server.pid")
PORT = "8000"


def write_pid():
    with open(PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))


def open_browser_when_ready():
    time.sleep(2.5)
    webbrowser.open(f"http://127.0.0.1:{PORT}/")


def main():
    write_pid()

    # --noconsole builds set sys.stdout/stderr to None; Django crashes writing to them.
    log_path = os.path.join(APP_DIR, "server.log")
    _log = open(log_path, "w", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = _log
    if sys.stderr is None:
        sys.stderr = _log

    threading.Thread(target=open_browser_when_ready, daemon=True).start()

    from django.core.management import execute_from_command_line

    # --noreload: the auto-reloader spawns a second child process to watch
    # for file changes, which we don't want (and don't need) in a shipped
    # build -- it would also mean two PIDs instead of the one we wrote above.
    execute_from_command_line(
        ["manage.py", "runserver", f"127.0.0.1:{PORT}", "--noreload"]
    )


if __name__ == "__main__":
    main()
