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


def collect_crash_dumps() -> dict:
    """BSOD / minidump analysis: recent crashes are the top "my PC is broken" complaint."""
    if sys.platform != "win32":
        return {"available": False, "count": 0, "dumps": [], "bugchecks": []}

    script = r"""
    $dumpDir = Join-Path $env:SystemRoot 'Minidump'
    $dumps = @()
    if (Test-Path $dumpDir) {
      $dumps = Get-ChildItem $dumpDir -Filter *.dmp -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 10 Name, @{n='SizeKB';e={[math]::Round($_.Length/1KB,1)}},
          @{n='When';e={$_.LastWriteTime.ToString('o')}}
    }
    $bugchecks = @()
    try {
      $bugchecks = Get-WinEvent -FilterHashtable @{ LogName='System'; Id=1001 } -MaxEvents 10 -ErrorAction Stop |
        Where-Object { $_.Message -match 'bugcheck|blue screen|0x[0-9A-Fa-f]+' } |
        Select-Object @{n='When';e={$_.TimeCreated.ToString('o')}},
          @{n='Message';e={ ($_.Message -split "`n")[0].Substring(0, [Math]::Min(160, ($_.Message -split "`n")[0].Length)) }}
    } catch {}
    @{ dumps = $dumps; bugchecks = $bugchecks } | ConvertTo-Json -Depth 4 -Compress
    """
    raw = run_powershell_stdout(script, timeout=45)
    if not raw:
        return {"available": False, "count": 0, "dumps": [], "bugchecks": []}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"available": False, "count": 0, "dumps": [], "bugchecks": []}
    dumps = data.get("dumps") or []
    if isinstance(dumps, dict):
        dumps = [dumps]
    bugchecks = data.get("bugchecks") or []
    if isinstance(bugchecks, dict):
        bugchecks = [bugchecks]
    return {
        "available": True,
        "count": len(dumps),
        "dumps": dumps,
        "bugchecks": bugchecks,
    }


def collect_smart_raw_attributes() -> dict:
    """Failure-prediction flags + raw wear counters — catches failing drives earlier than
    the coarse HealthStatus string."""
    if sys.platform != "win32":
        return {"available": False, "disks": []}

    script = """
    $out = @()
    Get-PhysicalDisk -ErrorAction SilentlyContinue | ForEach-Object {
      $pd = $_
      $rel = $pd | Get-StorageReliabilityCounter -ErrorAction SilentlyContinue
      $predict = $false
      try {
        $fp = Get-CimInstance -Namespace root\\wmi -ClassName MSStorageDriver_FailurePredictStatus `
          -ErrorAction Stop | Where-Object { $_.InstanceName -like \"*$($pd.DeviceId)*\" } | Select-Object -First 1
        if ($fp) { $predict = [bool]$fp.PredictFailure }
      } catch {}
      $out += [ordered]@{
        FriendlyName = $pd.FriendlyName
        MediaType = $pd.MediaType
        PredictFailure = $predict
        Temperature = $rel.Temperature
        Wear = $rel.Wear
        PowerOnHours = $rel.PowerOnHours
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
    risky = [d for d in disks if d.get("PredictFailure") or (d.get("Wear") or 0) >= 80]
    return {"available": bool(disks), "disks": disks, "at_risk": risky}


def collect_virtualization_security() -> dict:
    """Memory integrity (Core Isolation / HVCI) — a common security gap Windows flags."""
    if sys.platform != "win32":
        return {"available": False}

    script = """
    try {
      $dg = Get-CimInstance -Namespace root\\Microsoft\\Windows\\DeviceGuard -ClassName Win32_DeviceGuard -ErrorAction Stop
      @{
        available = $true
        memory_integrity = ($dg.SecurityServicesRunning -contains 2)
        vbs_running = ($dg.VirtualizationBasedSecurityStatus -eq 2)
        secure_boot_on = $false
      } | ConvertTo-Json -Compress
    } catch {
      @{ available = $false } | ConvertTo-Json -Compress
    }
    """
    raw = run_powershell_stdout(script, timeout=45)
    if not raw:
        return {"available": False}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"available": False}


def collect_secure_boot_tpm() -> dict:
    """Secure Boot + TPM 2.0 — Windows 11 readiness and security baseline."""
    if sys.platform != "win32":
        return {"available": False}

    script = """
    $sb = $null
    try { $sb = Confirm-SecureBootUEFI } catch {}
    $tpm = $null
    try {
      $t = Get-Tpm -ErrorAction Stop
      $tpm = @{
        present = $true
        ready = $t.TpmReady
        enabled = $t.TpmEnabled
        activated = $t.TpmActivated
        owned = $t.TpmOwned
      }
    } catch {
      $tpm = @{ present = $false }
    }
    $spec = $null
    try {
      $spec = (Get-CimInstance -Namespace root\\cimv2\\security\\microsofttpm -ClassName Win32_Tpm -ErrorAction Stop).SpecVersion
    } catch {}
    @{ secure_boot = $sb; tpm = $tpm; tpm_spec = $spec } | ConvertTo-Json -Depth 4 -Compress
    """
    raw = run_powershell_stdout(script, timeout=45)
    if not raw:
        return {"available": False}
    try:
        return {"available": True, **json.loads(raw)}
    except json.JSONDecodeError:
        return {"available": False}


def collect_page_file() -> dict:
    """Page file health — missing/misconfigured pagefiles cause crashes and slowdowns."""
    if sys.platform != "win32":
        return {"available": False}

    script = """
    $usage = Get-CimInstance Win32_PageFileUsage -ErrorAction SilentlyContinue |
      Select-Object Name, AllocatedBaseSize, CurrentUsage, PeakUsage
    $setting = Get-CimInstance Win32_PageFileSetting -ErrorAction SilentlyContinue |
      Select-Object Name, InitialSize, MaximumSize
    $cs = Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue |
      Select-Object AutomaticManagedPagefile
    @{
      managed = [bool]$cs.AutomaticManagedPagefile
      usage = @($usage)
      settings = @($setting)
    } | ConvertTo-Json -Depth 4 -Compress
    """
    raw = run_powershell_stdout(script, timeout=45)
    if not raw:
        return {"available": False}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"available": False}
    usage = data.get("usage") or []
    settings = data.get("settings") or []
    return {
        "available": True,
        "managed": data.get("managed", False),
        "configured": bool(usage or settings),
        "usage": usage,
        "settings": settings,
    }


def collect_cpu_throttling() -> dict:
    """Thermal/power throttling — compares current clock to base clock."""
    if sys.platform != "win32":
        return {"available": False}

    script = """
    Get-CimInstance Win32_Processor -ErrorAction SilentlyContinue |
      Select-Object Name, MaxClockSpeed, CurrentClockSpeed, LoadPercentage |
      ConvertTo-Json -Compress
    """
    raw = run_powershell_stdout(script, timeout=45)
    cpus = []
    if raw:
        try:
            data = json.loads(raw)
            cpus = data if isinstance(data, list) else [data]
        except json.JSONDecodeError:
            pass
    results = []
    for cpu in cpus:
        max_clock = cpu.get("MaxClockSpeed") or 0
        cur_clock = cpu.get("CurrentClockSpeed") or 0
        ratio = (cur_clock / max_clock) if max_clock else None
        results.append(
            {
                "name": cpu.get("Name", "CPU"),
                "max_mhz": max_clock,
                "current_mhz": cur_clock,
                "load_percent": cpu.get("LoadPercentage"),
                "clock_ratio": round(ratio, 2) if ratio is not None else None,
                "throttled": bool(ratio is not None and ratio < 0.6),
            }
        )
    return {"available": bool(results), "cpus": results}


def collect_failing_services() -> dict:
    """Stopped-but-automatic services explain weird behavior."""
    if sys.platform != "win32":
        return {"available": False, "services": []}

    script = """
    Get-CimInstance Win32_Service -ErrorAction SilentlyContinue |
      Where-Object { $_.StartMode -eq 'Auto' -and $_.State -ne 'Running' -and -not $_.DelayedAutoStart } |
      Select-Object Name, DisplayName, State, StartName, ExitCode |
      Sort-Object DisplayName |
      ConvertTo-Json -Compress
    """
    raw = run_powershell_stdout(script, timeout=45)
    services = []
    if raw:
        try:
            data = json.loads(raw)
            services = data if isinstance(data, list) else [data]
        except json.JSONDecodeError:
            pass
    return {"available": bool(services), "services": services[:25], "count": len(services)}


def collect_old_gpu_drivers() -> dict:
    """Flag GPU drivers older than 6 months — top cause of display/gaming issues."""
    if sys.platform != "win32":
        return {"available": False, "old": []}

    script = """
    $cutoff = (Get-Date).AddMonths(-6)
    Get-CimInstance Win32_PnPSignedDriver -ErrorAction SilentlyContinue |
      Where-Object { $_.DeviceClass -eq 'DISPLAY' -and $_.DriverDate -and $_.DriverDate -lt $cutoff } |
      Select-Object DeviceName, Manufacturer, DriverVersion,
        @{n='DriverDate';e={ $_.DriverDate.ToString('yyyy-MM-dd') }},
        @{n='AgeMonths';e={ [math]::Round(((Get-Date) - $_.DriverDate).Days / 30.4, 1) }} |
      ConvertTo-Json -Compress
    """
    raw = run_powershell_stdout(script, timeout=60)
    old = []
    if raw:
        try:
            data = json.loads(raw)
            old = data if isinstance(data, list) else [data]
        except json.JSONDecodeError:
            pass
    return {"available": True, "old": old, "count": len(old)}


def collect_network_latency() -> dict:
    """Latency + DNS check — 'internet works' isn't the same as 'internet is good'."""
    if sys.platform != "win32":
        return {"available": False}

    script = """
    $result = [ordered]@{ dns_ms = $null; ping_ms = $null; target = '1.1.1.1' }
    try {
      $sw = [System.Diagnostics.Stopwatch]::StartNew()
      [void][System.Net.Dns]::GetHostAddresses('www.microsoft.com')
      $sw.Stop()
      $result.dns_ms = $sw.ElapsedMilliseconds
    } catch {}
    try {
      $p = Test-Connection -ComputerName 1.1.1.1 -Count 3 -ErrorAction Stop |
        Measure-Object -Property Latency -Average
      $result.ping_ms = [math]::Round($p.Average, 1)
    } catch {
      try {
        $p = Test-Connection -ComputerName 1.1.1.1 -Count 3 -ErrorAction Stop |
          Measure-Object -Property ResponseTime -Average
        $result.ping_ms = [math]::Round($p.Average, 1)
      } catch {}
    }
    $result | ConvertTo-Json -Compress
    """
    raw = run_powershell_stdout(script, timeout=45)
    if not raw:
        return {"available": False}
    try:
        return {"available": True, **json.loads(raw)}
    except json.JSONDecodeError:
        return {"available": False}
