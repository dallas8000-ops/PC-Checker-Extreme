"""Collect lightweight cleanup, process, and connectivity diagnostics."""
import os
import socket
import sys

import psutil

from .powershell import run_powershell_stdout

_SYSTEM_PROCESS_NAMES = {
    "system",
    "system idle process",
    "registry",
    "memory compression",
    "csrss.exe",
    "wininit.exe",
    "services.exe",
    "lsass.exe",
    "svchost.exe",
    "explorer.exe",
    "dwm.exe",
    "ntoskrnl.exe",
}


def collect_top_processes(limit: int = 10) -> dict:
    processes = []
    for proc in psutil.process_iter(["pid", "name", "memory_info", "cpu_percent"]):
        try:
            info = proc.info
            memory = info.get("memory_info")
            if not memory or not info.get("name"):
                continue
            processes.append(
                {
                    "pid": info.get("pid"),
                    "name": info.get("name"),
                    "memory_mb": round(memory.rss / (1024**2), 1),
                    "cpu_percent": info.get("cpu_percent") or 0.0,
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    processes.sort(key=lambda process: process["memory_mb"], reverse=True)
    top = processes[:limit]
    resource_hog = next(
        (
            process
            for process in top
            if process["memory_mb"] >= 1536
            and process["name"].strip().lower() not in _SYSTEM_PROCESS_NAMES
        ),
        None,
    )
    return {
        "available": bool(top),
        "processes": top,
        "process_count": len(processes),
        "resource_hog": resource_hog,
    }


def _folder_size_mb(path: str) -> float:
    total = 0
    if not path or not os.path.isdir(path):
        return 0.0
    for root, _dirs, files in os.walk(path, onerror=lambda _error: None):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                continue
    return round(total / (1024**2), 1)


def _recycle_bin_size_mb() -> float | None:
    if sys.platform != "win32":
        return None
    script = """
    try {
      $shell = New-Object -ComObject Shell.Application
      $bin = $shell.Namespace(10)
      $sum = 0
      foreach ($item in $bin.Items()) { $sum += $item.ExtendedProperty('Size') }
      $sum
    } catch { -1 }
    """
    raw = run_powershell_stdout(script, timeout=30)
    try:
        value = float(raw)
        return round(value / (1024**2), 1) if value >= 0 else None
    except (TypeError, ValueError):
        return None


def collect_junk_files() -> dict:
    locations = []
    user_temp = os.environ.get("TEMP") or os.environ.get("TMP")
    if user_temp:
        locations.append({"label": "User Temp folder", "size_mb": _folder_size_mb(user_temp)})

    windir = os.environ.get("WINDIR") or os.environ.get("SystemRoot")
    if windir:
        locations.append(
            {"label": "Windows Temp folder", "size_mb": _folder_size_mb(os.path.join(windir, "Temp"))}
        )

    recycle_mb = _recycle_bin_size_mb()
    if recycle_mb is not None:
        locations.append({"label": "Recycle Bin", "size_mb": recycle_mb})

    return {
        "available": bool(locations),
        "locations": locations,
        "total_reclaimable_mb": round(sum(location["size_mb"] for location in locations), 1),
    }


def collect_network_status(host: str = "8.8.8.8", port: int = 53, timeout: float = 2.0) -> dict:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            connected = True
    except OSError:
        connected = False
    return {"available": True, "internet_connected": connected, "checked_host": host}