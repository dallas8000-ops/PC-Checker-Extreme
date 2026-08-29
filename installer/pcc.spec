# PyInstaller spec building both PCCheckerExtreme.exe and
# "Stop PC Checker Extreme.exe" into ONE shared output folder, so they
# share a single bundled Python runtime instead of duplicating it, and so
# Django's BASE_DIR (computed from settings.py's own file location)
# resolves to the same stable folder for both executables.
#
# Build with:  pyinstaller pcc.spec
# (run from the installer/ folder, with the project's venv active)

import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(SPEC), ".."))

# Django doesn't statically "import" migration files, app templates, or
# static assets the way PyInstaller's analyzer expects -- collect them
# explicitly so nothing is silently missing at runtime.
hidden = (
    collect_submodules("diagnostics")
    + collect_submodules("pc_checker_extreme")
    + [
        "whitenoise.middleware",
        "whitenoise.storage",
        "dj_database_url",
        "dotenv",
        "psutil",
        "psycopg2",
        "xhtml2pdf",
        "openai",
        "wmi",
        "win32timezone",  # commonly needed by pywin32 even when not imported directly
    ]
)

datas = (
    collect_data_files("diagnostics")
    + [(os.path.join(PROJECT_ROOT, "manage.py"), ".")]
)

common_kwargs = dict(
    pathex=[PROJECT_ROOT],
    hiddenimports=hidden,
    datas=datas,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

app_analysis = Analysis(["run_app.py"], **common_kwargs)
stop_analysis = Analysis(["stop_app.py"], **common_kwargs)

MERGE(
    (app_analysis, "run_app", "PCCheckerExtreme"),
    (stop_analysis, "stop_app", "Stop PC Checker Extreme"),
)

app_pyz = PYZ(app_analysis.pure, app_analysis.zipped_data)
app_exe = EXE(
    app_pyz,
    app_analysis.scripts,
    [],
    exclude_binaries=True,
    name="PCCheckerExtreme",
    console=False,
    icon="icon.ico" if os.path.exists(os.path.join(os.path.dirname(SPEC), "icon.ico")) else None,
)

stop_pyz = PYZ(stop_analysis.pure, stop_analysis.zipped_data)
stop_exe = EXE(
    stop_pyz,
    stop_analysis.scripts,
    [],
    exclude_binaries=True,
    name="Stop PC Checker Extreme",
    console=False,
    icon="icon.ico" if os.path.exists(os.path.join(os.path.dirname(SPEC), "icon.ico")) else None,
)

coll = COLLECT(
    app_exe,
    app_analysis.binaries,
    app_analysis.zipfiles,
    app_analysis.datas,
    stop_exe,
    stop_analysis.binaries,
    stop_analysis.zipfiles,
    stop_analysis.datas,
    name="PCCheckerExtreme",
)
