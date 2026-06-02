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
from .software_collector import collect_software


def run_full_scan(
    include_ai: bool = True,
    include_slow_checks: bool = False,
    progress_callback=None,
) -> dict:
    def progress(pct: int, stage: str):
        if progress_callback:
            progress_callback(pct, stage)

    progress(5, "Collecting hardware (WMI)…")
    hardware = collect_hardware()

    progress(25, "SMART disk health…")
    hardware["smart"] = collect_smart_health()

    progress(32, "Temperature sensors…")
    hardware["temperatures"] = collect_temperatures()

    progress(38, "Security status…")
    security = collect_security_status()

    progress(42, "Startup programs…")
    startup = collect_startup_programs()

    progress(48, "Running benchmark…")
    benchmark = collect_benchmark()

    progress(55, "Software inventory…")
    software = collect_software(include_slow_checks=include_slow_checks)

    progress(70, "Health checks…")
    health = run_health_checks(hardware, software)

    components = hardware.get("components_by_manufacturer", [])
    drivers = [c for c in components if c.get("category") == "Drivers"]
    duplicate_drivers = analyze_duplicate_drivers(drivers)
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
        "duplicate_drivers": duplicate_drivers,
        "winget_batch_command": winget_batch,
    }

    progress(80, "AI analysis…" if include_ai else "Finalizing…")
    ai_analysis = analyze_system(snapshot) if include_ai else {}

    overall = ai_analysis.get("overall_score") or health.get("health_score")
    progress(100, "Complete")

    return {
        "snapshot": snapshot,
        "ai_analysis": ai_analysis,
        "overall_score": overall,
    }
