"""Collect hardware components with manufacturer identification (Windows WMI + psutil)."""
import json
import platform
import re
import sys
from datetime import datetime, timezone

import psutil

from .powershell import run_powershell, run_powershell_stdout

# Device classes to include in driver report (Win32_PnPSignedDriver)
_DRIVER_CLASSES = (
    "DISPLAY",
    "NET",
    "SCSIAdapter",
    "HDC",
    "USB",
    "BLUETOOTH",
    "MEDIA",
    "SYSTEM",
    "COMPUTER",
    "MONITOR",
    "PORTS",
    "FIRMWARE",
)


def _wmi_json(class_name: str, properties: list[str], timeout: int = 60) -> list[dict]:
    props = ",".join(properties)
    script = f"""
    Get-CimInstance -ClassName {class_name} -ErrorAction SilentlyContinue |
    Select-Object {props} |
    ConvertTo-Json -Depth 5 -Compress
    """
    raw = run_powershell_stdout(script, timeout=timeout)
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return [data]
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _collect_drivers() -> list[dict]:
    classes = ",".join(f"'{c}'" for c in _DRIVER_CLASSES)
    script = f"""
    Get-CimInstance Win32_PnPSignedDriver -ErrorAction SilentlyContinue |
    Where-Object {{ $_.DeviceClass -in @({classes}) -and $_.DeviceName }} |
    Select-Object DeviceName, DriverVersion, Manufacturer, DriverDate, DeviceClass, IsSigned, DeviceID |
    Sort-Object DeviceClass, DeviceName -Unique |
    ConvertTo-Json -Depth 3 -Compress
    """
    raw = run_powershell_stdout(script, timeout=90)
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return [data]
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _as_text(value, default: str = "") -> str:
    """WMI often returns lists (e.g. BIOSVersion) — safe string for strip/split."""
    if value is None:
        return default
    if isinstance(value, list):
        parts = [str(v).strip() for v in value if v is not None and str(v).strip()]
        return " ".join(parts) if parts else default
    return str(value).strip() or default


_PLACEHOLDER_MARKERS = (
    "to be filled",
    "default string",
    "not available",
    "n/a",
    "none",
    "system product name",
    "system manufacturer",
    "oem",
    "xxx",
    "123456789",
)


def _is_placeholder(value) -> bool:
    text = _as_text(value)
    if not text:
        return True
    lower = text.lower()
    if lower in ("", "unknown", "0"):
        return True
    return any(marker in lower for marker in _PLACEHOLDER_MARKERS)


def _normalize_board_brand(name: str) -> str:
    if not name:
        return ""
    text = str(name).strip()
    lower = text.lower()
    if "micro-star" in lower or lower == "msi" or "micro star" in lower:
        return "MSI"
    if "asustek" in lower or lower.startswith("asus"):
        return "ASUS"
    if "gigabyte" in lower:
        return "Gigabyte"
    if "asrock" in lower:
        return "ASRock"
    return text


def _collect_motherboard_registry() -> dict:
    script = r"""
    $path = 'HKLM:\HARDWARE\DESCRIPTION\System\BIOS'
    $p = Get-ItemProperty -Path $path -ErrorAction SilentlyContinue
    $secureBoot = 'Unknown'
    try { $secureBoot = if (Confirm-SecureBootUEFI) { 'On' } else { 'Off' } } catch {}
    $tz = (Get-TimeZone).DisplayName
    if (-not $p) {
      @{ SecureBootState = $secureBoot; TimeZone = $tz } | ConvertTo-Json -Compress
      exit
    }
    @{
      BaseBoardManufacturer = $p.BaseBoardManufacturer
      BaseBoardProduct = $p.BaseBoardProduct
      BaseBoardVersion = $p.BaseBoardVersion
      BaseBoardSerial = $p.BaseBoardSerialNumber
      SystemManufacturer = $p.SystemManufacturer
      SystemProductName = $p.SystemProductName
      BIOSVendor = $p.BIOSVendor
      BIOSVersion = $p.BIOSVersion
      SecureBootState = $secureBoot
      TimeZone = $tz
    } | ConvertTo-Json -Compress
    """
    raw = run_powershell_stdout(script, timeout=30)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _resolve_motherboard(wmi: dict) -> dict:
    """Merge WMI + registry so real board names (e.g. MSI B550) replace OEM placeholders."""
    reg = wmi.get("motherboard_registry") or {}
    wmi_board = (wmi.get("motherboard") or [{}])[0]
    bios = (wmi.get("bios") or [{}])[0]
    system = (wmi.get("system") or [{}])[0]
    sys_product = (wmi.get("system_product") or [{}])[0]

    candidates_mfr = [
        reg.get("BaseBoardManufacturer"),
        wmi_board.get("Manufacturer"),
        reg.get("SystemManufacturer"),
        system.get("Manufacturer"),
        bios.get("Manufacturer"),
        sys_product.get("Vendor"),
    ]
    candidates_product = [
        reg.get("BaseBoardProduct"),
        wmi_board.get("Product"),
        reg.get("SystemProductName"),
        system.get("Model"),
        sys_product.get("Name"),
    ]
    candidates_version = [
        reg.get("BaseBoardVersion"),
        wmi_board.get("Version"),
        reg.get("BIOSVersion"),
        bios.get("SMBIOSBIOSVersion"),
    ]

    manufacturer = ""
    for c in candidates_mfr:
        if c and not _is_placeholder(c):
            manufacturer = _normalize_board_brand(_as_text(c))
            break
    if not manufacturer:
        for c in candidates_mfr:
            if c:
                manufacturer = _normalize_board_brand(_as_text(c))
                break

    product = ""
    for c in candidates_product:
        if c and not _is_placeholder(c):
            product = _as_text(c)
            break

    if not product and manufacturer:
        product = f"{manufacturer} Motherboard"

    version = ""
    for c in candidates_version:
        if c and not _is_placeholder(c):
            version = _as_text(c)
            break

    serial = _as_text(reg.get("BaseBoardSerial") or wmi_board.get("SerialNumber"))
    if _is_placeholder(serial):
        serial = ""

    return {
        "manufacturer": manufacturer or "Unknown",
        "product": product or "Motherboard",
        "version": version,
        "serial": serial,
        "source": "registry+wmi",
    }


def _collect_disk_partitions() -> list[dict]:
    script = """
    Get-CimInstance Win32_DiskPartition -ErrorAction SilentlyContinue |
    Select-Object DiskIndex, Index, Name, Size, Type |
    ConvertTo-Json -Depth 3 -Compress
    """
    raw = run_powershell_stdout(script, timeout=45)
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return [data]
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _collect_wmi_hardware() -> dict:
    if sys.platform != "win32":
        return {"available": False, "reason": "WMI collection requires Windows"}

    return {
        "available": True,
        "operating_system": _wmi_json(
            "Win32_OperatingSystem",
            [
                "Caption",
                "Version",
                "BuildNumber",
                "OSArchitecture",
                "WindowsDirectory",
                "SystemDirectory",
                "InstallDate",
            ],
        ),
        "system": _wmi_json(
            "Win32_ComputerSystem",
            [
                "Manufacturer",
                "Model",
                "SystemType",
                "TotalPhysicalMemory",
                "NumberOfProcessors",
                "UserName",
                "Domain",
                "PCSystemType",
            ],
        ),
        "bios": _wmi_json(
            "Win32_BIOS",
            [
                "Manufacturer",
                "SMBIOSBIOSVersion",
                "ReleaseDate",
                "SerialNumber",
                "Version",
                "SMBIOSMajorVersion",
                "SMBIOSMinorVersion",
                "BIOSVersion",
            ],
        ),
        "processors": _wmi_json(
            "Win32_Processor",
            [
                "Name",
                "Manufacturer",
                "NumberOfCores",
                "NumberOfLogicalProcessors",
                "MaxClockSpeed",
                "CurrentClockSpeed",
                "Architecture",
            ],
        ),
        "memory_modules": _wmi_json(
            "Win32_PhysicalMemory",
            [
                "Manufacturer",
                "PartNumber",
                "Capacity",
                "Speed",
                "FormFactor",
                "BankLabel",
                "DeviceLocator",
            ],
        ),
        "graphics": _wmi_json(
            "Win32_VideoController",
            [
                "Name",
                "AdapterCompatibility",
                "DriverVersion",
                "DriverDate",
                "AdapterRAM",
                "VideoProcessor",
                "PNPDeviceID",
                "Status",
                "VideoModeDescription",
                "CurrentHorizontalResolution",
                "CurrentVerticalResolution",
                "CurrentRefreshRate",
            ],
        ),
        "storage": _wmi_json(
            "Win32_DiskDrive",
            [
                "Index",
                "Model",
                "Manufacturer",
                "InterfaceType",
                "Size",
                "SerialNumber",
                "MediaType",
                "Partitions",
                "Status",
                "FirmwareRevision",
                "PNPDeviceID",
            ],
        ),
        "logical_disks": _wmi_json(
            "Win32_LogicalDisk",
            ["DeviceID", "FileSystem", "Size", "FreeSpace", "VolumeName", "DriveType", "Description"],
        ),
        "partitions": _collect_disk_partitions(),
        "motherboard": _wmi_json(
            "Win32_BaseBoard",
            ["Manufacturer", "Product", "Version", "SerialNumber"],
        ),
        "motherboard_registry": _collect_motherboard_registry(),
        "system_product": _wmi_json(
            "Win32_ComputerSystemProduct",
            ["Vendor", "Name", "Version", "IdentifyingNumber"],
        ),
        "system_enclosure": _wmi_json(
            "Win32_SystemEnclosure",
            ["Manufacturer", "ChassisTypes"],
        ),
        "network_adapters": _wmi_json(
            "Win32_NetworkAdapter",
            ["Name", "Manufacturer", "MACAddress", "NetEnabled", "AdapterType", "PNPDeviceID"],
        ),
        "sound": _wmi_json(
            "Win32_SoundDevice",
            ["Name", "Manufacturer", "Status", "PNPDeviceID"],
        ),
        "drivers": _collect_drivers(),
    }


def _format_bytes(value) -> str:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return str(value) if value else ""
    if n <= 0:
        return ""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} PB"


def _format_storage_size_gb(gb: float) -> str:
    """Human size like File Explorer (GB or TB)."""
    try:
        gb = float(gb)
    except (TypeError, ValueError):
        return "0 GB"
    if gb >= 1024:
        return f"{gb / 1024:.2f} TB"
    if gb >= 10:
        return f"{int(round(gb))} GB"
    return f"{gb:.2f} GB"


def _build_volumes(wmi: dict, live_metrics: dict) -> list[dict]:
    """All local volumes (C:, D:, E:, …) with labels matching This PC."""
    wmi_vols = []
    for vol in wmi.get("logical_disks") or []:
        try:
            if int(vol.get("DriveType", 0)) != 3:
                continue
        except (TypeError, ValueError):
            continue
        letter = (vol.get("DeviceID") or "").strip()
        if not letter:
            continue
        wmi_vols.append(vol)

    def sort_key(vol):
        lid = (vol.get("DeviceID") or "Z:").upper()
        return lid

    wmi_vols.sort(key=sort_key)
    psutil_by_letter = {}
    for d in live_metrics.get("disks", []):
        mount = (d.get("mount") or "").rstrip("\\").upper()
        if mount:
            psutil_by_letter[mount] = d

    volumes = []
    for vol in wmi_vols:
        letter = vol.get("DeviceID", "").upper()
        label = (vol.get("VolumeName") or "").strip() or "Local Disk"
        display_name = f"{label} ({letter})"

        psu = psutil_by_letter.get(letter.rstrip(":")) or psutil_by_letter.get(letter)
        if psu and psu.get("total_gb") is not None:
            total_gb = float(psu["total_gb"])
            free_gb = float(psu.get("free_gb") or 0)
            used_gb = float(psu.get("used_gb") or 0)
            percent_used = psu.get("percent_used") or 0
        else:
            try:
                total_gb = int(vol.get("Size") or 0) / (1024**3)
                free_gb = int(vol.get("FreeSpace") or 0) / (1024**3)
            except (TypeError, ValueError):
                total_gb = free_gb = 0
            used_gb = max(0, total_gb - free_gb)
            percent_used = round((used_gb / total_gb) * 100, 1) if total_gb else 0

        free_text = f"{_format_storage_size_gb(free_gb)} free of {_format_storage_size_gb(total_gb)}"
        is_windows = letter.startswith("C")

        volumes.append(
            {
                "letter": letter,
                "label": label,
                "display_name": display_name,
                "filesystem": vol.get("FileSystem") or "",
                "total_gb": round(total_gb, 2),
                "free_gb": round(free_gb, 2),
                "used_gb": round(used_gb, 2),
                "percent_used": percent_used,
                "free_text": free_text,
                "is_windows": is_windows,
            }
        )

    return volumes


def _format_wmi_date(value) -> str:
    if not value:
        return ""
    text = str(value)
    m = re.search(r"/Date\((\d+)", text)
    if m:
        try:
            ts = int(m.group(1)) / 1000
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        except (ValueError, OSError):
            pass
    if len(text) >= 8 and text[:8].isdigit():
        return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
    return text[:32]


def _clean_manufacturer(name: str) -> str:
    if not name:
        return "Unknown"
    cleaned = str(name).strip()
    generic = (
        "to be filled",
        "standard disk drives",
        "(standard",
        "microsoft",
        "unknown",
    )
    lower = cleaned.lower()
    if any(g in lower for g in generic) and len(cleaned) < 4:
        return "Unknown"
    return cleaned or "Unknown"


def _collect_psutil_summary() -> dict:
    vm = psutil.virtual_memory()
    disks = []
    for part in psutil.disk_partitions(all=True):
        if part.fstype and "cdrom" in (part.opts or "").lower():
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            disks.append(
                {
                    "mount": part.mountpoint,
                    "fstype": part.fstype or "",
                    "device": part.device,
                    "total_gb": None,
                    "used_gb": None,
                    "free_gb": None,
                    "percent_used": None,
                    "note": "Could not read usage (permission or unmounted)",
                }
            )
            continue
        disks.append(
            {
                "mount": part.mountpoint,
                "device": part.device,
                "fstype": part.fstype,
                "total_gb": round(usage.total / (1024**3), 2),
                "used_gb": round(usage.used / (1024**3), 2),
                "free_gb": round(usage.free / (1024**3), 2),
                "percent_used": usage.percent,
            }
        )

    cpu_freq = psutil.cpu_freq()
    return {
        "cpu_count_logical": psutil.cpu_count(logical=True),
        "cpu_count_physical": psutil.cpu_count(logical=False),
        "cpu_percent": psutil.cpu_percent(interval=0.5),
        "cpu_freq_mhz": round(cpu_freq.current, 1) if cpu_freq else None,
        "memory": {
            "total_gb": round(vm.total / (1024**3), 2),
            "available_gb": round(vm.available / (1024**3), 2),
            "percent_used": vm.percent,
        },
        "disks": disks,
        "boot_time": datetime.fromtimestamp(
            psutil.boot_time(), tz=timezone.utc
        ).isoformat(),
    }


def _build_components(wmi: dict) -> list[dict]:
    components = []

    for cpu in wmi.get("processors") or []:
        components.append(
            {
                "category": "CPU",
                "name": (cpu.get("Name") or "CPU").strip(),
                "manufacturer": _clean_manufacturer(cpu.get("Manufacturer")),
                "details": {
                    "cores": cpu.get("NumberOfCores"),
                    "threads": cpu.get("NumberOfLogicalProcessors"),
                    "max_clock_mhz": cpu.get("MaxClockSpeed"),
                    "current_clock_mhz": cpu.get("CurrentClockSpeed"),
                },
            }
        )

    for gpu in wmi.get("graphics") or []:
        name = (gpu.get("Name") or "").strip()
        if not name:
            continue
        res = ""
        w, h = gpu.get("CurrentHorizontalResolution"), gpu.get("CurrentVerticalResolution")
        if w and h:
            res = f"{w}x{h}"
            if gpu.get("CurrentRefreshRate"):
                res += f" @ {gpu.get('CurrentRefreshRate')}Hz"
        components.append(
            {
                "category": "GPU",
                "name": name,
                "manufacturer": _clean_manufacturer(
                    gpu.get("AdapterCompatibility") or gpu.get("VideoProcessor")
                ),
                "details": {
                    "video_processor": (gpu.get("VideoProcessor") or "").strip() or None,
                    "driver_version": gpu.get("DriverVersion"),
                    "driver_date": _format_wmi_date(gpu.get("DriverDate")),
                    "vram": _format_bytes(gpu.get("AdapterRAM")),
                    "resolution": res or gpu.get("VideoModeDescription"),
                    "status": gpu.get("Status"),
                    "device_id": _short_pnp(gpu.get("PNPDeviceID")),
                },
            }
        )

    board = wmi.get("motherboard_resolved") or _resolve_motherboard(wmi)
    details = {
        "version": board.get("version") or None,
        "serial": board.get("serial") or None,
        "chipset_board": board.get("product"),
    }
    for bios in wmi.get("bios") or []:
        details["bios_manufacturer"] = _as_text(bios.get("Manufacturer"))
        details["bios_version"] = _as_text(
            bios.get("BIOSVersion") or bios.get("SMBIOSBIOSVersion") or bios.get("Version")
        )
        details["bios_date"] = _format_wmi_date(bios.get("ReleaseDate"))
        break
    reg = wmi.get("motherboard_registry") or {}
    if reg.get("BIOSVendor") and not _is_placeholder(reg.get("BIOSVendor")):
        details["bios_vendor"] = _as_text(reg.get("BIOSVendor"))
    sys_info = (wmi.get("system") or [{}])[0]
    if sys_info.get("Manufacturer"):
        details["system_oem"] = f"{sys_info.get('Manufacturer')} {sys_info.get('Model', '')}".strip()
    components.append(
        {
            "category": "Motherboard",
            "name": board.get("product", "Motherboard"),
            "manufacturer": board.get("manufacturer", "Unknown"),
            "details": details,
        }
    )

    for mod in wmi.get("memory_modules") or []:
        components.append(
            {
                "category": "RAM",
                "name": (mod.get("PartNumber") or "Memory module").strip(),
                "manufacturer": _clean_manufacturer(mod.get("Manufacturer")),
                "details": {
                    "capacity": _format_bytes(mod.get("Capacity")),
                    "speed_mhz": mod.get("Speed"),
                    "slot": mod.get("DeviceLocator"),
                    "bank": mod.get("BankLabel"),
                },
            }
        )

    for drive in wmi.get("storage") or []:
        model = (drive.get("Model") or "Physical drive").strip()
        idx = drive.get("Index")
        label = f"Physical disk {idx}: {model}" if idx is not None else model
        mfr = _clean_manufacturer(drive.get("Manufacturer"))
        if mfr == "Unknown" and model:
            mfr = model.split()[0] if model else "Unknown"
        components.append(
            {
                "category": "Storage",
                "name": label,
                "manufacturer": mfr,
                "details": {
                    "interface": drive.get("InterfaceType"),
                    "size": _format_bytes(drive.get("Size")),
                    "media_type": drive.get("MediaType"),
                    "serial": (drive.get("SerialNumber") or "").strip(),
                    "firmware": (drive.get("FirmwareRevision") or "").strip(),
                    "partitions": drive.get("Partitions"),
                    "status": drive.get("Status"),
                },
            }
        )

    for vol in wmi.get("logical_disks") or []:
        try:
            dtype = int(vol.get("DriveType", 0))
        except (TypeError, ValueError):
            dtype = 0
        if dtype != 3:
            continue
        label = (vol.get("VolumeName") or "").strip() or "Local Disk"
        letter = vol.get("DeviceID") or "?"
        components.append(
            {
                "category": "Volume",
                "name": f"{label} ({letter})",
                "manufacturer": vol.get("FileSystem") or "NTFS",
                "details": {
                    "filesystem": vol.get("FileSystem"),
                    "total": _format_bytes(vol.get("Size")),
                    "free": _format_bytes(vol.get("FreeSpace")),
                    "description": (vol.get("Description") or "").strip(),
                },
            }
        )

    for nic in wmi.get("network_adapters") or []:
        if not nic.get("NetEnabled") or not nic.get("MACAddress"):
            continue
        components.append(
            {
                "category": "Network",
                "name": (nic.get("Name") or "Network adapter").strip(),
                "manufacturer": _clean_manufacturer(nic.get("Manufacturer")),
                "details": {
                    "mac": nic.get("MACAddress"),
                    "type": nic.get("AdapterType"),
                },
            }
        )

    for drv in wmi.get("drivers") or []:
        device = (drv.get("DeviceName") or "").strip()
        if not device:
            continue
        components.append(
            {
                "category": "Drivers",
                "name": device,
                "manufacturer": _clean_manufacturer(drv.get("Manufacturer")),
                "details": {
                    "class": drv.get("DeviceClass"),
                    "driver_version": drv.get("DriverVersion"),
                    "driver_date": _format_wmi_date(drv.get("DriverDate")),
                    "signed": drv.get("IsSigned"),
                    "device_id": _short_pnp(drv.get("DeviceID")),
                },
            }
        )

    return components


def _short_pnp(pnp_id: str) -> str:
    if not pnp_id:
        return ""
    text = str(pnp_id)
    if len(text) > 60:
        return "…" + text[-58:]
    return text


def _format_bios_version_date(bios: dict, reg: dict) -> str:
    vendor = _as_text(bios.get("Manufacturer") or reg.get("BIOSVendor"))
    version = _as_text(
        bios.get("BIOSVersion") or bios.get("SMBIOSBIOSVersion") or reg.get("BIOSVersion")
    )
    date = _format_wmi_date(bios.get("ReleaseDate"))
    parts = [p for p in (vendor, version) if p]
    label = " ".join(parts) if parts else ""
    if date:
        label = f"{label}, {date}" if label else date
    return label


def _build_system_profile(wmi: dict, live_metrics: dict, platform_info: dict) -> dict:
    """MSINFO-style system summary (matches Windows System Information)."""
    os0 = (wmi.get("operating_system") or [{}])[0]
    system = (wmi.get("system") or [{}])[0]
    bios = (wmi.get("bios") or [{}])[0]
    cpu = (wmi.get("processors") or [{}])[0]
    board = wmi.get("motherboard_resolved") or _resolve_motherboard(wmi)
    reg = wmi.get("motherboard_registry") or {}
    sys_product = (wmi.get("system_product") or [{}])[0]

    build = os0.get("BuildNumber") or platform_info.get("release", "")
    version_line = os0.get("Version") or ""
    if build:
        version_line = f"{version_line} Build {build}".strip()

    processor_line = (cpu.get("Name") or "").strip()
    if cpu.get("MaxClockSpeed"):
        processor_line += f", {cpu.get('MaxClockSpeed')} Mhz"
    if cpu.get("NumberOfCores"):
        processor_line += f", {cpu.get('NumberOfCores')} Core(s)"
    if cpu.get("NumberOfLogicalProcessors"):
        processor_line += f", {cpu.get('NumberOfLogicalProcessors')} Logical Processor(s)"

    smbios = ""
    if bios.get("SMBIOSMajorVersion") is not None:
        minor = bios.get("SMBIOSMinorVersion") or 0
        smbios = f"{bios.get('SMBIOSMajorVersion')}.{minor}"

    mem = live_metrics.get("memory", {})
    rows = [
        ("OS Name", os0.get("Caption") or f"Microsoft Windows {platform_info.get('release', '')}"),
        ("Version", version_line),
        ("OS Manufacturer", "Microsoft Corporation"),
        ("System Name", platform_info.get("node") or system.get("Name")),
        (
            "System Manufacturer",
            _normalize_board_brand(system.get("Manufacturer") or reg.get("SystemManufacturer") or "")
            or board.get("manufacturer"),
        ),
        (
            "System Model",
            system.get("Model")
            if not _is_placeholder(system.get("Model"))
            else (reg.get("SystemProductName") if not _is_placeholder(reg.get("SystemProductName")) else board.get("product")),
        ),
        ("System Type", os0.get("OSArchitecture") or system.get("SystemType")),
        ("System SKU", sys_product.get("IdentifyingNumber") or sys_product.get("Version")),
        ("Processor", processor_line.strip(", ") if processor_line else None),
        ("BIOS Version/Date", _format_bios_version_date(bios, reg)),
        ("SMBIOS Version", smbios or None),
        ("BaseBoard Manufacturer", board.get("manufacturer")),
        ("BaseBoard Product", board.get("product")),
        ("BaseBoard Version", board.get("version") or reg.get("BaseBoardVersion")),
        ("Platform Role", "Desktop" if str(system.get("PCSystemType")) in ("1", "Desktop") else system.get("PCSystemType")),
        ("Secure Boot State", reg.get("SecureBootState")),
        ("Windows Directory", os0.get("WindowsDirectory")),
        ("System Directory", os0.get("SystemDirectory")),
        ("Time Zone", reg.get("TimeZone")),
        ("Installed Physical Memory (RAM)", f"{mem.get('total_gb', 0):.1f} GB"),
        ("Available Physical Memory", f"{mem.get('available_gb', 0):.1f} GB"),
        ("User Name", system.get("UserName")),
    ]

    return {
        "rows": [{"label": label, "value": value} for label, value in rows if value],
        "motherboard": board,
    }


def collect_hardware() -> dict:
    wmi = _collect_wmi_hardware()
    wmi["motherboard_resolved"] = _resolve_motherboard(wmi)
    live_metrics = _collect_psutil_summary()
    components = _build_components(wmi)
    platform_info = {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "node": platform.node(),
    }
    system_profile = _build_system_profile(wmi, live_metrics, platform_info)
    volumes = _build_volumes(wmi, live_metrics)

    for vol in volumes:
        system_profile["rows"].append(
            {"label": f"Drive {vol['letter']}", "value": f"{vol['display_name']} — {vol['free_text']}"}
        )

    return {
        "platform": platform_info,
        "wmi": wmi,
        "live_metrics": live_metrics,
        "system_profile": system_profile,
        "volumes": volumes,
        "components_by_manufacturer": components,
        "storage_summary": {
            "physical_disk_count": len(wmi.get("storage") or []),
            "volume_count": len(volumes),
            "driver_count": len(wmi.get("drivers") or []),
        },
    }
