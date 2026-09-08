from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from .services.health_checks import run_health_checks
from .services.scan_insights import build_command_playbook
from .services import remediation


class DriverUpdateHealthTests(SimpleTestCase):
    def test_pending_driver_updates_are_reported_as_warning(self):
        result = run_health_checks(
            {
                "live_metrics": {
                    "memory": {"percent_used": 20},
                    "disks": [],
                }
            },
            {
                "outdated_winget": {"count": 0, "packages": []},
                "windows_updates": {
                    "count": 0,
                    "updates": [],
                    "driver_count": 2,
                    "drivers": [
                        {"Title": "Test display driver"},
                        {"Title": "Test network driver"},
                    ],
                },
            },
        )

        driver_check = next(check for check in result["checks"] if check["id"] == "driver_updates")
        self.assertEqual(driver_check["severity"], "warning")
        self.assertIn("2 driver update(s)", driver_check["title"])


class CleanupHealthTests(SimpleTestCase):
    def test_cleanup_findings_are_reported_and_added_to_playbook(self):
        cleanup = {
            "junk_files": {"total_reclaimable_mb": 3072},
            "top_processes": {
                "resource_hog": {"name": "ExampleApp", "memory_mb": 2048}
            },
            "network": {"available": True, "internet_connected": False, "checked_host": "8.8.8.8"},
        }
        result = run_health_checks(
            {"live_metrics": {"memory": {"percent_used": 20}, "disks": []}},
            {"outdated_winget": {"count": 0}, "windows_updates": {"count": 0}},
            cleanup,
        )

        finding_ids = {check["id"] for check in result["checks"]}
        self.assertTrue({"junk_files_high", "process_memory_hog", "no_internet"}.issubset(finding_ids))

        commands = build_command_playbook({"cleanup": cleanup, "hardware": {"live_metrics": {}}})
        self.assertTrue(any(command["category"] == "cleanup" for command in commands))


class RemediationUiTests(SimpleTestCase):
    def test_fix_buttons_post_to_remediation_api(self):
        js_path = Path(__file__).resolve().parent / "static" / "diagnostics" / "js" / "app.js"
        js = js_path.read_text(encoding="utf-8")

        self.assertIn("btn-fix", js)
        self.assertIn('fetch("/api/fix/"', js)
        self.assertIn("data-fix-id", js)

    def test_report_tools_does_not_register_a_second_fix_handler(self):
        js_path = Path(__file__).resolve().parent / "static" / "diagnostics" / "js" / "report-tools.js"
        js = js_path.read_text(encoding="utf-8")

        self.assertNotIn('querySelectorAll(".btn-fix")', js)
        self.assertNotIn('fetch("/api/fix/"', js)

    @patch("diagnostics.services.remediation.run_powershell")
    @patch("diagnostics.services.remediation._is_admin", return_value=False)
    @patch("diagnostics.services.remediation.os.remove")
    @patch("diagnostics.services.remediation.os.path.isfile", return_value=True)
    def test_memory_integrity_requests_elevation_when_app_is_not_admin(
        self, _is_file, _remove, _is_admin, run_powershell
    ):
        run_powershell.return_value = ("", "", 0)

        with patch("diagnostics.services.remediation.tempfile.mktemp", return_value="C:\\temp\\fix.result"):
            result = remediation.fix_memory_integrity()

        self.assertTrue(result["ok"])
        self.assertTrue(run_powershell.called)
        self.assertIn("Verb RunAs", run_powershell.call_args.args[0])
