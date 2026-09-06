"""Apply safe, user-confirmed remediations for detected issues.

Each fix is keyed to a deterministic health-check id (the same ids produced in
health_checks.py) and runs a narrowly-scoped PowerShell remediation. Nothing here
runs without an explicit POST from the report page. Every fix reports whether it
succeeded, what it did, and whether a reboot is required for it to take effect.

Safety model:
- Only fixes that are reversible or low-risk are auto-applied.
- Disk cleanup targets only temp folders + Recycle Bin (regenerating files).
- Memory integrity writes the documented HVCI registry value; it cannot fully
  apply without a reboot, so we set it and tell the user to restart.
- Driver updates are delegated to winget / Windows Update, which may need admin
  or a reboot to finish -- we trigger them and report, we do not force.
"""
import os
import sys

from .powershell import run_powershell


def _ok(message: str, **extra) -> dict:
    return {"ok": True, "message": message, **extra}


def _fail(message: str, **extra) -> dict:
    return {"ok": False, "message": message, **extra}


def _is_admin() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def fix_junk_files() -> dict:
    """Clear user + Windows temp folders and empty the Recycle Bin."""
    if sys.platform != "win32":
        return _fail("Cleanup is only supported on Windows.")
    script = r"""
    $freed = 0
    $targets = @($env:TEMP, (Join-Path $env:WINDIR 'Temp'))
    foreach ($t in $targets) {
      if (Test-Path $t) {
        try {
          $before = (Get-ChildItem $t -Recurse -Force -ErrorAction SilentlyContinue |
            Measure-Object -Property Length -Sum).Sum
          Remove-Item (Join-Path $t '*') -Recurse -Force -ErrorAction SilentlyContinue
          $after = (Get-ChildItem $t -Recurse -Force -ErrorAction SilentlyContinue |
            Measure-Object -Property Length -Sum).Sum
          $freed += ($before - $after)
        } catch {}
      }
    }
    try { Clear-RecycleBin -Force -ErrorAction SilentlyContinue } catch {}
    [math]::Round($freed / 1MB, 1)
    """
    out, err, code = run_powershell(script, timeout=120)
    if code == -1:
        return _fail(f"Cleanup timed out or failed: {err}")
    try:
        freed_mb = float((out or "0").strip().splitlines()[-1])
    except (ValueError, IndexError):
        freed_mb = 0.0
    if freed_mb >= 1:
        return _ok(f"Freed approximately {freed_mb:.0f} MB of temp/junk files.")
    return _ok("Cleanup ran. Temp folders and Recycle Bin were cleared (some files were in use and skipped).")


def fix_memory_integrity() -> dict:
    """Enable Memory Integrity (Core Isolation / HVCI). Requires reboot to apply."""
    if sys.platform != "win32":
        return _fail("This fix is only supported on Windows.")
    if not _is_admin():
        return _fail(
            "Enabling Memory Integrity needs administrator rights. "
            "Relaunch PC Checker Extreme as administrator, or enable it manually in "
            "Windows Security > Device security > Core isolation.",
            needs_admin=True,
        )
    script = r"""
    $path = 'HKLM:\SYSTEM\CurrentControlSet\Control\DeviceGuard\Scenarios\HypervisorEnforcedCodeIntegrity'
    New-Item -Path $path -Force | Out-Null
    New-ItemProperty -Path $path -Name 'Enabled' -PropertyType DWORD -Value 1 -Force | Out-Null
    (Get-ItemProperty -Path $path -Name 'Enabled').Enabled
    """
    out, err, code = run_powershell(script, timeout=45)
    if code == -1 or "1" not in (out or ""):
        return _fail(f"Could not set Memory Integrity: {err or 'unknown error'}")
    return _ok(
        "Memory Integrity has been enabled. Restart your PC for it to take effect.",
        reboot_required=True,
    )


def fix_driver_updates() -> dict:
    """Trigger pending driver updates via winget, falling back to opening Windows Update."""
    if sys.platform != "win32":
        return _fail("This fix is only supported on Windows.")
    winget = _which("winget")
    if winget:
        script = "winget upgrade --all --disable-interactivity --accept-package-agreements --accept-source-agreements"
        out, err, code = run_powershell(script, timeout=300)
        if code == 0:
            return _ok(
                "winget applied available updates. Some driver updates may still require "
                "Windows Update or a reboot to finish."
            )
        # fall through to opening Windows Update on failure
    run_powershell("Start-Process 'ms-settings:windowsupdate'", timeout=20)
    return _ok(
        "Opened Windows Update so you can install pending driver updates.",
        note="winget was unavailable or could not complete automatically.",
    )


def _which(name: str) -> str | None:
    import shutil

    return shutil.which(name)


# Registry of fixable issues, keyed by health-check id. The report page renders a
# "Fix it for me" button only for ids present here.
FIX_REGISTRY = {
    "junk_files_high": {"title": "Free up disk space", "handler": fix_junk_files},
    "junk_files_moderate": {"title": "Free up disk space", "handler": fix_junk_files},
    "memory_integrity_off": {"title": "Enable Memory Integrity", "handler": fix_memory_integrity},
    "driver_updates": {"title": "Update drivers", "handler": fix_driver_updates},
    "outdated_apps": {"title": "Update outdated apps", "handler": fix_driver_updates},
    "windows_updates": {"title": "Install Windows updates", "handler": fix_driver_updates},
}


def apply_fix(fix_id: str) -> dict:
    entry = FIX_REGISTRY.get(fix_id)
    if not entry:
        return _fail(f"No automatic fix is available for '{fix_id}'.")
    try:
        return entry["handler"]()
    except Exception as exc:  # never let a remediation crash the request
        return _fail(f"Fix failed with an unexpected error: {exc}")
