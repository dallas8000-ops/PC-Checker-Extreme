"""AI-powered system review and interactive suggestions via OpenAI."""
import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

ANALYSIS_SCHEMA_HINT = """
Return valid JSON only with this structure:
{
  "summary": "2-3 sentence overall assessment",
  "overall_score": 0-100,
  "health_grade": "A|B|C|D|F",
  "component_reviews": [
    {
      "category": "CPU|GPU|RAM|Storage|Motherboard|Network|Software",
      "component_name": "string",
      "manufacturer": "string",
      "status": "excellent|good|fair|poor|unknown",
      "findings": "brief finding",
      "recommendation": "actionable suggestion or null"
    }
  ],
  "priority_actions": [
    {"priority": "high|medium|low", "title": "string", "description": "string", "category": "hardware|software|security|performance"}
  ],
  "upgrade_suggestions": [
    {"part": "string", "reason": "string", "estimated_impact": "low|medium|high"}
  ],
  "software_update_plan": [
    {"app_name": "string", "urgency": "high|medium|low", "notes": "string"}
  ],
  "interactive_sections": [
    {
      "id": "unique_slug",
      "title": "section title",
      "icon": "emoji single char",
      "expandable_summary": "one line for collapsed state",
      "details": "markdown-friendly longer explanation",
      "related_component_ids": []
    }
  ],
  "plain_english_summary": "One short paragraph a non-technical user can understand",
  "fix_actions": [
    {"step": 1, "title": "string", "detail": "specific action e.g. Free 20GB on C:", "category": "disk|driver|bios|software|security"}
  ]
}
"""


def _fallback_analysis(snapshot: dict, health: dict) -> dict:
    components = snapshot.get("hardware", {}).get("components_by_manufacturer", [])
    outdated = snapshot.get("software", {}).get("outdated_winget", {}).get("packages", [])

    reviews = []
    for comp in components[:12]:
        reviews.append(
            {
                "category": comp.get("category", "Hardware"),
                "component_name": comp.get("name", "Unknown"),
                "manufacturer": comp.get("manufacturer", "Unknown"),
                "status": "good",
                "findings": "Detected via WMI. Enable OpenAI for deeper analysis.",
                "recommendation": None,
            }
        )

    actions = []
    for check in health.get("checks", []):
        if check["severity"] in ("critical", "warning"):
            actions.append(
                {
                    "priority": "high" if check["severity"] == "critical" else "medium",
                    "title": check["title"],
                    "description": check["message"],
                    "category": "performance",
                }
            )

    software_plan = [
        {
            "app_name": p.get("name", "App"),
            "urgency": "medium",
            "notes": f"Update {p.get('current_version')} → {p.get('available_version')}",
        }
        for p in outdated[:15]
    ]

    score = health.get("health_score", 75)
    grade = "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D" if score >= 40 else "F"

    board = next(
        (c for c in components if c.get("category") == "Motherboard"),
        {},
    )
    plain = (
        f"This PC scored {score}/100 on our health check. "
        f"Key hardware includes {board.get('manufacturer', 'your')} {board.get('name', 'motherboard')}. "
        f"Review priority actions below. Add OPENAI_API_KEY for a richer AI-written summary."
    )

    fix_actions = [
        {
            "step": i + 1,
            "title": a["title"],
            "detail": a["description"],
            "category": a.get("category", "performance"),
        }
        for i, a in enumerate(actions[:6])
    ]

    return {
        "summary": (
            "Local scan complete. Add OPENAI_API_KEY in .env for AI-generated insights, "
            "upgrade paths, and personalized recommendations."
        ),
        "plain_english_summary": plain,
        "fix_actions": fix_actions,
        "overall_score": score,
        "health_grade": grade,
        "component_reviews": reviews,
        "priority_actions": actions[:8],
        "upgrade_suggestions": [],
        "software_update_plan": software_plan,
        "interactive_sections": [
            {
                "id": "local_scan",
                "title": "Local diagnostics",
                "icon": "🔧",
                "expandable_summary": "Hardware and software inventory captured without cloud AI.",
                "details": "Configure OPENAI_API_KEY to unlock full AI review.",
                "related_component_ids": [],
            }
        ],
        "ai_powered": False,
    }


def analyze_system(snapshot: dict) -> dict:
    health = snapshot.get("health", {})
    api_key = settings.OPENAI_API_KEY

    if not api_key:
        result = _fallback_analysis(snapshot, health)
        result["ai_powered"] = False
        return result

    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("openai package not installed")
        return _fallback_analysis(snapshot, health)

    client = OpenAI(api_key=api_key)
    model = settings.OPENAI_MODEL

    compact = {
        "hostname": snapshot.get("hostname"),
        "hardware_components": snapshot.get("hardware", {}).get("components_by_manufacturer"),
        "system_profile": snapshot.get("hardware", {}).get("system_profile", {}).get("rows", [])[:25],
        "live_metrics": snapshot.get("hardware", {}).get("live_metrics"),
        "health_checks": health.get("checks"),
        "health_score": health.get("health_score"),
        "bottleneck": snapshot.get("bottleneck"),
        "outdated_apps": snapshot.get("software", {}).get("outdated_winget", {}).get("packages", [])[:30],
        "windows_updates_count": snapshot.get("software", {}).get("windows_updates", {}).get("count", 0),
        "driver_updates": snapshot.get("software", {}).get("windows_updates", {}).get("drivers", [])[:25],
        "installed_programs_sample": snapshot.get("software", {}).get("installed", {}).get("programs", [])[:25],
        "smart": snapshot.get("hardware", {}).get("smart"),
        "benchmark": snapshot.get("benchmark"),
        "security": snapshot.get("security"),
        "event_log_summary": snapshot.get("event_log", {}).get("summary"),
        "reliability_failures": snapshot.get("reliability", {}).get("failure_count"),
        "top_processes": snapshot.get("cleanup", {}).get("top_processes", {}).get("processes", [])[:10],
        "junk_files": snapshot.get("cleanup", {}).get("junk_files", {}),
        "network_status": snapshot.get("cleanup", {}).get("network", {}),
        "duplicate_drivers": snapshot.get("duplicate_drivers", [])[:10],
        "command_playbook_titles": [c.get("title") for c in snapshot.get("command_playbook", [])[:8]],
    }

    prompt = f"""You are an expert PC technician. Analyze this system diagnostic snapshot.
Identify each component by manufacturer where possible. Flag bottlenecks, security risks, and outdated software.
Reference event_log_summary and reliability_failures when relevant. Suggest commands from command_playbook_titles when helpful.
Be specific and practical. {ANALYSIS_SCHEMA_HINT}

System snapshot:
{json.dumps(compact, indent=2, default=str)}
"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You output only valid JSON matching the requested schema. No markdown fences.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
        data["ai_powered"] = True
        return data
    except Exception as exc:
        logger.exception("AI analysis failed: %s", exc)
        fallback = _fallback_analysis(snapshot, health)
        fallback["ai_error"] = str(exc)
        fallback["ai_powered"] = False
        return fallback
