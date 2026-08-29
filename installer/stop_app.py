"""
Compiled to Stop PC Checker Extreme.exe via PyInstaller (--onedir, --noconsole).

Reads server.pid next to this executable (written by PCCheckerExtreme.exe
on startup) and stops that process. Shows a native message box so this
behaves the same as the old "Stop PC Checker Extreme.vbs" did.
"""
import ctypes
import os
import sys

import psutil

if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

PID_FILE = os.path.join(APP_DIR, "server.pid")

MB_ICONINFORMATION = 0x40


def show_message(text, title="PC Checker Extreme"):
    ctypes.windll.user32.MessageBoxW(0, text, title, MB_ICONINFORMATION)


def main():
    stopped = False
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r", encoding="utf-8") as f:
                pid = int(f.read().strip())
            proc = psutil.Process(pid)
            proc.terminate()
            proc.wait(timeout=5)
            stopped = True
        except (psutil.NoSuchProcess, ValueError, psutil.TimeoutExpired):
            pass
        finally:
            try:
                os.remove(PID_FILE)
            except OSError:
                pass

    if stopped:
        show_message("PC Checker Extreme server stopped.")
    else:
        show_message("PC Checker Extreme does not appear to be running.")


if __name__ == "__main__":
    main()
