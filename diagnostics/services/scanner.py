from .ai_analyzer import analyze_system
from .extended_diagnostics import (
    analyze_duplicate_drivers,
    build_winget_batch_command,
    collect_benchmark,
    collect_security_status,
    collect_smart_health,
    collect_startup_programs,
    collect_temperatures,
    enrich_drivers_with_links,
)
from .hardware_collector import collect_hardware
from .health_checks import run_health_checks
from .scan_insights import (
    analyze_bottleneck,
    build_command_playbook,
    build_driver_gap_report,
    build_ms_catalog_links,
    collect_battery_status,
    collect_event_log_digest,
    collect_reliability_digest,
    enrich_duplicate_driver_advice,
    rank_startup_programs,
)
from .software_collector import collect_software


def run_full_scan(
    include_ai: bool = True,
    include_slow_checks: bool = False,
    include_software_inventory: bool = False,
    progress_callback=None,
) -> dict:
    def progress(pct: int, stage: str):
        if progress_callback:
            progress_callback(pct, stage)

    progress(5, "Reading Windows System Information (WMI)…")
    hardware = collect_hardware()

    progress(25, "SMART disk health…")
    hardware["smart"] = collect_smart_health()

    progress(32, "Temperature sensors…")
    hardware["temperatures"] = collect_temperatures()

    progress(38, "Security status…")
    security = collect_security_status()

    progress(40, "Event log (last 7 days)…")
    event_log = collect_event_log_digest()

    progress(44, "Reliability Monitor…")
    reliability = collect_reliability_digest()

    progress(46, "Startup programs…")
    startup = rank_startup_programs(collect_startup_programs())

    progress(48, "Battery status…")
    battery = collect_battery_status()

    progress(50, "Running benchmark…")
    benchmark = collect_benchmark()

    if include_software_inventory:
        progress(55, "Installed programs (registry)…")
    else:
        progress(55, "Skipping program list (system info only)…")
    software = collect_software(
        include_inventory=include_software_inventory,
        include_slow_checks=include_slow_checks,
    )

    progress(70, "Health checks…")
    health = run_health_checks(hardware, software)

    components = hardware.get("components_by_manufacturer", [])
    drivers = [c for c in components if c.get("category") == "Drivers"]
    duplicate_drivers = enrich_duplicate_driver_advice(analyze_duplicate_drivers(drivers))
    enrich_drivers_with_links(components)
    hardware["components_by_manufacturer"] = components

    outdated = software.get("outdated_winget", {}).get("packages", [])
    winget_batch = build_winget_batch_command(outdated)

    snapshot = {
        "hostname": hardware.get("platform", {}).get("node", ""),
        "hardware": hardware,
        "software": software,
        "health": health,
        "security": security,
        "startup": startup,
        "benchmark": benchmark,
        "event_log": event_log,
        "reliability": reliability,
        "battery": battery,
        "duplicate_drivers": duplicate_drivers,
        "winget_batch_command": winget_batch,
    }
    snapshot["bottleneck"] = analyze_bottleneck(snapshot)
    snapshot["command_playbook"] = build_command_playbook(snapshot)
    snapshot["driver_gaps"] = build_driver_gap_report(snapshot)
    snapshot["catalog_links"] = build_ms_catalog_links(snapshot)

    progress(80, "AI analysis…" if include_ai else "Finalizing…")
    ai_analysis = analyze_system(snapshot) if include_ai else {}

    overall = ai_analysis.get("overall_score") or health.get("health_score")
    progress(100, "Complete")

    return {
        "snapshot": snapshot,
        "ai_analysis": ai_analysis,
        "overall_score": overall,
    }
