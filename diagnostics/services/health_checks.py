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

    # --- Extended diagnostics signals (passed in via cleanup/extended) ---
    extended = cleanup.get("extended", {})

    crashes = extended.get("crashes", {})
    if crashes.get("count", 0) > 0:
        n = crashes["count"]
        checks.append(
            {
                "id": "recent_crashes",
                "severity": "critical" if n >= 3 else "warning",
                "title": f"{n} crash dump(s) found",
                "message": "Recent blue screens / app crashes detected. Review the Reliability and Event Log sections.",
            }
        )

    smart_raw = extended.get("smart_raw", {})
    at_risk = smart_raw.get("at_risk", [])
    if at_risk:
        names = ", ".join(d.get("FriendlyName", "disk") for d in at_risk[:3])
        checks.append(
            {
                "id": "smart_failure_risk",
                "severity": "critical",
                "title": "Drive failure predicted",
                "message": f"SMART reports elevated failure risk on: {names}. Back up data immediately.",
            }
        )

    vbs = extended.get("virtualization", {})
    if vbs.get("available") and vbs.get("memory_integrity") is False:
        checks.append(
            {
                "id": "memory_integrity_off",
                "severity": "warning",
                "title": "Memory integrity (Core Isolation) is off",
                "message": "Enable it in Windows Security > Device security > Core isolation for better protection.",
            }
        )

    sb_tpm = extended.get("secure_boot_tpm", {})
    if sb_tpm.get("available"):
        if sb_tpm.get("secure_boot") is False:
            checks.append(
                {
                    "id": "secure_boot_off",
                    "severity": "warning",
                    "title": "Secure Boot is disabled",
                    "message": "Enable Secure Boot in UEFI/BIOS for Windows 11 compliance and boot protection.",
                }
            )
        tpm = sb_tpm.get("tpm", {})
        if tpm.get("present") and not tpm.get("ready"):
            checks.append(
                {
                    "id": "tpm_not_ready",
                    "severity": "info",
                    "title": "TPM present but not ready",
                    "message": "TPM is detected but not fully enabled/ready. Enable it in UEFI/BIOS.",
                }
            )

    pagefile = extended.get("page_file", {})
    if pagefile.get("available") and not pagefile.get("configured") and not pagefile.get("managed"):
        checks.append(
            {
                "id": "no_pagefile",
                "severity": "warning",
                "title": "No page file configured",
                "message": "A missing page file can cause crashes and slowdowns under memory pressure. Let Windows manage it.",
            }
        )

    throttle = extended.get("cpu_throttling", {})
    for cpu in throttle.get("cpus", []):
        if cpu.get("throttled"):
            checks.append(
                {
                    "id": "cpu_throttled",
                    "severity": "warning",
                    "title": "CPU is throttling",
                    "message": f"{cpu['name']} running at {cpu['current_mhz']} MHz of {cpu['max_mhz']} MHz. Check cooling and power plan.",
                }
            )

    failing = extended.get("failing_services", {})
    if failing.get("count", 0) > 0:
        n = failing["count"]
        checks.append(
            {
                "id": "failing_services",
                "severity": "warning" if n < 5 else "critical",
                "title": f"{n} automatic service(s) not running",
                "message": "Some services set to start automatically are stopped. This can cause features to misbehave.",
            }
        )

    old_gpu = extended.get("old_gpu_drivers", {})
    if old_gpu.get("count", 0) > 0:
        oldest = max(old_gpu.get("old", []), key=lambda d: d.get("AgeMonths", 0))
        checks.append(
            {
                "id": "old_gpu_driver",
                "severity": "warning",
                "title": "Graphics driver is outdated",
                "message": f"{oldest.get('DeviceName', 'GPU')} driver is {oldest.get('AgeMonths', 0):.0f} months old. Update for stability and features.",
            }
        )

    latency = extended.get("network_latency", {})
    if latency.get("available"):
        ping = latency.get("ping_ms")
        dns = latency.get("dns_ms")
        if ping is not None and ping >= 200:
            checks.append(
                {
                    "id": "high_latency",
                    "severity": "warning",
                    "title": "High network latency",
                    "message": f"Average ping {ping:.0f} ms to {latency.get('target', 'the internet')}. Expect lag in calls and gaming.",
                }
            )
        if dns is not None and dns >= 300:
            checks.append(
                {
                    "id": "slow_dns",
                    "severity": "info",
                    "title": "Slow DNS resolution",
                    "message": f"DNS lookups take ~{dns:.0f} ms. Consider a faster DNS (e.g. 1.1.1.1 or 8.8.8.8).",
                }
            )

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
