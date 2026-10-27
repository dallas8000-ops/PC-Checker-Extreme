from pathlib import Path
from unittest.mock import patch

from django.test import Client, SimpleTestCase, TestCase

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


class DeviceToolsAnalysisTests(SimpleTestCase):
    def test_usb_problem_and_failing_disk_are_flagged(self):
        from .services.device_tools import analyze_status

        raw = {
            "usb": {
                "problem_devices": {"name": "Unknown USB Device", "pnp_class": "USB",
                                    "instance_id": "USB\\VID_0000&PID_0002\\1", "code": 43},
                "controllers": [{"name": "Intel USB 3.20 xHCI", "status": "OK"}],
                "selective_suspend_ac": 1,
                "events": [],
            },
            "storage": {
                "disks": [{"name": "Old HDD", "health": "Warning", "read_errors": 3}],
                "volumes": [{"letter": "C", "drive_type": "Fixed", "health": "Healthy",
                             "size_gb": 100, "free_gb": 5}],
                "events": [{"provider": "disk", "id": 7, "message": "bad block"}],
            },
            "is_admin": False,
        }
        result = analyze_status(raw)

        usb_titles = " ".join(f["title"] for f in result["usb"]["findings"])
        self.assertIn("code 43", usb_titles)
        self.assertIn("selective suspend", usb_titles)
        disk = {f["severity"] for f in result["storage"]["findings"]}
        self.assertIn("critical", disk)
        titles = " ".join(f["title"] for f in result["storage"]["findings"])
        self.assertIn("only 5 GB free", titles)
        self.assertIn("disk error event", titles)

    def test_healthy_system_reports_ok(self):
        from .services.device_tools import analyze_status

        raw = {
            "usb": {"problem_devices": [], "controllers": [], "selective_suspend_ac": 0, "events": []},
            "storage": {"disks": [{"name": "NVMe", "health": "Healthy", "temperature": 40, "wear": 2}],
                        "volumes": [], "events": []},
            "is_admin": True,
        }
        result = analyze_status(raw)
        self.assertEqual(result["usb"]["findings"][0]["severity"], "ok")
        self.assertEqual(result["storage"]["findings"][0]["severity"], "ok")

    def test_unknown_tool_is_rejected(self):
        from .services.device_tools import run_tool

        self.assertFalse(run_tool("format_c")["ok"])


class CsrfFailureTests(TestCase):
    def test_missing_csrf_cookie_redirects_to_login_instead_of_403(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post("/scan/start/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_missing_csrf_cookie_on_api_returns_json(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post("/api/tools/run/", data="{}", content_type="application/json")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(response.json()["reload"])
