"""Quick health checks: disk space, memory pressure, boot age."""
from datetime import datetime, timezone

import psutil


def run_health_checks(hardware: dict, software: dict, cleanup: dict | None = None) -> dict:
    checks = []
    cleanup = cleanup or {}
    metrics = hardware.get("live_metrics", {})
    memory = metrics.get("memory", {})

    mem_pct = memory.get("percent_used", 0)
    if mem_pct >= 90:
        checks.append(
            {
                "id": "memory_critical",
                "severity": "critical",
                "title": "Memory critically high",
                "message": f"RAM usage is at {mem_pct}%. Close heavy apps or add RAM.",
            }
        )
    elif mem_pct >= 75:
        checks.append(
            {
                "id": "memory_warning",
                "severity": "warning",
                "title": "High memory usage",
                "message": f"RAM usage is at {mem_pct}%.",
            }
        )
    else:
        checks.append(
            {
                "id": "memory_ok",
                "severity": "ok",
                "title": "Memory usage normal",
                "message": f"RAM usage is at {mem_pct}%.",
            }
        )

    for disk in metrics.get("disks", []):
        pct = disk.get("percent_used", 0)
        mount = disk.get("mount", "?")
        if pct >= 95:
            checks.append(
                {
                    "id": f"disk_{mount}_critical",
                    "severity": "critical",
                    "title": f"Disk {mount} almost full",
                    "message": f"{pct}% used on {mount}. Free space urgently needed.",
                }
            )
        elif pct >= 85:
            checks.append(
                {
                    "id": f"disk_{mount}_warning",
                    "severity": "warning",
                    "title": f"Disk {mount} running low",
                    "message": f"{pct}% used on {mount}.",
                }
            )

    outdated = software.get("outdated_winget", {})
    pkg_count = outdated.get("count", 0) or len(outdated.get("packages", []))
    if pkg_count > 0:
        checks.append(
            {
                "id": "outdated_apps",
                "severity": "warning" if pkg_count < 10 else "critical",
                "title": f"{pkg_count} application(s) have updates",
                "message": "Review the Updates tab for winget upgrade candidates.",
            }
        )

    win_updates = software.get("windows_updates", {})
    pending = win_updates.get("count", 0)
    if pending > 0:
        checks.append(
            {
                "id": "windows_updates",
                "severity": "warning",
                "title": f"{pending} Windows update(s) pending",
                "message": "Install pending Windows updates for security and stability.",
            }
        )

    driver_updates = win_updates.get("driver_count", 0) or len(win_updates.get("drivers", []))
    if driver_updates > 0:
        checks.append(
            {
                "id": "driver_updates",
                "severity": "warning",
                "title": f"{driver_updates} driver update(s) pending",
                "message": "Review Windows Update driver packages for device stability and compatibility.",
            }
        )

    junk = cleanup.get("junk_files", {})
    reclaimable_mb = junk.get("total_reclaimable_mb", 0) or 0
    if reclaimable_mb >= 2048:
        checks.append({
            "id": "junk_files_high",
            "severity": "warning",
            "title": f"{reclaimable_mb / 1024:.1f} GB of temp/junk files found",
            "message": "Temp folders and Recycle Bin are holding reclaimable space. Run a cleanup.",
        })
    elif reclaimable_mb >= 512:
        checks.append({
            "id": "junk_files_moderate",
            "severity": "info",
            "title": f"{reclaimable_mb:.0f} MB of temp/junk files found",
            "message": "A quick temp-file cleanup could free up some space.",
        })

    hog = (cleanup.get("top_processes", {}) or {}).get("resource_hog")
    if hog:
        checks.append({
            "id": "process_memory_hog",
            "severity": "warning",
            "title": f"{hog['name']} is using {hog['memory_mb'] / 1024:.1f} GB of RAM",
            "message": "Consider closing it if you do not need it running, or check for a runaway process.",
        })

    network = cleanup.get("network", {})
    if network.get("available") and not network.get("internet_connected", True):
        checks.append({
            "id": "no_internet",
            "severity": "warning",
            "title": "No internet connectivity detected",
            "message": f"Could not reach {network.get('checked_host', 'the internet')}. Check your network connection.",
        })

    boot_iso = metrics.get("boot_time")
    if boot_iso:
        try:
            boot = datetime.fromisoformat(boot_iso.replace("Z", "+00:00"))
            uptime_days = (datetime.now(timezone.utc) - boot).days
            if uptime_days > 30:
                checks.append(
                    {
                        "id": "long_uptime",
                        "severity": "info",
                        "title": "Long uptime",
                        "message": f"System has been running {uptime_days} days. A reboot may help apply updates.",
                    }
                )
        except ValueError:
            pass

    severity_order = {"critical": 0, "warning": 1, "info": 2, "ok": 3}
    checks.sort(key=lambda c: severity_order.get(c["severity"], 9))

    score = 100
    for c in checks:
        if c["severity"] == "critical":
            score -= 25
        elif c["severity"] == "warning":
            score -= 10
        elif c["severity"] == "info":
            score -= 2
    score = max(0, min(100, score))

    return {"checks": checks, "health_score": score}
