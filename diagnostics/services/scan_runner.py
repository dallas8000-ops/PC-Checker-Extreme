"""Background scan execution with progress updates."""
import socket
import threading

from django.db import connection

from diagnostics.models import ScanReport

from .scanner import run_full_scan


def _update_progress(report_id, progress: int, stage: str, status: str | None = None):
    updates = {"scan_progress": min(100, max(0, progress)), "scan_stage": stage}
    if status:
        updates["status"] = status
    ScanReport.objects.filter(pk=report_id).update(**updates)


def _progress_callback(report_id):
    def callback(progress: int, stage: str):
        _update_progress(report_id, progress, stage)

    return callback


def _run_scan_job(
    report_id,
    include_ai: bool,
    include_slow_checks: bool,
    include_software_inventory: bool,
):
    connection.close()
    report = ScanReport.objects.get(pk=report_id)
    try:
        _update_progress(report_id, 2, "Starting scan…", ScanReport.Status.SCANNING)
        result = run_full_scan(
            include_ai=include_ai,
            include_slow_checks=include_slow_checks,
            include_software_inventory=include_software_inventory,
            progress_callback=_progress_callback(report_id),
        )
        snapshot = result["snapshot"]
        report = ScanReport.objects.get(pk=report_id)
        report.hostname = snapshot.get("hostname") or socket.gethostname()
        report.system_snapshot = snapshot
        report.ai_analysis = result["ai_analysis"]
        report.overall_score = result.get("overall_score")
        report.status = ScanReport.Status.COMPLETE
        report.scan_progress = 100
        report.scan_stage = "Complete"
        report.error_message = ""
        report.save()
    except Exception as exc:
        err = str(exc)
        if "WinError 2" in err or "cannot find the file" in err.lower():
            from .powershell import get_powershell_executable

            err = (
                "Could not start PowerShell. "
                f"Tried: {get_powershell_executable()}."
            )
        ScanReport.objects.filter(pk=report_id).update(
            status=ScanReport.Status.FAILED,
            error_message=err,
            scan_stage="Failed",
        )
    finally:
        connection.close()


def start_background_scan(
    report_id,
    include_ai: bool,
    include_slow_checks: bool,
    include_software_inventory: bool = False,
):
    thread = threading.Thread(
        target=_run_scan_job,
        args=(report_id, include_ai, include_slow_checks, include_software_inventory),
        daemon=True,
    )
    thread.start()
