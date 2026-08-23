"""Event log, reliability, battery, command playbook, bottleneck, driver gaps, scan diff, AI chat."""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

from django.conf import settings

from .driver_lookup import resolve_driver_sources
from .extended_diagnostics import driver_update_url
from .powershell import run_powershell_stdout


def collect_event_log_digest(days: int = 7, limit: int = 25) -> dict:
    if sys.platform != "win32":
        return {"available": False, "events": [], "note": "Windows only"}

    script = f"""
    $start = (Get-Date).AddDays(-{days})
    $levels = 1,2,3
    $events = Get-WinEvent -FilterHashtable @{{
      LogName='System','Application'; Level=$levels; StartTime=$start
    }} -MaxEvents {limit} -ErrorAction SilentlyContinue |
    Select-Object TimeCreated, LevelDisplayName, ProviderName, Id, Message
    if (-not $events) {{ '[]' }} else {{
      $events | ForEach-Object {{
        $msg = $_.Message
        if ($msg.Length -gt 280) {{ $msg = $msg.Substring(0, 280) + '…' }}
        [ordered]@{{
          TimeCreated = $_.TimeCreated.ToString('o')
          Level = $_.LevelDisplayName
          Provider = $_.ProviderName
          Id = $_.Id
          Message = $msg
        }}
      }} | ConvertTo-Json -Compress
    }}
    """
    raw = run_powershell_stdout(script, timeout=60)
    events = []
    if raw:
        try:
            data = json.loads(raw)
            events = data if isinstance(data, list) else [data]
        except json.JSONDecodeError:
            pass
    return {
        "available": bool(events),
        "days": days,
        "events": events,
        "summary": _summarize_events(events),
    }


def _summarize_events(events: list) -> dict:
    counts = {"Critical": 0, "Error": 0, "Warning": 0}
    for e in events:
        level = e.get("Level") or ""
        if level in counts:
            counts[level] += 1
    return counts


def collect_reliability_digest(limit: int = 20) -> dict:
    if sys.platform != "win32":
        return {"available": False, "records": []}

    script = f"""
    $records = Get-CimInstance Win32_ReliabilityRecords -ErrorAction SilentlyContinue |
      Sort-Object TimeGenerated -Descending |
      Select-Object -First {limit} |
      Select-Object TimeGenerated, SourceName, EventIdentifier, Message, ProductName, RecordType
    if (-not $records) {{ '[]' }} else {{
      $records | ForEach-Object {{
        $msg = $_.Message
        if ($msg -and $msg.Length -gt 200) {{ $msg = $msg.Substring(0, 200) + '…' }}
        [ordered]@{{
          TimeGenerated = $_.TimeGenerated
          SourceName = $_.SourceName
          EventIdentifier = $_.EventIdentifier
          Message = $msg
          ProductName = $_.ProductName
          RecordType = $_.RecordType
        }}
      }} | ConvertTo-Json -Compress
    }}
    """
    raw = run_powershell_stdout(script, timeout=45)
    records = []
    if raw:
        try:
            data = json.loads(raw)
            records = data if isinstance(data, list) else [data]
        except json.JSONDecodeError:
            pass
    failures = sum(1 for r in records if str(r.get("RecordType")) in ("1", "Software", "2"))
    return {
        "available": bool(records),
        "records": records,
        "failure_count": failures,
        "note": "From Windows Reliability Monitor (Win32_ReliabilityRecords).",
    }


def collect_battery_status() -> dict:
    if sys.platform != "win32":
        return {"available": False}

    script = r"""
    $bat = Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue
    $reportPath = Join-Path $env:USERPROFILE 'battery-report.html'
    $reportGenerated = $false
    try {
      powercfg /batteryreport /output $reportPath /duration 14 2>$null | Out-Null
      $reportGenerated = Test-Path $reportPath
    } catch {}
    if (-not $bat) {
      @{ available = $false; note = 'No battery detected (desktop or AC-only).' } | ConvertTo-Json -Compress
      exit
    }
    $b = $bat | Select-Object -First 1
    @{
      available = $true
      name = $b.Name
      status = $b.BatteryStatus
      estimatedChargeRemaining = $b.EstimatedChargeRemaining
      designCapacity = $b.DesignCapacity
      fullChargeCapacity = $b.FullChargeCapacity
      chemistry = $b.Chemistry
      report_path = $(if ($reportGenerated) { $reportPath } else { $null })
    } | ConvertTo-Json -Compress
    """
    raw = run_powershell_stdout(script, timeout=90)
    if not raw:
        return {"available": False, "note": "Could not read battery status."}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {"available": False}
    except json.JSONDecodeError:
        return {"available": False}


def rank_startup_programs(startup: dict) -> dict:
    programs = startup.get("programs") or []
    ranked = []
    heavy_hints = ("update", "steam", "discord", "spotify", "adobe", "chrome", "teams", "onedrive")
    for p in programs:
        name = (p.get("Name") or "").strip()
        cmd = (p.get("Command") or "").lower()
        impact = "low"
        if any(h in cmd or h in name.lower() for h in heavy_hints):
            impact = "high"
        elif len(cmd) > 120:
            impact = "medium"
        ranked.append({**p, "impact": impact})
    ranked.sort(key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.get("impact"), 3))
    return {"programs": ranked[:30], "count": len(ranked)}


def build_command_playbook(snapshot: dict) -> list[dict]:
    """Copy-paste remediation commands tailored to this scan."""
    hw = snapshot.get("hardware", {})
    health = snapshot.get("health", {})
    software = snapshot.get("software", {})
    commands = []

    for check in health.get("checks", []):
        if check.get("id", "").startswith("disk_") and check.get("severity") in ("critical", "warning"):
            commands.append(
                {
                    "title": "Free disk space",
                    "category": "disk",
                    "command": "cleanmgr /d C:",
                    "description": "Opens Disk Cleanup for C: (review before deleting).",
                    "admin": False,
                }
            )
            commands.append(
                {
                    "title": "Storage sense (PowerShell)",
                    "category": "disk",
                    "command": "Start-Process 'ms-settings:storage'",
                    "description": "Opens Windows Storage settings.",
                    "admin": False,
                }
            )
            break

    mem_pct = hw.get("live_metrics", {}).get("memory", {}).get("percent_used", 0)
    if mem_pct >= 80:
        commands.append(
            {
                "title": "List top memory processes",
                "category": "performance",
                "command": "Get-Process | Sort-Object WorkingSet -Descending | Select-Object -First 15 Name, @{n='MB';e={[int]($_.WS/1MB)}}",
                "description": "PowerShell — see what is using RAM.",
                "admin": False,
            }
        )

    junk = snapshot.get("cleanup", {}).get("junk_files", {})
    if (junk.get("total_reclaimable_mb") or 0) >= 512:
        commands.extend([
            {
                "title": "Clear user temp files",
                "category": "cleanup",
                "command": 'Remove-Item "$env:TEMP\\*" -Recurse -Force -ErrorAction SilentlyContinue',
                "description": "Clears your user temp folder. Temp files regenerate automatically.",
                "admin": False,
            },
            {
                "title": "Empty Recycle Bin",
                "category": "cleanup",
                "command": "Clear-RecycleBin -Force -ErrorAction SilentlyContinue",
                "description": "Permanently empties the Recycle Bin.",
                "admin": False,
            },
        ])

    winget = software.get("outdated_winget", {})
    if winget.get("packages"):
        cmds = snapshot.get("winget_batch_command") or "winget upgrade --all --disable-interactivity"
        commands.append(
            {
                "title": "Upgrade outdated apps (winget)",
                "category": "software",
                "command": cmds,
                "description": "Review list in Updates tab before running.",
                "admin": False,
            }
        )

    commands.extend(
        [
            {
                "title": "System File Checker",
                "category": "repair",
                "command": "sfc /scannow",
                "description": "Scans protected Windows files (Admin CMD).",
                "admin": True,
            },
            {
                "title": "DISM restore health",
                "category": "repair",
                "command": "DISM /Online /Cleanup-Image /RestoreHealth",
                "description": "Repairs Windows component store (Admin CMD).",
                "admin": True,
            },
            {
                "title": "Open System Information",
                "category": "info",
                "command": "msinfo32",
                "description": "Same data source family as this scan (WMI).",
                "admin": False,
            },
            {
                "title": "Open Reliability Monitor",
                "category": "info",
                "command": "perfmon /rel",
                "description": "View stability history and app failures.",
                "admin": False,
            },
        ]
    )

    seen = set()
    unique = []
    for c in commands:
        key = c["command"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)
    return unique[:12]


def analyze_bottleneck(snapshot: dict) -> dict:
    hw = snapshot.get("hardware", {})
    bench = snapshot.get("benchmark", {})
    metrics = hw.get("live_metrics", {})
    mem = metrics.get("memory", {})
    cpu_pct = metrics.get("cpu_percent") or 0
    mem_pct = mem.get("percent_used") or 0
    cpu_score = bench.get("cpu_score") or 50
    disk_score = bench.get("disk_score") or 50

    scores = {
        "cpu": 100 - min(100, cpu_pct) * 0.5 + cpu_score * 0.5,
        "memory": 100 - mem_pct,
        "disk": disk_score or 50,
    }
    weakest = min(scores, key=scores.get)
    labels = {
        "cpu": "CPU-bound — processor or background load is the main limit.",
        "memory": "RAM-bound — add memory or reduce running apps.",
        "disk": "Disk-bound — storage speed or free space is the main limit.",
    }
    use_case = []
    if scores["disk"] < 60:
        use_case.append("Everyday tasks and boot may feel slow until disk is upgraded or freed.")
    if scores["memory"] < 60:
        use_case.append("Multitasking and browser tabs will struggle.")
    if scores["cpu"] < 60:
        use_case.append("Gaming, video, and compile workloads may be CPU-limited.")

    return {
        "scores": {k: round(v, 1) for k, v in scores.items()},
        "primary_bottleneck": weakest,
        "summary": labels.get(weakest, ""),
        "use_case_notes": use_case,
        "workload_guess": _guess_workload(snapshot),
    }


def _guess_workload(snapshot: dict) -> str:
    comps = snapshot.get("hardware", {}).get("components_by_manufacturer", [])
    gpu = next((c for c in comps if c.get("category") == "GPU"), None)
    if gpu and any(x in (gpu.get("name") or "").lower() for x in ("rtx", "rx ", "arc", "gtx")):
        return "Gaming / creative (discrete GPU detected)"
    return "General desktop / office"


def _build_msi_motherboard_advisory(board: dict, snapshot: dict) -> str:
    manufacturer = (board.get("manufacturer") or "").lower()
    product = board.get("product", "")
    nvidia_present = any(
        (comp.get("category") == "GPU" and "nvidia" in (comp.get("manufacturer") or "").lower())
        for comp in snapshot.get("hardware", {}).get("components_by_manufacturer", [])
    )
    if manufacturer == "msi":
        note = (
            "MSI motherboard detected. Update the BIOS and chipset drivers from MSI support first, then verify PCIe slot configuration "
            "and BIOS settings such as Above 4G Decoding / Resize BAR when using NVIDIA graphics."
        )
        if nvidia_present:
            note += " If you see GPU stability or performance issues, perform a clean NVIDIA driver install after the BIOS update."
        return note
    return "Download chipset / LAN / audio drivers for your board."


def _build_nvidia_gpu_advisory(name: str, manufacturer: str, driver_version: str | None) -> tuple[str, str | None]:
    note = (
        "NVIDIA GPU detected. Update the driver from NVIDIA support and consider a clean install if you have display, performance, or stability issues."
    )
    if driver_version:
        note += f" Installed driver version: {driver_version}."
    query = resolve_driver_sources(vendor=manufacturer, model=name, component="GPU")
    support_url = next(
        (m.get("support_url") for m in query.get("matches", []) if m.get("key") == "nvidia"),
        None,
    )
    return note, support_url


def build_driver_gap_report(snapshot: dict) -> list[dict]:
    """OEM support links + per-driver update URLs for key devices."""
    gaps = []
    seen = set()
    components = snapshot.get("hardware", {}).get("components_by_manufacturer", [])

    board = snapshot.get("hardware", {}).get("system_profile", {}).get("motherboard") or {}
    if board.get("manufacturer"):
        result = resolve_driver_sources(
            vendor=board.get("manufacturer", ""),
            model=board.get("product", ""),
            component="Motherboard",
        )
        for m in result.get("matches", []):
            key = m.get("key")
            if key in seen:
                continue
            seen.add(key)
            gaps.append(
                {
                    "device": f"{board.get('manufacturer')} {board.get('product')}",
                    "class": "Motherboard",
                    "driver_url": m.get("driver_url"),
                    "support_url": m.get("support_url"),
                    "status": "check_oem",
                    "note": _build_msi_motherboard_advisory(board, snapshot),
                }
            )

    for cat in ("GPU", "Network", "Storage"):
        for comp in components:
            if comp.get("category") != cat:
                continue
            name = comp.get("name", "")
            mfr = comp.get("manufacturer", "")
            driver_version = comp.get("details", {}).get("driver_version")
            url = comp.get("details", {}).get("update_url") or driver_update_url(name, mfr)
            key = (cat, name[:50])
            if key in seen:
                continue
            seen.add(key)
            support_url = url
            note = f"Verify driver version: {driver_version or 'unknown'}."
            if cat == "GPU" and "nvidia" in mfr.lower():
                advisory, nvidia_support_url = _build_nvidia_gpu_advisory(name, mfr, driver_version)
                note = advisory
                support_url = nvidia_support_url or support_url
            gaps.append(
                {
                    "device": name,
                    "class": cat,
                    "driver_url": url,
                    "support_url": support_url,
                    "status": "update_recommended",
                    "note": note,
                }
            )
    return gaps[:15]


def build_ms_catalog_links(snapshot: dict) -> list[dict]:
    links = []
    for gap in build_driver_gap_report(snapshot)[:5]:
        q = quote_plus(gap.get("device", ""))
        links.append(
            {
                "label": gap.get("device"),
                "catalog_url": f"https://www.catalog.update.microsoft.com/Search.aspx?q={q}",
                "learn_url": f"https://learn.microsoft.com/en-us/search/?terms={q}",
            }
        )
    return links


def enrich_duplicate_driver_advice(duplicates: list[dict]) -> list[dict]:
    out = []
    for d in duplicates:
        out.append(
            {
                **d,
                "advice": (
                    "Open Device Manager → find duplicate entries → uninstall device "
                    "(check 'Delete driver' only if you have a replacement driver ready)."
                ),
                "device_manager_cmd": "devmgmt.msc",
            }
        )
    return out


def compare_snapshots(snap_a: dict, snap_b: dict) -> dict:
    """Structured diff between two scan snapshots (B = older, A = newer)."""
    changes = []

    def _board(snap):
        return (snap.get("hardware", {}).get("system_profile") or {}).get("motherboard") or {}

    ba, bb = _board(snap_a), _board(snap_b)
    if ba.get("product") != bb.get("product"):
        changes.append(
            {
                "field": "Motherboard",
                "before": f"{bb.get('manufacturer')} {bb.get('product')}",
                "after": f"{ba.get('manufacturer')} {ba.get('product')}",
            }
        )

    ra = snap_a.get("hardware", {}).get("live_metrics", {}).get("memory", {}).get("total_gb")
    rb = snap_b.get("hardware", {}).get("live_metrics", {}).get("memory", {}).get("total_gb")
    if ra != rb:
        changes.append({"field": "RAM total", "before": f"{rb} GB", "after": f"{ra} GB"})

    sa = snap_a.get("health", {}).get("health_score")
    sb = snap_b.get("health", {}).get("health_score")
    if sa is not None and sb is not None and sa != sb:
        changes.append({"field": "Health score", "before": str(sb), "after": str(sa)})

    vols_a = {v.get("letter"): v for v in snap_a.get("hardware", {}).get("volumes", [])}
    vols_b = {v.get("letter"): v for v in snap_b.get("hardware", {}).get("volumes", [])}
    for letter, va in vols_a.items():
        vb = vols_b.get(letter)
        if not vb:
            continue
        if va.get("free_gb") != vb.get("free_gb"):
            changes.append(
                {
                    "field": f"Drive {letter} free space",
                    "before": f"{vb.get('free_gb')} GB",
                    "after": f"{va.get('free_gb')} GB",
                }
            )

    comps_a = len(snap_a.get("hardware", {}).get("components_by_manufacturer", []))
    comps_b = len(snap_b.get("hardware", {}).get("components_by_manufacturer", []))
    if comps_a != comps_b:
        changes.append(
            {
                "field": "Hardware components detected",
                "before": str(comps_b),
                "after": str(comps_a),
            }
        )

    return {"changes": changes, "change_count": len(changes)}


def summarize_compare_diff(diff: dict, scan_a, scan_b) -> str:
    """Rule-based compare summary (no API)."""
    n = diff.get("change_count", 0)
    if n == 0:
        return "No major differences detected between these two scans."
    lines = [f"Found {n} notable change(s) between scans:"]
    for c in diff.get("changes", [])[:8]:
        lines.append(f"• {c['field']}: {c['before']} → {c['after']}")
    da = scan_a.created_at.strftime("%Y-%m-%d") if scan_a else "?"
    db = scan_b.created_at.strftime("%Y-%m-%d") if scan_b else "?"
    lines.append(f"(Newer scan {da} vs older {db})")
    return "\n".join(lines)


def ai_compare_summary(diff: dict, snap_a: dict, snap_b: dict) -> str:
    api_key = settings.OPENAI_API_KEY
    if not api_key:
        return ""

    try:
        from openai import OpenAI
    except ImportError:
        return ""

    client = OpenAI(api_key=api_key)
    prompt = f"""Summarize these PC scan differences for a non-technical user in 3-5 sentences.
Focus on whether the PC improved or worsened and what to do next.

Diff JSON:
{json.dumps(diff, default=str)}

Newer snapshot hostname: {snap_a.get('hostname')}
Older snapshot hostname: {snap_b.get('hostname')}
"""
    try:
        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are a concise PC technician."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=400,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception:
        return ""


def ai_chat_reply(report, user_message: str) -> dict:
    """Answer a question using the saved scan snapshot as context."""
    snapshot = report.system_snapshot or {}
    api_key = settings.OPENAI_API_KEY

    if not api_key:
        return {
            "reply": (
                "AI chat requires OPENAI_API_KEY in your environment. "
                "Your scan data is still available in the report tabs."
            ),
            "ai_powered": False,
        }

    try:
        from openai import OpenAI
    except ImportError:
        return {"reply": "Install the openai package to use chat.", "ai_powered": False}

    compact = {
        "hostname": snapshot.get("hostname"),
        "health_score": snapshot.get("health", {}).get("health_score"),
        "system_profile": snapshot.get("hardware", {}).get("system_profile", {}).get("rows", [])[:20],
        "motherboard": snapshot.get("hardware", {}).get("system_profile", {}).get("motherboard"),
        "bottleneck": snapshot.get("bottleneck"),
        "health_checks": snapshot.get("health", {}).get("checks"),
        "event_summary": snapshot.get("event_log", {}).get("summary"),
        "ai_summary": (report.ai_analysis or {}).get("plain_english_summary"),
    }

    client = OpenAI(api_key=api_key)
    try:
        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are PC Checker Extreme assistant. Answer using ONLY the scan context. "
                        "Be practical; suggest commands from the playbook when relevant. "
                        "Do not invent hardware not in the snapshot."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Scan context:\n{json.dumps(compact, default=str)}\n\nQuestion: {user_message}",
                },
            ],
            temperature=0.4,
            max_tokens=600,
        )
        reply = (response.choices[0].message.content or "").strip()
        return {"reply": reply, "ai_powered": True}
    except Exception as exc:
        return {"reply": f"AI chat failed: {exc}", "ai_powered": False}
