"""USB and storage admin tools: live status plus user-confirmed repair actions.

Status collection is read-only and runs as the current user. Some readings
(SMART / reliability counters) need administrator rights; those come back empty
until the user runs the elevated "deep health" action.

Actions mirror remediation.py's safety model: each one is an allowlisted id,
runs only on an explicit POST from the tools page, and is either reversible
(power settings), non-destructive (rescans, read-only volume scans, TRIM) or
explicitly described as requiring a restart. Anything that needs admin rights
goes through a UAC prompt the user must approve.
"""
import base64
import json
import os
import sys
import tempfile

from .powershell import run_powershell
from .remediation import _fail, _is_admin, _ok

# USB selective suspend power setting (subgroup, setting) GUIDs.
_USB_SUBGROUP = "2a737441-1930-4402-8d77-b2bebba308a3"
_USB_SUSPEND = "48e6b7a6-50f5-4782-a5d4-53bb8f07e226"

# Device Manager problem codes (ConfigManagerErrorCode) users actually hit.
PROBLEM_CODES = {
    1: "Device is not configured correctly.",
    3: "Driver may be corrupted, or the system is low on memory.",
    10: "Device cannot start. Usually a driver problem or a failing device/port.",
    12: "Not enough free resources for this device.",
    14: "Restart required for the device to work.",
    18: "Drivers need to be reinstalled.",
    19: "Registry configuration for this device is damaged.",
    21: "Windows is removing this device.",
    22: "Device is disabled.",
    24: "Device is not present, not working, or missing drivers.",
    28: "No driver is installed for this device.",
    29: "Device is disabled in firmware (BIOS/UEFI).",
    31: "Windows cannot load the driver for this device.",
    32: "Driver service is disabled.",
    37: "Driver failed to initialize.",
    39: "Driver is corrupted or missing.",
    41: "Driver loaded but the hardware could not be found.",
    43: "Device reported a problem (common for USB devices that fail to enumerate: "
        "try another port/cable, or the device is failing).",
    45: "Device is not currently connected.",
    48: "Driver blocked because it is known to have problems.",
    52: "Driver is not digitally signed / signature could not be verified.",
}

_USB_ID_PREFIXES = ("USB\\", "USBSTOR\\", "HID\\", "UASPSTOR\\", "SCSI\\", "BTHENUM\\")

_STATUS_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$since = (Get-Date).AddDays(-14)

# Boot times, so events logged in the first minutes after startup (driver
# framework not ready yet, Windows retries) can be told apart from real failures.
$boots = @(Get-WinEvent -FilterHashtable @{ LogName = 'System'; ProviderName = 'Microsoft-Windows-Kernel-General'; Id = 12; StartTime = $since.AddDays(-1) } |
  Select-Object -ExpandProperty TimeCreated | Sort-Object)

function Get-SecondsAfterBoot($t) {
  $b = $boots | Where-Object { $_ -le $t } | Select-Object -Last 1
  if ($b) { [int]($t - $b).TotalSeconds } else { $null }
}

# Every matching event (not just the newest few), grouped by source + id + device
# so counts are real and repeats collapse into one row.
function Get-Events($providers) {
  $all = @()
  foreach ($p in $providers) {
    try {
      $all += Get-WinEvent -FilterHashtable @{ LogName = 'System'; ProviderName = $p; Level = 1,2,3; StartTime = $since } -MaxEvents 2000 -ErrorAction Stop
    } catch {}
  }
  $rows = $all | ForEach-Object {
    $lines = $_.Message -split "`r?`n" | Where-Object { $_.Trim() }
    $deviceLine = $lines | Where-Object { $_ -match '^\s*Device:\s*(.+)$' } | Select-Object -First 1
    $device = if ($deviceLine) { ($deviceLine -replace '^\s*Device:\s*', '').Trim() } else { '' }
    [pscustomobject]@{
      ev = $_; device = $device
      key = "$($_.ProviderName)|$($_.Id)|$device"
      first_line = [string]($lines | Select-Object -First 1)
    }
  }
  $groups = $rows | Group-Object key | ForEach-Object {
    $events = $_.Group | Sort-Object { $_.ev.TimeCreated } -Descending
    $latest = $events[0]
    $afterBoot = @($events | Where-Object { $s = Get-SecondsAfterBoot $_.ev.TimeCreated; $s -ne $null -and $s -le 120 }).Count
    $dev = $null
    if ($latest.device) { $dev = Get-PnpDevice -InstanceId $latest.device -ErrorAction SilentlyContinue }
    $msg = $latest.first_line
    if ($msg.Length -gt 220) { $msg = $msg.Substring(0, 220) + '...' }
    [pscustomobject]@{
      time = $latest.ev.TimeCreated.ToString('yyyy-MM-dd HH:mm')
      provider = $latest.ev.ProviderName
      id = $latest.ev.Id
      level = $latest.ev.LevelDisplayName
      message = $msg
      count = $events.Count
      startup_count = $afterBoot
      device_id = $latest.device
      device_name = if ($dev) { $dev.FriendlyName } else { '' }
      device_status = if ($dev) { [string]$dev.Status } else { '' }
      device_present = if ($dev) { [bool]$dev.Present } else { $null }
    }
  }
  [pscustomobject]@{ total = @($all).Count; groups = @($groups | Sort-Object time -Descending) }
}

$problems = Get-CimInstance Win32_PnPEntity | Where-Object { $_.ConfigManagerErrorCode -ne 0 } | ForEach-Object {
  [pscustomobject]@{
    name = $_.Name
    pnp_class = $_.PNPClass
    instance_id = $_.PNPDeviceID
    code = [int]$_.ConfigManagerErrorCode
  }
}

$controllers = Get-CimInstance Win32_USBController | ForEach-Object {
  [pscustomobject]@{ name = $_.Name; status = $_.Status }
}
$usbCount = @(Get-CimInstance Win32_PnPEntity | Where-Object { $_.PNPDeviceID -like 'USB\*' }).Count

$suspend = (powercfg /query SCHEME_CURRENT __SUB__ __SET__) -join "`n"
$hex = [regex]::Matches($suspend, '0x0000000([01])') | ForEach-Object { [int]$_.Groups[1].Value }

$disks = Get-PhysicalDisk | ForEach-Object {
  $d = $_
  $rc = $d | Get-StorageReliabilityCounter
  [pscustomobject]@{
    device_id = $d.DeviceId
    name = $d.FriendlyName
    media = [string]$d.MediaType
    bus = [string]$d.BusType
    health = [string]$d.HealthStatus
    operational = ($d.OperationalStatus -join ', ')
    size_gb = [math]::Round($d.Size / 1GB, 0)
    temperature = $rc.Temperature
    temperature_max = $rc.TemperatureMax
    wear = $rc.Wear
    read_errors = $rc.ReadErrorsUncorrected
    write_errors = $rc.WriteErrorsUncorrected
    power_on_hours = $rc.PowerOnHours
  }
}

$predict = Get-CimInstance -Namespace root\wmi -ClassName MSStorageDriver_FailurePredictStatus | ForEach-Object {
  [pscustomobject]@{ instance = $_.InstanceName; predict_failure = [bool]$_.PredictFailure; reason = $_.Reason }
}

$volumes = Get-Volume | Where-Object { $_.DriveLetter } | Sort-Object DriveLetter | ForEach-Object {
  [pscustomobject]@{
    letter = [string]$_.DriveLetter
    label = $_.FileSystemLabel
    fs = $_.FileSystem
    drive_type = [string]$_.DriveType
    health = [string]$_.HealthStatus
    size_gb = [math]::Round($_.Size / 1GB, 1)
    free_gb = [math]::Round($_.SizeRemaining / 1GB, 1)
  }
}

[pscustomobject]@{
  usb = [pscustomobject]@{
    problem_devices = @($problems)
    controllers = @($controllers)
    usb_device_count = $usbCount
    selective_suspend_ac = if ($hex.Count -ge 1) { $hex[0] } else { $null }
    selective_suspend_dc = if ($hex.Count -ge 2) { $hex[1] } else { $null }
    events = Get-Events @('Microsoft-Windows-Kernel-PnP','USBHUB3','USBXHCI','Microsoft-Windows-USB-USBHUB3','Microsoft-Windows-USB-USBXHCI')
  }
  storage = [pscustomobject]@{
    disks = @($disks)
    failure_predict = @($predict)
    volumes = @($volumes)
    events = Get-Events @('disk','Ntfs','Microsoft-Windows-Ntfs','stornvme','storahci','volmgr','iaStorAC','iaStorVD','Microsoft-Windows-StorPort')
  }
  is_admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
} | ConvertTo-Json -Depth 5 -Compress
""".replace("__SUB__", _USB_SUBGROUP).replace("__SET__", _USB_SUSPEND)

# Disk event ids that point at real hardware/file-system trouble.
_DISK_EVENT_HINTS = {
    7: ("critical", "Bad block reported on a disk."),
    11: ("critical", "Disk controller error."),
    51: ("warning", "Error during a paging operation (often a failing disk or loose cable)."),
    55: ("critical", "File system structure is corrupt; run a volume scan."),
    98: ("warning", "Volume needs a file-system check."),
    129: ("warning", "Storage controller reset — check cables/firmware."),
    153: ("warning", "Disk I/O had to be retried."),
    157: ("warning", "Disk was surprise-removed."),
}


def _as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _is_usb_device(device: dict) -> bool:
    instance = (device.get("instance_id") or "").upper()
    pnp_class = (device.get("pnp_class") or "").upper()
    return instance.startswith(_USB_ID_PREFIXES) or pnp_class in ("USB", "USBDEVICE", "HIDCLASS")


def _event_groups(events) -> list[dict]:
    """Normalize grouped event output ({total, groups}) or a plain list of events."""
    if isinstance(events, dict):
        groups = _as_list(events.get("groups"))
    else:
        groups = _as_list(events)
    for group in groups:
        group.setdefault("count", 1)
        group.setdefault("startup_count", 0)
    return groups


def _classify_device_event(group: dict) -> tuple[str, str]:
    """Decide whether a repeated PnP warning is a real problem or startup noise."""
    status = (group.get("device_status") or "").upper()
    present = group.get("device_present")
    only_at_startup = group["count"] > 0 and group.get("startup_count", 0) >= group["count"]
    if group.get("device_id") and present and status not in ("OK", ""):
        return "problem", f"Device status is {group.get('device_status')} right now."
    if only_at_startup and (status == "OK" or present is False):
        if present is False:
            return "startup", "Only at startup; device is not connected now."
        return "startup", "Only at startup; device is working now."
    if group.get("device_id") and present is False:
        return "disconnected", "Device is not connected now."
    return "problem", ""


def _finding(severity: str, title: str, message: str, tool: str = "") -> dict:
    return {"severity": severity, "title": title, "message": message, "tool": tool}


def analyze_status(raw: dict) -> dict:
    """Turn raw PowerShell output into findings for the tools page."""
    usb = raw.get("usb") or {}
    storage = raw.get("storage") or {}
    usb_findings, disk_findings = [], []

    problems = _as_list(usb.get("problem_devices"))
    for device in problems:
        code = device.get("code")
        device["explanation"] = PROBLEM_CODES.get(code, f"Device Manager problem code {code}.")
        device["is_usb"] = _is_usb_device(device)
    usb_problems = [d for d in problems if d["is_usb"]]
    other_problems = [d for d in problems if not d["is_usb"]]

    for device in usb_problems:
        severity = "warning" if device.get("code") in (22, 45) else "critical"
        usb_findings.append(
            _finding(
                severity,
                f"{device.get('name') or 'Unknown USB device'} (code {device.get('code')})",
                device["explanation"],
                "usb_restart_problem",
            )
        )
    for controller in _as_list(usb.get("controllers")):
        if (controller.get("status") or "OK").upper() != "OK":
            usb_findings.append(
                _finding(
                    "critical",
                    f"USB controller {controller.get('name')} reports '{controller.get('status')}'",
                    "Rescan hardware; if it persists, update the chipset driver from your motherboard vendor.",
                    "usb_rescan",
                )
            )
    if usb.get("selective_suspend_ac") == 1:
        usb_findings.append(
            _finding(
                "info",
                "USB selective suspend is on",
                "Windows may power down idle USB ports. If devices randomly disconnect or "
                "don't wake up, turn it off.",
                "usb_power_fix",
            )
        )
    usb_events = _event_groups(usb.get("events"))
    for group in usb_events:
        group["verdict"], group["note"] = _classify_device_event(group)
    real = [g for g in usb_events if g["verdict"] == "problem"]
    benign = [g for g in usb_events if g["verdict"] != "problem"]
    if real:
        usb_findings.append(
            _finding(
                "warning",
                f"{sum(g['count'] for g in real)} USB/Plug-and-Play warning(s) for "
                f"{len(real)} device(s) in the last 14 days",
                "These happened outside of startup or the device still has a problem now. "
                "See the event list below.",
                "usb_restart_problem",
            )
        )
    if benign:
        usb_findings.append(
            _finding(
                "info",
                f"{sum(g['count'] for g in benign)} startup-only driver warning(s) — devices working",
                "Logged in the first seconds after Windows starts, before the driver framework is "
                "ready. Windows retries and the devices load normally, so no action is needed.",
            )
        )
    if not usb_findings:
        usb_findings.append(
            _finding("ok", "USB looks healthy", "No USB devices or controllers report problems.")
        )

    disks = _as_list(storage.get("disks"))
    for disk in disks:
        name = disk.get("name") or f"Disk {disk.get('device_id')}"
        if (disk.get("health") or "Healthy") != "Healthy":
            disk_findings.append(
                _finding(
                    "critical",
                    f"{name} health: {disk.get('health')}",
                    "Back up your data now. Windows reports this drive is degraded or failing.",
                    "disk_deep_health",
                )
            )
        if (disk.get("read_errors") or 0) > 0 or (disk.get("write_errors") or 0) > 0:
            disk_findings.append(
                _finding(
                    "critical",
                    f"{name} has uncorrectable read/write errors",
                    f"Read errors: {disk.get('read_errors') or 0}, write errors: {disk.get('write_errors') or 0}. "
                    "Back up important files and plan to replace this drive.",
                )
            )
        wear = disk.get("wear")
        if wear is not None and wear >= 80:
            disk_findings.append(
                _finding("warning", f"{name} is {wear}% worn", "SSD is near the end of its rated life.")
            )
        temp = disk.get("temperature")
        if temp and temp >= 60:
            disk_findings.append(
                _finding("warning", f"{name} is running hot ({temp}°C)", "Improve airflow or add a heatsink.")
            )
    for predict in _as_list(storage.get("failure_predict")):
        if predict.get("predict_failure"):
            disk_findings.append(
                _finding(
                    "critical",
                    "SMART predicts a drive failure",
                    f"Drive {predict.get('instance')} reported a SMART failure prediction. Back up immediately.",
                )
            )

    for volume in _as_list(storage.get("volumes")):
        letter = volume.get("letter")
        if (volume.get("drive_type") or "") not in ("Fixed", "Removable"):
            continue
        if (volume.get("health") or "Healthy") != "Healthy":
            disk_findings.append(
                _finding(
                    "critical",
                    f"Volume {letter}: health {volume.get('health')}",
                    "File-system errors detected. Run the volume scan, then the repair if issues are found.",
                    "disk_fix_errors",
                )
            )
        size, free = volume.get("size_gb") or 0, volume.get("free_gb") or 0
        if size and free / size < 0.10:
            disk_findings.append(
                _finding(
                    "warning",
                    f"Volume {letter}: only {free} GB free",
                    "Less than 10% free space slows Windows and blocks updates.",
                )
            )

    disk_events = _event_groups(storage.get("events"))
    for event in disk_events:
        hint = _DISK_EVENT_HINTS.get(event.get("id"))
        if hint and event.get("provider", "").lower() in ("disk", "ntfs", "microsoft-windows-ntfs", "stornvme", "storahci", "iastorac", "iastorvd"):
            event["hint"] = hint[1]
    flagged = [e for e in disk_events if e.get("hint")]
    if flagged:
        worst = "critical" if any(_DISK_EVENT_HINTS[e["id"]][0] == "critical" for e in flagged) else "warning"
        disk_findings.append(
            _finding(
                worst,
                f"{sum(e['count'] for e in flagged)} disk error event(s) in the last 14 days",
                "; ".join(sorted({e["hint"] for e in flagged})),
                "disk_scan",
            )
        )

    if not any(d.get("temperature") is not None for d in disks) and not raw.get("is_admin"):
        disk_findings.append(
            _finding(
                "info",
                "SMART details need administrator rights",
                "Run 'Deep drive health' to read temperature, wear and error counters.",
                "disk_deep_health",
            )
        )
    if not any(f["severity"] in ("critical", "warning") for f in disk_findings):
        disk_findings.insert(
            0, _finding("ok", "Drives look healthy", "All physical disks and volumes report Healthy.")
        )

    return {
        "usb": {**usb, "problem_devices": usb_problems, "events": usb_events,
                "event_total": sum(g["count"] for g in usb_events), "findings": usb_findings},
        "storage": {**storage, "disks": disks, "events": disk_events,
                    "event_total": sum(e["count"] for e in disk_events), "findings": disk_findings},
        "other_problem_devices": other_problems,
        "is_admin": bool(raw.get("is_admin")),
    }


def collect_status() -> dict:
    """Read-only USB + storage snapshot for the tools page."""
    if sys.platform != "win32":
        return {"supported": False, "error": "Device tools need the app running on Windows."}
    out, err, code = run_powershell(_STATUS_SCRIPT, timeout=90)
    try:
        raw = json.loads(out.strip().splitlines()[-1]) if out.strip() else {}
    except (json.JSONDecodeError, IndexError):
        raw = {}
    if not raw:
        return {"supported": True, "error": f"Could not read device status. {err.strip()[:300]}"}
    return {"supported": True, "error": "", **analyze_status(raw)}


def _run_elevated_output(script: str, timeout: int = 300) -> tuple[bool, str]:
    """Run a script through a UAC prompt and return (completed, captured output)."""
    if _is_admin():
        out, err, code = run_powershell(script, timeout=timeout)
        return code != -1, (out or err).strip()

    result_file = tempfile.mktemp(prefix="pcc-tool-", suffix=".txt")
    wrapped = (
        f"$__r = & {{ {script} }} *>&1 | Out-String -Width 200\n"
        f"Set-Content -LiteralPath {json.dumps(result_file)} -Value $__r -Encoding UTF8"
    )
    encoded = base64.b64encode(wrapped.encode("utf-16le")).decode("ascii")
    launch = (
        "Start-Process powershell.exe -Verb RunAs -Wait -WindowStyle Hidden "
        f"-ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-EncodedCommand','{encoded}'"
    )
    try:
        _, err, code = run_powershell(launch, timeout=timeout)
        if code != 0 or not os.path.isfile(result_file):
            return False, err.strip() or "The administrator prompt was cancelled or the action did not finish."
        with open(result_file, encoding="utf-8-sig", errors="replace") as fh:
            return True, fh.read().strip()
    finally:
        try:
            os.remove(result_file)
        except OSError:
            pass


def _elevated_tool(script: str, done_message: str, timeout: int = 300, **extra) -> dict:
    ok, output = _run_elevated_output(script, timeout=timeout)
    if not ok:
        return _fail(output, needs_admin=True)
    return _ok(done_message, output=output[-6000:], **extra)


def tool_usb_rescan() -> dict:
    return _elevated_tool(
        "pnputil /scan-devices",
        "Windows rescanned for hardware. Unplug and replug any device that still isn't detected.",
        timeout=120,
    )


def tool_usb_restart_problem() -> dict:
    script = r"""
    $ids = Get-CimInstance Win32_PnPEntity | Where-Object {
      $_.ConfigManagerErrorCode -ne 0 -and $_.ConfigManagerErrorCode -ne 22 -and
      ($_.PNPDeviceID -match '^(USB|USBSTOR|HID|UASPSTOR|BTHENUM)\\' -or $_.PNPClass -in 'USB','USBDevice','HIDClass')
    } | Select-Object -ExpandProperty PNPDeviceID
    if (-not $ids) { 'No USB devices with problems were found.'; return }
    foreach ($id in $ids) { "== $id"; pnputil /restart-device "$id" }
    pnputil /scan-devices
    """
    return _elevated_tool(
        script,
        "Restarted USB devices that reported problems and rescanned hardware. Re-check the list below.",
        timeout=180,
    )


def _set_usb_suspend(value: int) -> tuple[bool, str]:
    script = (
        f"powercfg /setacvalueindex SCHEME_CURRENT {_USB_SUBGROUP} {_USB_SUSPEND} {value}; "
        f"powercfg /setdcvalueindex SCHEME_CURRENT {_USB_SUBGROUP} {_USB_SUSPEND} {value}; "
        "powercfg /setactive SCHEME_CURRENT; if ($LASTEXITCODE -ne 0) { exit 1 }"
    )
    _, err, code = run_powershell(script, timeout=30)
    if code == 0:
        return True, ""
    return _run_elevated_output(script, timeout=60)


def tool_usb_power_fix() -> dict:
    ok, err = _set_usb_suspend(0)
    if not ok:
        return _fail(f"Could not change the power plan: {err}")
    return _ok("USB selective suspend is now off for the active power plan (plugged in and on battery).")


def tool_usb_power_restore() -> dict:
    ok, err = _set_usb_suspend(1)
    if not ok:
        return _fail(f"Could not change the power plan: {err}")
    return _ok("USB selective suspend is back on (Windows default).")


def tool_disk_deep_health() -> dict:
    script = r"""
    Get-PhysicalDisk | ForEach-Object {
      $rc = $_ | Get-StorageReliabilityCounter
      [pscustomobject]@{
        Disk = $_.FriendlyName; Health = $_.HealthStatus; Media = $_.MediaType
        TempC = $rc.Temperature; MaxTempC = $rc.TemperatureMax; WearPct = $rc.Wear
        ReadErrors = $rc.ReadErrorsUncorrected; WriteErrors = $rc.WriteErrorsUncorrected
        PowerOnHours = $rc.PowerOnHours; StartStops = $rc.StartStopCycleCount
      }
    } | Format-List
    'SMART failure prediction:'
    Get-CimInstance -Namespace root\wmi -ClassName MSStorageDriver_FailurePredictStatus |
      Select-Object InstanceName, PredictFailure | Format-Table -AutoSize
    """
    return _elevated_tool(script, "Read drive health counters with administrator rights.", timeout=120)


def tool_disk_scan() -> dict:
    script = r"""
    Get-Volume | Where-Object { $_.DriveLetter -and $_.DriveType -eq 'Fixed' -and $_.FileSystem -in 'NTFS','ReFS' } |
      ForEach-Object { "Volume $($_.DriveLetter): " + (Repair-Volume -DriveLetter $_.DriveLetter -Scan) }
    """
    return _elevated_tool(
        script,
        "Online scan finished (read-only, nothing was changed). 'NoErrorsFound' means the volume is clean.",
        timeout=900,
    )


def tool_disk_fix_errors() -> dict:
    script = r"""
    Get-Volume | Where-Object { $_.DriveLetter -and $_.DriveType -eq 'Fixed' -and $_.FileSystem -in 'NTFS','ReFS' } |
      ForEach-Object {
        $scan = Repair-Volume -DriveLetter $_.DriveLetter -Scan
        if ("$scan" -eq 'NoErrorsFound') { "Volume $($_.DriveLetter): no errors, skipped"; return }
        "Volume $($_.DriveLetter): $scan -> " + (Repair-Volume -DriveLetter $_.DriveLetter -SpotFix)
      }
    """
    return _elevated_tool(
        script,
        "Repair ran on volumes that had errors. If the system drive needed it, restart your PC to finish.",
        timeout=900,
        reboot_required=True,
    )


def tool_disk_optimize() -> dict:
    script = r"""
    $media = @{}
    Get-PhysicalDisk | ForEach-Object { $media[[string]$_.DeviceId] = [string]$_.MediaType }
    Get-Volume | Where-Object { $_.DriveLetter -and $_.DriveType -eq 'Fixed' } | ForEach-Object {
      $num = ($_ | Get-Partition | Select-Object -First 1).DiskNumber
      if ($media["$num"] -eq 'SSD') {
        Optimize-Volume -DriveLetter $_.DriveLetter -ReTrim -Verbose
      } else {
        Optimize-Volume -DriveLetter $_.DriveLetter -Analyze -Verbose
      }
    }
    """
    return _elevated_tool(
        script,
        "SSDs were trimmed; hard drives were analyzed for fragmentation (see output).",
        timeout=900,
    )


def tool_open_device_manager() -> dict:
    run_powershell("Start-Process devmgmt.msc", timeout=20)
    return _ok("Opened Device Manager.")


def tool_open_disk_management() -> dict:
    run_powershell("Start-Process diskmgmt.msc", timeout=20)
    return _ok("Opened Disk Management (Windows may ask for administrator approval).")


TOOL_REGISTRY = {
    "usb_rescan": {
        "group": "usb", "title": "Rescan hardware", "admin": True,
        "description": "Ask Windows to detect devices again (same as Device Manager → Scan for hardware changes).",
        "handler": tool_usb_rescan,
    },
    "usb_restart_problem": {
        "group": "usb", "title": "Restart problem USB devices", "admin": True,
        "description": "Restarts each USB/HID device that reports an error, then rescans. Disabled devices are left alone.",
        "handler": tool_usb_restart_problem,
    },
    "usb_power_fix": {
        "group": "usb", "title": "Stop USB ports sleeping", "admin": False,
        "description": "Turns off USB selective suspend. Fixes devices that randomly disconnect. Reversible.",
        "handler": tool_usb_power_fix,
    },
    "usb_power_restore": {
        "group": "usb", "title": "Restore USB power default", "admin": False,
        "description": "Turns USB selective suspend back on (Windows default).",
        "handler": tool_usb_power_restore,
    },
    "open_device_manager": {
        "group": "usb", "title": "Open Device Manager", "admin": False,
        "description": "Opens Windows Device Manager for manual driver work.",
        "handler": tool_open_device_manager,
    },
    "disk_deep_health": {
        "group": "storage", "title": "Deep drive health", "admin": True,
        "description": "Reads SMART temperature, wear, error counters and failure prediction.",
        "handler": tool_disk_deep_health,
    },
    "disk_scan": {
        "group": "storage", "title": "Scan volumes for errors", "admin": True,
        "description": "Online file-system check of every fixed drive. Read-only; nothing is changed.",
        "handler": tool_disk_scan,
    },
    "disk_fix_errors": {
        "group": "storage", "title": "Repair volume errors", "admin": True,
        "description": "Scans each drive and spot-fixes only the ones with errors. May need a restart for C:.",
        "handler": tool_disk_fix_errors, "confirm": True,
    },
    "disk_optimize": {
        "group": "storage", "title": "Optimize drives", "admin": True,
        "description": "TRIM for SSDs; fragmentation analysis for hard drives.",
        "handler": tool_disk_optimize,
    },
    "open_disk_management": {
        "group": "storage", "title": "Open Disk Management", "admin": True,
        "description": "Opens Windows Disk Management to view partitions and drive letters.",
        "handler": tool_open_disk_management,
    },
}


def tools_for(group: str) -> list[dict]:
    return [
        {"id": tool_id, **{k: v for k, v in entry.items() if k != "handler"}}
        for tool_id, entry in TOOL_REGISTRY.items()
        if entry["group"] == group
    ]


def run_tool(tool_id: str) -> dict:
    entry = TOOL_REGISTRY.get(tool_id)
    if not entry:
        return _fail(f"Unknown tool '{tool_id}'.")
    if sys.platform != "win32":
        return _fail("Device tools need the app running on Windows.")
    try:
        return entry["handler"]()
    except Exception as exc:  # never let a tool crash the request
        return _fail(f"Tool failed with an unexpected error: {exc}")
