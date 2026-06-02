"""Run a diagnostic scan from Task Scheduler / cron.

Example (Windows Task Scheduler weekly):
  cd "C:\\Software Projects\\PC Checker Extreme"
  .venv\\Scripts\\python.exe manage.py run_scheduled_scan
"""
import socket

from django.core.management.base import BaseCommand

from diagnostics.models import ScanReport
from diagnostics.services.scanner import run_full_scan


class Command(BaseCommand):
    help = "Run a full PC scan and save report (for scheduled tasks)"

    def add_arguments(self, parser):
        parser.add_argument("--no-ai", action="store_true")
        parser.add_argument("--updates", action="store_true", help="Include winget/update checks")

    def handle(self, *args, **options):
        report = ScanReport.objects.create(
            status=ScanReport.Status.SCANNING,
            hostname=socket.gethostname(),
        )
        try:
            result = run_full_scan(
                include_ai=not options["no_ai"],
                include_slow_checks=options["updates"],
            )
            report.hostname = result["snapshot"].get("hostname") or socket.gethostname()
            report.system_snapshot = result["snapshot"]
            report.ai_analysis = result["ai_analysis"]
            report.overall_score = result.get("overall_score")
            report.status = ScanReport.Status.COMPLETE
            report.scan_progress = 100
            report.scan_stage = "Complete"
            report.save()
            self.stdout.write(self.style.SUCCESS(f"Scan complete: {report.id} score={report.overall_score}"))
        except Exception as exc:
            report.status = ScanReport.Status.FAILED
            report.error_message = str(exc)
            report.save()
            self.stderr.write(str(exc))
            raise
