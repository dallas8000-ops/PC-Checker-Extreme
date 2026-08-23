"""Installed software inventory and outdated application detection."""
import json
import re
import sys
from datetime import datetime, timezone

from .powershell import run_powershell

WINGET_TIMEOUT_SEC = 60
WINDOWS_UPDATE_TIMEOUT_SEC = 45


def collect_installed_programs(limit: int = 80) -> dict:
    if sys.platform != "win32":
        return {"programs": [], "count": 0, "note": "Registry scan requires Windows"}

    script = r"""
    $paths = @(
        'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*'
    )
    $apps = foreach ($path in $paths) {
        Get-ItemProperty $path -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName } |
        Select-Object DisplayName, DisplayVersion, Publisher, InstallDate
    }
    $apps | Sort-Object DisplayName -Unique |
    Select-Object -First """ + str(limit) + r""" |
    ConvertTo-Json -Compress
    """
    stdout, _, _ = run_powershell(script, timeout=45)
    programs = []
    if stdout.strip():
        try:
            data = json.loads(stdout)
            programs = data if isinstance(data, list) else [data]
        except json.JSONDecodeError:
            pass

    return {"programs": programs, "count": len(programs)}


def collect_outdated_via_winget() -> dict:
    if sys.platform != "win32":
        return {"available": False, "packages": [], "error": "winget requires Windows"}

    script = """
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) { Write-Output '{"error":"winget not found"}'; exit 0 }
    winget upgrade --disable-interactivity --accept-source-agreements 2>&1
    """
    stdout, stderr, code = run_powershell(script, timeout=WINGET_TIMEOUT_SEC)
    combined = (stdout or "") + "\n" + (stderr or "")

    if code == -1 and "cannot find" in (stderr or "").lower():
        return {
            "available": False,
            "packages": [],
            "error": "PowerShell could not be started. Check that Windows PowerShell is installed.",
        }

    if code == -1 or "Timed out" in (stderr or ""):
        return {
            "available": False,
            "packages": [],
            "error": f"winget timed out after {WINGET_TIMEOUT_SEC}s — try Quick Scan without update checks.",
            "timed_out": True,
        }

    if '{"error":"winget not found"}' in combined:
        return {
            "available": False,
            "packages": [],
            "error": "Windows Package Manager (winget) is not installed.",
        }

    packages = _parse_winget_upgrade_output(combined)
    return {
        "available": True,
        "packages": packages,
        "count": len(packages),
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "raw_excerpt": combined[:2000] if not packages else "",
    }


def _parse_winget_upgrade_output(text: str) -> list[dict]:
    """Parse winget upgrade table output into structured package list."""
    lines = text.splitlines()
    packages = []
    in_table = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if "Name" in stripped and "Id" in stripped and "Version" in stripped:
            in_table = True
            continue
        if stripped.startswith("---") or stripped.startswith("─"):
            continue
        if not in_table:
            continue
        if stripped.lower().startswith("no installed package"):
            break
        if "upgrades available" in stripped.lower():
            continue

        parts = re.split(r"\s{2,}", stripped)
        if len(parts) >= 3:
            name = parts[0].strip()
            pkg_id = parts[1].strip() if len(parts) > 3 else ""
            current = parts[-2].strip() if len(parts) >= 4 else parts[1].strip()
            available = parts[-1].strip()
            packages.append(
                {
                    "name": name,
                    "id": pkg_id or name,
                    "current_version": current,
                    "available_version": available,
                }
            )
        elif len(parts) == 2:
            packages.append(
                {
                    "name": parts[0],
                    "id": parts[0],
                    "current_version": parts[1],
                    "available_version": "update available",
                }
            )

    return packages[:100]


def collect_windows_updates_status() -> dict:
    if sys.platform != "win32":
        return {"available": False}

    script = """
    try {
        $session = New-Object -ComObject Microsoft.Update.Session
        $searcher = $session.CreateUpdateSearcher()
        function Get-PendingUpdates($criteria, $limit) {
            $result = $searcher.Search($criteria)
            $updates = @()
            foreach ($u in $result.Updates | Select-Object -First $limit) {
                $description = $u.Description
                $updates += [ordered]@{
                    Title = $u.Title
                    Description = if ($description) { $description.Substring(0, [Math]::Min(200, $description.Length)) } else { '' }
                    IsMandatory = $u.IsMandatory
                    MaxDownloadSize = $u.MaxDownloadSize
                }
            }
            return $updates
        }
        $updates = @(Get-PendingUpdates "IsInstalled=0 and Type='Software'" 25)
        $drivers = @(Get-PendingUpdates "IsInstalled=0 and Type='Driver'" 25)
        @{ count = $updates.Count; updates = $updates; driver_count = $drivers.Count; drivers = $drivers } | ConvertTo-Json -Depth 4 -Compress
    } catch {
        @{ count = 0; updates = @(); driver_count = 0; drivers = @(); error = $_.Exception.Message } | ConvertTo-Json -Compress
    }
    """
    stdout, stderr, code = run_powershell(script, timeout=WINDOWS_UPDATE_TIMEOUT_SEC)
    if code == -1:
        return {
            "available": False,
            "count": 0,
            "updates": [],
            "driver_count": 0,
            "drivers": [],
            "error": f"Windows Update check failed: {stderr or 'PowerShell error'}",
            "timed_out": "Timed out" in (stderr or ""),
        }
    if not stdout.strip():
        return {"available": False, "count": 0, "updates": [], "driver_count": 0, "drivers": []}
    try:
        data = json.loads(stdout)
        return {"available": True, **data}
    except json.JSONDecodeError:
        return {"available": False, "count": 0, "updates": [], "driver_count": 0, "drivers": []}


def collect_software(
    *,
    include_inventory: bool = False,
    include_slow_checks: bool = False,
) -> dict:
    """
    include_inventory: Control Panel / uninstall-registry program list (not msinfo32).
    include_slow_checks: winget + Windows Update COM (can take 1–2+ minutes).
    Default: system-info-focused scan — no program list unless opted in.
    """
    if include_inventory:
        result = {"installed": collect_installed_programs()}
    else:
        result = {
            "installed": {
                "programs": [],
                "count": 0,
                "skipped": True,
                "note": "Program list skipped — scan used Windows System Information (WMI) only.",
            }
        }
    if include_slow_checks:
        result["outdated_winget"] = collect_outdated_via_winget()
        result["windows_updates"] = collect_windows_updates_status()
    else:
        result["outdated_winget"] = {
            "available": False,
            "packages": [],
            "skipped": True,
            "note": "Enable “Check app & Windows updates” for winget (slower).",
        }
        result["windows_updates"] = {
            "available": False,
            "count": 0,
            "updates": [],
            "skipped": True,
        }
    return result
