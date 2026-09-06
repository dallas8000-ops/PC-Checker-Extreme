# PyInstaller spec building both PCCheckerExtreme.exe and
# "Stop PC Checker Extreme.exe" into ONE shared output folder, so they
# share a single bundled Python runtime instead of duplicating it, and so
# Django's BASE_DIR (computed from settings.py's own file location)
# resolves to the same stable folder for both executables.
#
# Build with:  pyinstaller pcc.spec
# (run from the installer/ folder, with the project's venv active)

import os
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

INSTALLER_DIR = os.path.dirname(SPEC)
PROJECT_ROOT = os.path.abspath(os.path.join(INSTALLER_DIR, ".."))

# collect_submodules()/collect_data_files() import the target package for
# real under the hood, and Django's own PyInstaller hook looks for
# manage.py relative to the current working directory to find "the
# project" -- neither works unless the project root is actually on
# sys.path and is the process's cwd, regardless of what directory this
# spec was invoked from.
sys.path.insert(0, PROJECT_ROOT)
os.chdir(PROJECT_ROOT)

# collect_submodules("diagnostics") has to import diagnostics.models, which
# defines Django ORM model classes -- that raises AppRegistryNotReady unless
# Django's app registry is already initialized first. PyInstaller silently
# swallows that exception and just reports "not a package", which is what
# was actually happening here (diagnostics/__init__.py exists just fine --
# this was never really a package-detection problem).
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "pc_checker_extreme.settings")
import django
django.setup()

# Django doesn't statically "import" migration files, app templates, or
# static assets the way PyInstaller's analyzer expects -- collect them
# explicitly so nothing is silently missing at runtime.
hidden = (
    collect_submodules("diagnostics")
    + collect_submodules("pc_checker_extreme")
    # Explicit fallback: collect_submodules("diagnostics") skips diagnostics.services
    # at spec-parse time because AppRegistryNotReady fires before the registry is set up.
    + [
        "diagnostics.services.ai_analyzer",
        "diagnostics.services.cleanup_check",
        "diagnostics.services.driver_lookup",
        "diagnostics.services.extended_diagnostics",
        "diagnostics.services.hardware_collector",
        "diagnostics.services.health_checks",
        "diagnostics.services.oem_detection",
        "diagnostics.services.powershell",
        "diagnostics.services.scan_insights",
        "diagnostics.services.scan_runner",
        "diagnostics.services.scanner",
        "diagnostics.services.software_collector",
    ]
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
    # xhtml2pdf dynamically imports reportlab/svglib submodules at runtime,
    # so PyInstaller's static analysis misses them -- collect recursively.
    + collect_submodules("xhtml2pdf")
    + collect_submodules("reportlab")
    + collect_submodules("svglib")
    # sentry_sdk's integrations (django, logging, stdlib, excepthook, ...) are
    # loaded dynamically by name at sentry_sdk.init() time, so PyInstaller's
    # static analyzer never sees the import and silently drops them otherwise.
    + collect_submodules("sentry_sdk")
    + ["certifi"]
)

datas = (
    collect_data_files("diagnostics")
    + collect_data_files("pc_checker_extreme")
    + collect_data_files("sentry_sdk")
    + collect_data_files("reportlab")
    + collect_data_files("certifi")
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

app_analysis = Analysis([os.path.join(INSTALLER_DIR, "run_app.py")], **common_kwargs)
stop_analysis = Analysis([os.path.join(INSTALLER_DIR, "stop_app.py")], **common_kwargs)

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
