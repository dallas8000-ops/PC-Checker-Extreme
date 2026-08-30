import json
import os
import socket
import sys

from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET, require_http_methods

from .models import ScanReport
from .report_context import build_report_context
from .services.driver_lookup import resolve_driver_sources
from .services.hardware_collector import probe_motherboard_live
from .services.scan_insights import ai_chat_reply, ai_compare_summary, compare_snapshots, summarize_compare_diff
from .services.scan_runner import start_background_scan


def _report_queryset_for(request):
    if request.user.is_authenticated:
        return ScanReport.objects.filter(owner=request.user)
    return ScanReport.objects.none()


def _api_key_ok(request) -> bool:
    expected = getattr(settings, "PCC_API_KEY", "") or ""
    if not expected:
        return True
    return request.headers.get("X-API-Key") == expected or request.GET.get("api_key") == expected


def _live_telemetry():
    try:
        import psutil

        mem = psutil.virtual_memory()
        disks = []
        total_free = 0.0
        for part in psutil.disk_partitions(all=True):
            if part.fstype and "cdrom" in (part.opts or "").lower():
                continue
            mount = part.mountpoint.rstrip("\\")
            letter = mount if len(mount) <= 3 else mount
            try:
                usage = psutil.disk_usage(part.mountpoint)
                free_gb = round(usage.free / (1024**3), 1)
                total_free += free_gb
                disks.append(
                    {
                        "label": letter.upper() if ":" in letter else letter,
                        "percent": round(usage.percent, 1),
                        "free_gb": free_gb,
                    }
                )
            except (PermissionError, OSError):
                continue
        primary = disks[0]["percent"] if disks else 0
        return {
            "cpu": round(psutil.cpu_percent(interval=0.3), 1),
            "ram": round(mem.percent, 1),
            "ram_total_gb": round(mem.total / (1024**3), 1),
            "disk": primary,
            "disk_free_gb": round(total_free, 1),
            "disk_count": len(disks),
            "disks": disks,
        }
    except Exception:
        return {
            "cpu": 0,
            "ram": 0,
            "ram_total_gb": 0,
            "disk": 0,
            "disk_free_gb": 0,
            "disk_count": 0,
            "disks": [],
        }


def landing(request):
    return render(request, "diagnostics/landing.html")


def _motherboard_for_dashboard(last_complete_scan):
    """Prefer last scan snapshot; on Windows fall back to live msinfo-style probe."""
    if last_complete_scan:
        hw = (last_complete_scan.system_snapshot or {}).get("hardware", {})
        board = (hw.get("system_profile") or {}).get("motherboard")
        if board and not _board_is_empty(board):
            return board
        wmi = hw.get("wmi") or {}
        board = wmi.get("motherboard_resolved")
        if board and not _board_is_empty(board):
            return board
        for comp in hw.get("components_by_manufacturer", []):
            if comp.get("category") == "Motherboard":
                return {
                    "manufacturer": comp.get("manufacturer"),
                    "product": comp.get("name"),
                    "version": (comp.get("details") or {}).get("version", ""),
                    "serial": (comp.get("details") or {}).get("serial", ""),
                    "source": "scan",
                }

    if sys.platform == "win32":
        try:
            return probe_motherboard_live()
        except Exception:
            pass
    return None


def _board_is_empty(board: dict) -> bool:
    product = (board.get("product") or "").strip().lower()
    if not product or product in ("motherboard", "unknown"):
        return True
    mfr = (board.get("manufacturer") or "").strip().lower()
    return mfr in ("", "unknown")


def home(request):
    is_cloud_host = os.environ.get("RENDER") == "true" or sys.platform != "win32"
    recent = list(_report_queryset_for(request)[:8])
    history_scores = [
        s.overall_score for s in reversed(recent) if s.overall_score is not None
    ]
    last = recent[0] if recent else None
    last_complete = next(
        (s for s in recent if s.status == ScanReport.Status.COMPLETE),
        None,
    )
    return render(
        request,
        "diagnostics/home.html",
        {
            "recent_scans": recent,
            "has_openai": bool(settings.OPENAI_API_KEY),
            "telemetry": _live_telemetry(),
            "last_scan": last,
            "last_complete_scan": last_complete,
            "chart_history_json": json.dumps(history_scores or [72, 78, 81, 85]),
            "is_cloud_host": is_cloud_host,
            "motherboard": _motherboard_for_dashboard(last_complete),
        },
    )


def signup(request):
    if request.user.is_authenticated:
        return redirect("diagnostics:home")

    form = UserCreationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("diagnostics:home")

    return render(request, "registration/signup.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def start_scan(request):
    if request.method == "GET":
        return redirect("diagnostics:home")

    include_ai = request.POST.get("include_ai", "on") == "on"
    include_slow_checks = request.POST.get("include_slow_checks") == "on"
    include_software_inventory = request.POST.get("include_software_inventory") == "on"
    report = ScanReport.objects.create(
        owner=request.user,
        status=ScanReport.Status.SCANNING,
        hostname=socket.gethostname(),
        scan_progress=0,
        scan_stage="Queued…",
    )
    start_background_scan(
        report.id,
        include_ai,
        include_slow_checks,
        include_software_inventory,
    )
    return redirect("diagnostics:scan_progress", report_id=report.id)


@login_required
def scan_progress(request, report_id):
    report = get_object_or_404(_report_queryset_for(request), pk=report_id)
    return render(request, "diagnostics/scan_progress.html", {"report": report})


@login_required
@require_GET
def scan_status(request, report_id):
    if not _api_key_ok(request):
        return JsonResponse({"error": "Invalid API key"}, status=403)
    report = get_object_or_404(_report_queryset_for(request), pk=report_id)
    data = {
        "id": str(report.id),
        "status": report.status,
        "progress": report.scan_progress,
        "stage": report.scan_stage,
        "error": report.error_message,
    }
    if report.status == ScanReport.Status.COMPLETE:
        data["redirect"] = f"/scan/{report.id}/"
    elif report.status == ScanReport.Status.FAILED:
        data["redirect"] = f"/scan/{report.id}/"
    return JsonResponse(data)


@login_required
def report_detail(request, report_id):
    report = get_object_or_404(_report_queryset_for(request), pk=report_id)
    if report.status == ScanReport.Status.FAILED:
        return render(
            request,
            "diagnostics/error.html",
            {"message": report.error_message, "report": report},
        )
    if report.status != ScanReport.Status.COMPLETE:
        return redirect("diagnostics:scan_progress", report_id=report.id)
    ctx = build_report_context(report)
    return render(request, "diagnostics/report.html", ctx)


@login_required
def compare_scans(request):
    completed = list(
        _report_queryset_for(request)
        .filter(status=ScanReport.Status.COMPLETE)
        .order_by("-created_at")[:10]
    )
    id_a = request.GET.get("a")
    id_b = request.GET.get("b")
    scan_a = scan_b = None
    if id_a:
        scan_a = _report_queryset_for(request).filter(
            pk=id_a,
            status=ScanReport.Status.COMPLETE,
        ).first()
    if id_b:
        scan_b = _report_queryset_for(request).filter(
            pk=id_b,
            status=ScanReport.Status.COMPLETE,
        ).first()
    if not scan_a and len(completed) >= 1:
        scan_a = completed[0]
    if not scan_b and len(completed) >= 2:
        scan_b = completed[1]

    def metrics(scan):
        if not scan:
            return {}
        snap = scan.system_snapshot or {}
        hw = snap.get("hardware", {})
        return {
            "score": scan.overall_score,
            "hostname": scan.hostname,
            "date": scan.created_at,
            "volumes": hw.get("volumes", []),
            "ram_gb": hw.get("live_metrics", {}).get("memory", {}).get("total_gb"),
        }

    ma, mb = metrics(scan_a), metrics(scan_b)
    score_delta = None
    if ma.get("score") is not None and mb.get("score") is not None:
        score_delta = ma["score"] - mb["score"]

    diff = None
    compare_summary = ""
    ai_compare = ""
    if scan_a and scan_b and scan_a.id != scan_b.id:
        diff = compare_snapshots(scan_a.system_snapshot or {}, scan_b.system_snapshot or {})
        compare_summary = summarize_compare_diff(diff, scan_a, scan_b)
        ai_compare = ai_compare_summary(diff, scan_a.system_snapshot or {}, scan_b.system_snapshot or {})

    return render(
        request,
        "diagnostics/compare.html",
        {
            "completed_scans": completed,
            "scan_a": scan_a,
            "scan_b": scan_b,
            "metrics_a": ma,
            "metrics_b": mb,
            "score_delta": score_delta,
            "diff": diff,
            "compare_summary": compare_summary,
            "ai_compare_summary": ai_compare,
            "has_openai": bool(settings.OPENAI_API_KEY),
        },
    )


@login_required
@require_http_methods(["POST"])
def scan_chat(request, report_id):
    report = get_object_or_404(
        _report_queryset_for(request),
        pk=report_id,
        status=ScanReport.Status.COMPLETE,
    )
    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        body = {}
    message = (body.get("message") or request.POST.get("message") or "").strip()
    if not message:
        return JsonResponse({"error": "Message required"}, status=400)
    if len(message) > 2000:
        return JsonResponse({"error": "Message too long"}, status=400)
    result = ai_chat_reply(report, message)
    return JsonResponse(result)


@login_required
@require_GET
def export_html(request, report_id):
    report = get_object_or_404(
        _report_queryset_for(request),
        pk=report_id,
        status=ScanReport.Status.COMPLETE,
    )
    html = render_to_string(
        "diagnostics/export_report.html",
        build_report_context(report),
    )
    response = HttpResponse(html, content_type="text/html; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="pc-checker-{report.hostname}-{report.id}.html"'
    return response


@login_required
@require_GET
def export_pdf(request, report_id):
    report = get_object_or_404(
        _report_queryset_for(request),
        pk=report_id,
        status=ScanReport.Status.COMPLETE,
    )
    html = render_to_string(
        "diagnostics/export_report.html",
        build_report_context(report),
    )
    try:
        from io import BytesIO

        from xhtml2pdf import pisa

        result = BytesIO()
        pisa.CreatePDF(html, dest=result)
        response = HttpResponse(result.getvalue(), content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="pc-checker-{report.hostname}-{report.id}.pdf"'
        )
        return response
    except ImportError:
        return HttpResponse(
            "PDF export requires: pip install xhtml2pdf. Use HTML export instead.",
            status=501,
        )


@login_required
@require_GET
def report_json(request, report_id):
    if not _api_key_ok(request):
        return JsonResponse({"error": "Invalid API key"}, status=403)
    report = get_object_or_404(_report_queryset_for(request), pk=report_id)
    return JsonResponse(
        {
            "id": str(report.id),
            "status": report.status,
            "progress": report.scan_progress,
            "stage": report.scan_stage,
            "hostname": report.hostname,
            "overall_score": report.overall_score,
            "system_snapshot": report.system_snapshot,
            "ai_analysis": report.ai_analysis,
            "created_at": report.created_at.isoformat(),
        }
    )


@require_GET
def api_health(request):
    from django.db import connection
    try:
        connection.ensure_connection()
        db_ok = True
    except Exception:
        db_ok = False
    status = "ok" if db_ok else "degraded"
    return JsonResponse({"status": status, "db": db_ok, "app": "PC Checker Extreme"},
                        status=200 if db_ok else 503)


@require_GET
def driver_lookup(request):
    if not _api_key_ok(request):
        return JsonResponse({"error": "Invalid API key"}, status=403)

    vendor = (request.GET.get("vendor") or "").strip()
    model = (request.GET.get("model") or "").strip()
    component = (request.GET.get("component") or "").strip()
    hardware_id = (request.GET.get("hardware_id") or "").strip()
    segment = (request.GET.get("segment") or "general").strip().lower()

    if not any([vendor, model, component, hardware_id]):
        return JsonResponse(
            {
                "error": "Provide at least one of: vendor, model, component, hardware_id",
            },
            status=400,
        )

    payload = resolve_driver_sources(
        vendor=vendor,
        model=model,
        component=component,
        hardware_id=hardware_id,
        segment=segment,
    )
    return JsonResponse(payload)
