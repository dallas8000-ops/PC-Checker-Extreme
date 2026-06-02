"""Build template context for report and export views."""


def build_report_context(report) -> dict:
    snapshot = report.system_snapshot or {}
    ai = report.ai_analysis or {}
    hardware = snapshot.get("hardware", {})
    software = snapshot.get("software", {})
    health = snapshot.get("health", {})

    components = hardware.get("components_by_manufacturer", [])
    by_category = {}
    for c in components:
        cat = c.get("category", "Other")
        by_category.setdefault(cat, []).append(c)

    category_order = [
        "Motherboard",
        "CPU",
        "GPU",
        "RAM",
        "Storage",
        "Volume",
        "Drivers",
        "Network",
        "Sound",
        "Other",
    ]
    ordered = {}
    for cat in category_order:
        if cat in by_category:
            ordered[cat] = by_category[cat]
    for cat, items in by_category.items():
        if cat not in ordered:
            ordered[cat] = items

    return {
        "report": report,
        "snapshot": snapshot,
        "ai": ai,
        "health": health,
        "components_by_category": ordered,
        "storage_summary": hardware.get("storage_summary", {}),
        "system_profile": hardware.get("system_profile", {}),
        "volumes": hardware.get("volumes", []),
        "smart": hardware.get("smart", {}),
        "temperatures": hardware.get("temperatures", {}),
        "security": snapshot.get("security", {}),
        "startup": snapshot.get("startup", {}),
        "benchmark": snapshot.get("benchmark", {}),
        "duplicate_drivers": snapshot.get("duplicate_drivers", []),
        "winget_batch_command": snapshot.get("winget_batch_command", ""),
        "outdated_packages": software.get("outdated_winget", {}).get("packages", []),
        "windows_updates": software.get("windows_updates", {}).get("updates", []),
        "installed_programs": software.get("installed", {}).get("programs", []),
        "live_metrics": hardware.get("live_metrics", {}),
    }
