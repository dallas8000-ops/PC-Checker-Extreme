"""
The customer-facing installer, compiled to "Install PC Checker Extreme.exe"
via PyInstaller (--onedir or --onefile, --noconsole).

Ships in the same folder as an "app" subfolder (the PyInstaller --onedir
build of PCCheckerExtreme.exe + Stop PC Checker Extreme.exe + the Django
app + pre-collected staticfiles + a pre-seeded db.sqlite3). This script's
only job is to copy that payload into a stable per-user location, write a
fresh .env, create shortcuts, and register an uninstaller -- no admin
rights needed anywhere in this process.

Run normally to install. Run with --uninstall (what the registry entry's
UninstallString points at, from the installed copy of this same exe) to
remove everything it created.
"""
import ctypes
import os
import secrets
import shutil
import sys
import winreg

APP_NAME = "PC Checker Extreme"
APP_ID = "PCCheckerExtreme"  # used as the registry key name / AppUserModelID
PUBLISHER = "Gilliom Frontline Digital"
APP_URL = "https://gilliomfrontlinedigital.com"
APP_VERSION = "1.0.0"

MB_ICONINFORMATION = 0x40
MB_ICONERROR = 0x10
MB_YESNO = 0x04
MB_ICONQUESTION = 0x20
IDYES = 6


def _get_desktop_path():
    """Use Shell API so OneDrive-redirected Desktops resolve correctly."""
    try:
        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(0, 0x0010, 0, 0, buf) == 0:
            return buf.value
    except Exception:
        pass
    return os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")


def show_message(text, title=APP_NAME, icon=MB_ICONINFORMATION):
    ctypes.windll.user32.MessageBoxW(0, text, title, icon)


def ask_yes_no(text, title=APP_NAME):
    result = ctypes.windll.user32.MessageBoxW(0, text, title, MB_YESNO | MB_ICONQUESTION)
    return result == IDYES


def here():
    """Folder this executable (or script, when run unfrozen for testing) lives in."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def install_dir():
    return os.path.join(os.environ["LOCALAPPDATA"], APP_NAME)


def create_shortcut(path, target, working_dir, icon):
    # Use PowerShell subprocess so COM runs outside the frozen process,
    # avoiding the pywintypes.com_error inheritance-chain bug in PyInstaller.
    import subprocess

    def _esc(s):
        return s.replace("'", "''")

    script = (
        f"$ws = New-Object -ComObject WScript.Shell; "
        f"$sc = $ws.CreateShortcut('{_esc(path)}'); "
        f"$sc.TargetPath = '{_esc(target)}'; "
        f"$sc.WorkingDirectory = '{_esc(working_dir)}'; "
        f"$sc.IconLocation = '{_esc(icon)}'; "
        f"$sc.Save()"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
    )


def do_install():
    payload_dir = os.path.join(here(), "app")
    if not os.path.isdir(payload_dir):
        show_message(
            "Could not find the app payload next to this installer "
            f"(expected a folder named 'app' in {here()}). "
            "Re-download the installer -- it may be corrupted or incomplete.",
            icon=MB_ICONERROR,
        )
        sys.exit(1)

    dest = install_dir()
    if os.path.isdir(dest):
        if not ask_yes_no(
            f"{APP_NAME} appears to already be installed at:\n{dest}\n\n"
            "Reinstall (your saved data and .env will be kept)?"
        ):
            return
        # Kill any running instances so Windows releases the file locks.
        import subprocess, time
        for exe_name in ["PCCheckerExtreme.exe", "Stop PC Checker Extreme.exe"]:
            subprocess.run(["taskkill", "/f", "/im", exe_name], capture_output=True)
        time.sleep(1)
        # Copy over the existing install, but don't touch .env or db.sqlite3 --
        # those hold this customer's generated secret key and their data.
        for name in os.listdir(payload_dir):
            if name in (".env", "db.sqlite3"):
                continue
            src = os.path.join(payload_dir, name)
            dst = os.path.join(dest, name)
            if os.path.isdir(src):
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
    else:
        os.makedirs(dest, exist_ok=True)
        for name in os.listdir(payload_dir):
            src = os.path.join(payload_dir, name)
            dst = os.path.join(dest, name)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)

    # Fresh .env with a real secret key -- skip if this is a reinstall and
    # one already exists, so we don't invalidate existing sessions/data.
    env_path = os.path.join(dest, ".env")
    if not os.path.exists(env_path):
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(f"DJANGO_SECRET_KEY={secrets.token_urlsafe(50)}\n")
            f.write("DJANGO_DEBUG=false\n")

    # Copy this installer into the install folder too, so the registry's
    # UninstallString has something stable to point at even if the customer
    # deletes the original downloaded installer file.
    installer_copy = os.path.join(dest, "Uninstall.exe")
    try:
        shutil.copy2(sys.executable if getattr(sys, "frozen", False) else __file__, installer_copy)
    except OSError:
        installer_copy = None

    exe_path = os.path.join(dest, "PCCheckerExtreme.exe")
    stop_exe_path = os.path.join(dest, "Stop PC Checker Extreme.exe")
    icon_path = os.path.join(dest, "icon.ico")
    if not os.path.exists(icon_path):
        icon_path = exe_path  # PyInstaller exes carry their own embedded icon

    start_menu = os.path.join(
        os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs", APP_NAME
    )
    os.makedirs(start_menu, exist_ok=True)
    try:
        create_shortcut(os.path.join(start_menu, f"{APP_NAME}.lnk"), exe_path, dest, icon_path)
        create_shortcut(
            os.path.join(start_menu, f"Stop {APP_NAME}.lnk"), stop_exe_path, dest, icon_path
        )
    except Exception:
        pass

    desktop = _get_desktop_path()
    try:
        create_shortcut(os.path.join(desktop, f"{APP_NAME}.lnk"), exe_path, dest, icon_path)
    except Exception:
        pass  # desktop shortcut is a nice-to-have, never block install over it

    # Register in "Apps & Features" (HKCU -- no admin rights needed).
    key_path = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_ID}"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
        winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
        winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, PUBLISHER)
        winreg.SetValueEx(key, "URLInfoAbout", 0, winreg.REG_SZ, APP_URL)
        winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, dest)
        winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, icon_path)
        uninstall_target = installer_copy or exe_path
        winreg.SetValueEx(
            key, "UninstallString", 0, winreg.REG_SZ, f'"{uninstall_target}" --uninstall'
        )
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)

    show_message(
        f"{APP_NAME} installed.\n\n"
        f"Find it in your Start Menu, or on your Desktop.\n\n"
        f"Installed to:\n{dest}"
    )

    if ask_yes_no(f"Launch {APP_NAME} now?"):
        os.startfile(exe_path)


def do_uninstall():
    dest = install_dir()
    if not ask_yes_no(f"Remove {APP_NAME} and all its data from:\n{dest}\n\nThis cannot be undone."):
        return

    # Stop the server first if it's running, so its files aren't locked.
    stop_exe = os.path.join(dest, "Stop PC Checker Extreme.exe")
    if os.path.exists(stop_exe):
        try:
            os.system(f'"{stop_exe}"')
        except OSError:
            pass

    for name in (
        os.path.join(
            os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs", APP_NAME
        ),
        os.path.join(os.environ["USERPROFILE"], "Desktop", f"{APP_NAME}.lnk"),
    ):
        if os.path.isdir(name):
            shutil.rmtree(name, ignore_errors=True)
        elif os.path.exists(name):
            try:
                os.remove(name)
            except OSError:
                pass

    key_path = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_ID}"
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
    except FileNotFoundError:
        pass

    show_message(f"{APP_NAME} has been removed.")

    # Remove the install folder last, and from outside itself, since this
    # running exe is very likely a copy living inside `dest`.
    if os.path.isdir(dest):
        try:
            shutil.rmtree(dest)
        except OSError:
            # Our own running exe file can't delete itself while in use on
            # Windows -- schedule it via a detached cmd that waits a moment.
            os.system(f'cmd /c "timeout /t 2 >nul & rmdir /s /q "{dest}""')


def main():
    if "--uninstall" in sys.argv:
        do_uninstall()
    else:
        do_install()


if __name__ == "__main__":
    main()
