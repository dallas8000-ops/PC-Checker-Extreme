"""
Build the PC Checker Extreme distributable -- Python only, no PowerShell,
no Inno Setup. Run this from the project's existing dev virtual environment
(the same one you use for `python manage.py runserver`):

    cd "C:\\Software Projects\\PC Checker Extreme"
    .venv\\Scripts\\python.exe installer\\build.py

What it does, in order:
  1. Makes sure PyInstaller is installed in this venv.
  2. Runs collectstatic (same as always).
  3. Builds a pre-migrated, pre-seeded db.sqlite3 the same safe way the old
     PowerShell script did: move the dev db aside, migrate + seed against a
     clean slate, copy the result out, then restore the dev db -- your dev
     database is never at risk.
  4. Runs PyInstaller against installer/pcc.spec, producing PCCheckerExtreme.exe
     and "Stop PC Checker Extreme.exe" in one shared folder.
  5. Runs PyInstaller against installer/install.py, producing the customer-
     facing "Install PC Checker Extreme.exe".
  6. Assembles everything into installer/dist_final/ and zips it up.

If PyInstaller reports a missing module the first time you run this (a
"ModuleNotFoundError" style message), that's normal and easy to fix: tell
me the exact module name and I'll add it to pcc.spec's hidden imports list.
That's an ordinary, well-documented PyInstaller thing -- nothing like the
PowerShell issues from before.
"""
import os
import shutil
import subprocess
import sys
import zipfile

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INSTALLER_DIR = os.path.join(PROJECT_ROOT, "installer")
PYTHON = sys.executable  # the venv python currently running this script

APP_VERSION = "1.0.0"


def run(cmd, cwd=None):
    print(f"\n>>> {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd or PROJECT_ROOT)
    if result.returncode != 0:
        print(f"\nFAILED (exit code {result.returncode}): {' '.join(cmd)}")
        sys.exit(result.returncode)


def ensure_pyinstaller():
    try:
        import PyInstaller  # noqa: F401
        print("PyInstaller already installed.")
    except ImportError:
        run([PYTHON, "-m", "pip", "install", "pyinstaller", "--quiet"])


def collect_static():
    print("\n=== Collecting static files ===")
    run([PYTHON, "manage.py", "collectstatic", "--noinput", "--clear", "--verbosity", "0"])


def build_seeded_database():
    print("\n=== Building pre-seeded database ===")
    dev_db = os.path.join(PROJECT_ROOT, "db.sqlite3")
    backup_db = os.path.join(INSTALLER_DIR, "_db_dev_backup.sqlite3")
    seeded_db = os.path.join(INSTALLER_DIR, "db.sqlite3")

    if os.path.exists(dev_db):
        shutil.move(dev_db, backup_db)
    try:
        run([PYTHON, "manage.py", "migrate", "--run-syncdb"])
        run([PYTHON, "manage.py", "seed_driver_sources", "--segment", "all"])
        if not os.path.exists(dev_db):
            print("migrate did not produce db.sqlite3 at the expected path.")
            sys.exit(1)
        shutil.copy2(dev_db, seeded_db)
        size_kb = os.path.getsize(seeded_db) / 1024
        print(f"Pre-seeded database ready ({size_kb:.0f} KB)")
    finally:
        # Always restore the dev database, whether the build succeeded or not.
        if os.path.exists(dev_db):
            os.remove(dev_db)
        if os.path.exists(backup_db):
            shutil.move(backup_db, dev_db)


def build_main_app():
    print("\n=== Building PCCheckerExtreme.exe + Stop PC Checker Extreme.exe ===")
    # DJANGO_ROOT tells PyInstaller's Django hook where manage.py lives.
    os.environ.setdefault("DJANGO_ROOT", PROJECT_ROOT)
    run(
        [PYTHON, "-m", "PyInstaller", "--noconfirm", "pcc.spec"],
        cwd=INSTALLER_DIR,
    )


def build_installer_exe():
    print("\n=== Building Install PC Checker Extreme.exe ===")
    icon_arg = []
    icon_path = os.path.join(INSTALLER_DIR, "icon.ico")
    if os.path.exists(icon_path):
        icon_arg = ["--icon", icon_path]
    run(
        [
            PYTHON, "-m", "PyInstaller",
            "--noconfirm", "--onefile", "--noconsole",
            "--name", "Install PC Checker Extreme",
            *icon_arg,
            "install.py",
        ],
        cwd=INSTALLER_DIR,
    )


def assemble_distributable():
    print("\n=== Assembling final distributable ===")
    dist_final = os.path.join(INSTALLER_DIR, "dist_final")
    if os.path.isdir(dist_final):
        shutil.rmtree(dist_final)
    os.makedirs(dist_final)

    # The shared app folder (both exes + bundled runtime) from step 4.
    app_src = os.path.join(INSTALLER_DIR, "dist", "PCCheckerExtreme")
    app_dst = os.path.join(dist_final, "app")
    shutil.copytree(app_src, app_dst)

    # Add the payload the app needs at runtime that PyInstaller didn't
    # bundle as code: collected static files and the pre-seeded database.
    shutil.copytree(
        os.path.join(PROJECT_ROOT, "staticfiles"),
        os.path.join(app_dst, "staticfiles"),
    )
    shutil.copy2(
        os.path.join(INSTALLER_DIR, "db.sqlite3"),
        os.path.join(app_dst, "db.sqlite3"),
    )
    icon_path = os.path.join(INSTALLER_DIR, "icon.ico")
    if os.path.exists(icon_path):
        shutil.copy2(icon_path, os.path.join(app_dst, "icon.ico"))

    # The installer exe itself, at the top level next to app/.
    shutil.copy2(
        os.path.join(INSTALLER_DIR, "dist", "Install PC Checker Extreme.exe"),
        os.path.join(dist_final, "Install PC Checker Extreme.exe"),
    )

    zip_path = os.path.join(
        INSTALLER_DIR, f"PCCheckerExtreme-Installer-v{APP_VERSION}.zip"
    )
    if os.path.exists(zip_path):
        os.remove(zip_path)
    print(f"Zipping to {zip_path} ...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(dist_final):
            for name in files:
                full = os.path.join(root, name)
                arcname = os.path.relpath(full, dist_final)
                zf.write(full, arcname)

    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    print(f"\nBUILD COMPLETE\n  {zip_path}\n  {size_mb:.1f} MB\n")
    print("Send that zip to a customer, or test it yourself: extract it")
    print('anywhere and double-click "Install PC Checker Extreme.exe".')


def main():
    ensure_pyinstaller()
    collect_static()
    build_seeded_database()
    build_main_app()
    build_installer_exe()
    assemble_distributable()


if __name__ == "__main__":
    main()
