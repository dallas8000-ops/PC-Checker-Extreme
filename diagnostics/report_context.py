"""Build template context for report and export views."""

from diagnostics.services.driver_lookup import resolve_driver_sources


def _detect_manufacturer_queries(snapshot: dict) -> list[dict]:
    hardware = snapshot.get("hardware", {})
    components = hardware.get("components_by_manufacturer", [])
    queries = []

    for comp in components:
        vendor = (comp.get("manufacturer") or "").strip()
        if not vendor:
            continue
        queries.append(
            {
                "vendor": vendor,
                "model": (comp.get("name") or "").strip(),
                "component": (comp.get("category") or "").strip(),
                "hardware_id": "",
            }
        )

    system_profile = hardware.get("system_profile", {})
    profile_rows = {
        (row.get("label") or "").strip().lower(): (row.get("value") or "").strip()
        for row in system_profile.get("rows", [])
    }
    sys_vendor = profile_rows.get("system manufacturer")
    sys_model = profile_rows.get("system model")
    if sys_vendor:
        queries.append(
            {
                "vendor": sys_vendor,
                "model": sys_model or "",
                "component": "System",
                "hardware_id": "",
            }
        )

    deduped = []
    seen = set()
    for q in queries:
        key = (q["vendor"].lower(), q["model"].lower(), q["component"].lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(q)
    return deduped[:20]


def _build_driver_support_sources(snapshot: dict, segment: str = "general") -> list[dict]:
    entries = []
    seen = set()

    for query in _detect_manufacturer_queries(snapshot):
        result = resolve_driver_sources(
            vendor=query["vendor"],
            model=query["model"],
            component=query["component"],
            hardware_id=query["hardware_id"],
            segment=segment,
        )
        for match in result.get("matches", []):
            stable_id = (match.get("key"), match.get("support_url"), match.get("driver_url"))
            if stable_id in seen:
                continue
            seen.add(stable_id)
            entries.append(
                {
                    **match,
                    "matched_vendor": query["vendor"],
                    "matched_model": query["model"],
                    "matched_component": query["component"],
                }
            )
    return entries


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
        "driver_support_sources": _build_driver_support_sources(snapshot, segment="general"),
    }
