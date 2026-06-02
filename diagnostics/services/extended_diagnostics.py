"""SMART, temperatures, security, startup, benchmark, driver analysis."""
import json
import sys
import time

from .powershell import run_powershell, run_powershell_stdout


def collect_smart_health() -> dict:
    if sys.platform != "win32":
        return {"available": False, "disks": []}

    script = """
    $out = @()
    Get-PhysicalDisk -ErrorAction SilentlyContinue | ForEach-Object {
      $rel = $_ | Get-StorageReliabilityCounter -ErrorAction SilentlyContinue
      $out += [ordered]@{
        FriendlyName = $_.FriendlyName
        MediaType = $_.MediaType
        HealthStatus = $_.HealthStatus
        OperationalStatus = $_.OperationalStatus
        SizeGB = [math]::Round($_.Size/1GB, 2)
        Temperature = $rel.Temperature
        Wear = $rel.Wear
        ReadErrorsTotal = $rel.ReadErrorsTotal
        WriteErrorsTotal = $rel.WriteErrorsTotal
      }
    }
    if ($out.Count -eq 0) { '[]' } else { $out | ConvertTo-Json -Compress }
    """
    raw = run_powershell_stdout(script, timeout=60)
    disks = []
    if raw:
        try:
            data = json.loads(raw)
            disks = data if isinstance(data, list) else [data]
        except json.JSONDecodeError:
            pass
    return {"available": bool(disks), "disks": disks}


def collect_temperatures() -> dict:
    if sys.platform != "win32":
        return {"available": False, "sensors": []}

    script = """
    $sensors = @()
  # ACPI thermal zones (may be empty on desktops)
    Get-CimInstance MSAcpi_ThermalZoneTemperature -ErrorAction SilentlyContinue | ForEach-Object {
      $c = ($_.CurrentTemperature / 10) - 273.15
      $sensors += [ordered]@{ Name = 'Thermal zone'; Type = 'ACPI'; Celsius = [math]::Round($c, 1) }
    }
  # Performance counters
    $cpu = Get-CimInstance Win32_PerfFormattedData_Counters_ThermalZoneInformation_ThermalZoneInfo -EA SilentlyContinue |
      Select-Object -First 1
    if ($cpu) {
      $sensors += [ordered]@{ Name = 'CPU thermal'; Type = 'PerfCounter'; Celsius = $cpu.HighPrecisionTemperature }
    }
    if ($sensors.Count -eq 0) { '[]' } else { $sensors | ConvertTo-Json -Compress }
    """
    raw = run_powershell_stdout(script, timeout=45)
    sensors = []
    if raw:
        try:
            data = json.loads(raw)
            sensors = data if isinstance(data, list) else [data]
        except json.JSONDecodeError:
            pass
    return {
        "available": bool(sensors),
        "sensors": sensors,
        "note": "Limited without GPU tools (e.g. HWiNFO). ACPI/perf counters only.",
    }


def collect_security_status() -> dict:
    if sys.platform != "win32":
        return {"available": False}

    script = """
    $def = $null
    try { $def = Get-MpComputerStatus | Select-Object AMServiceEnabled, AntispywareEnabled, RealTimeProtectionEnabled, IoavProtectionEnabled } catch {}
    $fw = Get-NetFirewallProfile | Select-Object Name, Enabled
  @{ defender = $def; firewall = $fw } | ConvertTo-Json -Depth 4 -Compress
    """
    raw = run_powershell_stdout(script, timeout=45)
    if not raw:
        return {"available": False}
    try:
        return {"available": True, **json.loads(raw)}
    except json.JSONDecodeError:
        return {"available": False}


def collect_startup_programs() -> dict:
    if sys.platform != "win32":
        return {"programs": []}

    script = """
    Get-CimInstance Win32_StartupCommand -ErrorAction SilentlyContinue |
    Select-Object Name, Command, Location, User |
    ConvertTo-Json -Compress
    """
    raw = run_powershell_stdout(script, timeout=45)
    programs = []
    if raw:
        try:
            data = json.loads(raw)
            programs = data if isinstance(data, list) else [data]
        except json.JSONDecodeError:
            pass
    return {"programs": programs[:40], "count": len(programs)}


def collect_benchmark() -> dict:
    """Lightweight CPU + disk micro-benchmark (seconds)."""
    import psutil

    t0 = time.perf_counter()
    _ = sum(i * i for i in range(300_000))
    cpu_sec = round(time.perf_counter() - t0, 3)

    disk_sec = None
    disk_note = ""
    try:
        import tempfile

        path = tempfile.NamedTemporaryFile(delete=True)
        t1 = time.perf_counter()
        with open(path.name, "wb") as f:
            f.write(b"0" * (4 * 1024 * 1024))
            f.flush()
        disk_sec = round(time.perf_counter() - t1, 3)
        path.close()
    except OSError as exc:
        disk_note = str(exc)

    cpu_score = max(0, min(100, int(100 - (cpu_sec - 0.02) * 200)))
    disk_score = max(0, min(100, int(100 - (disk_sec or 1) * 25))) if disk_sec else None

    return {
        "cpu_seconds": cpu_sec,
        "cpu_score": cpu_score,
        "disk_write_4mb_seconds": disk_sec,
        "disk_score": disk_score,
        "disk_note": disk_note,
        "ram_total_gb": round(psutil.virtual_memory().total / (1024**3), 1),
    }


def analyze_duplicate_drivers(drivers: list[dict]) -> list[dict]:
    """Flag duplicate or conflicting driver names."""
    seen = {}
    duplicates = []
    for drv in drivers:
        name = (drv.get("DeviceName") or drv.get("name") or "").lower()
        if not name:
            continue
        key = name[:40]
        if key in seen:
            duplicates.append(
                {
                    "device": drv.get("DeviceName") or drv.get("name"),
                    "conflicts_with": seen[key],
                    "class": drv.get("DeviceClass") or drv.get("details", {}).get("class"),
                }
            )
        else:
            seen[key] = drv.get("DeviceName") or drv.get("name")
    return duplicates[:20]


def driver_update_url(device_name: str, manufacturer: str = "") -> str:
    """Best-effort update link for a driver/device."""
    text = f"{device_name} {manufacturer}".lower()
    if "nvidia" in text or "geforce" in text or "rtx" in text:
        return "https://www.nvidia.com/Download/index.aspx"
    if "amd" in text or "radeon" in text:
        return "https://www.amd.com/en/support"
    if "intel" in text:
        return "https://www.intel.com/content/www/us/en/download-center/home.html"
    if "realtek" in text:
        return "https://www.realtek.com/en/downloads"
    if "marvell" in text or "storage" in text or "samsung" in text:
        return "https://www.microsoft.com/en-us/windows/windows-update"
    return "https://www.microsoft.com/en-us/windows/windows-update"


def build_winget_batch_command(packages: list[dict]) -> str:
    if not packages:
        return ""
    ids = [p.get("id") or p.get("name") for p in packages[:15] if p.get("id") or p.get("name")]
    if not ids:
        return "winget upgrade --all --disable-interactivity"
    lines = ["winget upgrade --disable-interactivity"] + [
        f'winget upgrade --id "{pid}"' for pid in ids
    ]
    return " && ".join(lines)


def enrich_drivers_with_links(components: list[dict]) -> list[dict]:
    for c in components:
        if c.get("category") != "Drivers":
            continue
        c.setdefault("details", {})["update_url"] = driver_update_url(
            c.get("name", ""), c.get("manufacturer", "")
        )
    return components
