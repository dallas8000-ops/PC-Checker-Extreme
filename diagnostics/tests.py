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


class AccuracyRegressionTests(SimpleTestCase):
    def _check_ids(self, extended):
        checks = run_health_checks(
            {"live_metrics": {"memory": {"percent_used": 20}, "disks": []}},
            {"outdated_winget": {"count": 0}, "windows_updates": {"count": 0}},
            {"extended": extended},
        )["checks"]
        return {c["id"] for c in checks}

    def test_unreadable_tpm_is_not_reported_as_not_ready(self):
        ids = self._check_ids({"secure_boot_tpm": {"available": True, "tpm": {"present": True, "ready": None}}})
        self.assertNotIn("tpm_not_ready", ids)
        ids = self._check_ids({"secure_boot_tpm": {"available": True, "tpm": {"present": True, "ready": False}}})
        self.assertIn("tpm_not_ready", ids)

    def test_configured_memory_integrity_says_restart_not_enable(self):
        ids = self._check_ids({"virtualization": {
            "available": True, "memory_integrity": False, "memory_integrity_configured": True}})
        self.assertIn("memory_integrity_pending", ids)
        self.assertNotIn("memory_integrity_off", ids)

    def test_virtualization_off_in_bios_is_named_as_the_cause(self):
        ids = self._check_ids({"virtualization": {
            "available": True, "memory_integrity": False, "memory_integrity_configured": True,
            "virtualization_firmware": False, "hypervisor_present": False}})
        self.assertIn("virtualization_disabled_bios", ids)
        self.assertNotIn("memory_integrity_pending", ids)

    def test_startup_only_driver_warnings_on_working_devices_are_info(self):
        from .services.device_tools import analyze_status

        raw = {
            "usb": {
                "problem_devices": [], "controllers": [], "selective_suspend_ac": 0,
                "events": {"total": 50, "groups": [
                    {"provider": "Microsoft-Windows-Kernel-PnP", "id": 219, "count": 33,
                     "startup_count": 33, "device_id": "PCI\\VEN_8086&DEV_1137\\X",
                     "device_status": "OK", "device_present": True},
                    {"provider": "Microsoft-Windows-Kernel-PnP", "id": 219, "count": 17,
                     "startup_count": 17, "device_id": "HID\\VID_0951&PID_16A4\\Y",
                     "device_status": "OK", "device_present": True},
                ]},
            },
            "storage": {"disks": [], "volumes": [], "events": {"total": 0, "groups": []}},
            "is_admin": True,
        }
        result = analyze_status(raw)
        self.assertEqual(result["usb"]["event_total"], 50)
        severities = {f["severity"] for f in result["usb"]["findings"]}
        self.assertNotIn("warning", severities)
        self.assertTrue(any("50 startup-only" in f["title"] for f in result["usb"]["findings"]))

    def test_repeated_warning_on_broken_device_is_flagged(self):
        from .services.device_tools import analyze_status

        raw = {
            "usb": {
                "problem_devices": [], "controllers": [], "selective_suspend_ac": 0,
                "events": {"total": 4, "groups": [
                    {"provider": "Microsoft-Windows-Kernel-PnP", "id": 219, "count": 4,
                     "startup_count": 0, "device_id": "USB\\VID_1\\Z",
                     "device_status": "Error", "device_present": True},
                ]},
            },
            "storage": {"disks": [], "volumes": [], "events": []},
            "is_admin": True,
        }
        findings = analyze_status(raw)["usb"]["findings"]
        self.assertTrue(any(f["severity"] == "warning" and f["title"].startswith("4 USB") for f in findings))


class AiErrorMessageTests(SimpleTestCase):
    def test_rejected_key_is_reported_instead_of_add_key(self):
        from .services import ai_analyzer

        class FakeAuthError(Exception):
            status_code = 401

        with patch.object(ai_analyzer.settings, "OPENAI_API_KEY", "sk-test"), \
             patch("openai.OpenAI") as client:
            client.return_value.chat.completions.create.side_effect = FakeAuthError("Incorrect API key provided")
            result = ai_analyzer.analyze_system({"health": {"health_score": 90, "checks": []}})

        self.assertIn("rejected the API key", result["summary"])
        self.assertNotIn("Add OPENAI_API_KEY", result["summary"])
        self.assertNotIn("Add OPENAI_API_KEY", result["plain_english_summary"])


class ScoreAccuracyTests(SimpleTestCase):
    def test_official_score_is_measured_health_not_ai_estimate(self):
        from .services import scanner
        import inspect
        src = inspect.getsource(scanner.run_full_scan)
        self.assertIn('overall = health.get("health_score")', src)

    def test_failed_disk_benchmark_is_not_a_bottleneck(self):
        from .services.scan_insights import analyze_bottleneck

        result = analyze_bottleneck({
            "hardware": {"live_metrics": {"cpu_percent": 5, "memory": {"percent_used": 25}}},
            "benchmark": {"cpu_score": 100, "disk_score": None},
        })
        self.assertNotIn("disk", result["scores"])
        self.assertEqual(result["primary_bottleneck"], "none")
        self.assertLessEqual(result["scores"]["cpu"], 100)

    def test_slow_measured_disk_is_still_flagged(self):
        from .services.scan_insights import analyze_bottleneck

        result = analyze_bottleneck({
            "hardware": {"live_metrics": {"cpu_percent": 5, "memory": {"percent_used": 25}}},
            "benchmark": {"cpu_score": 100, "disk_score": 30},
        })
        self.assertEqual(result["primary_bottleneck"], "disk")

    def test_disk_benchmark_measures_on_windows(self):
        from .services.extended_diagnostics import collect_benchmark

        result = collect_benchmark()
        self.assertEqual(result["disk_note"], "")
        self.assertIsNotNone(result["disk_score"])

    def test_similar_named_controllers_are_not_duplicates(self):
        from .services.extended_diagnostics import analyze_duplicate_drivers

        drivers = [
            {"DeviceName": "Intel(R) Serial IO I2C Host Controller - 43E8", "DeviceID": "PCI\\VEN_8086&DEV_43E8\\3&11583659&0&A8"},
            {"DeviceName": "Intel(R) Serial IO I2C Host Controller - 43E9", "DeviceID": "PCI\\VEN_8086&DEV_43E9\\3&11583659&0&A9"},
        ]
        self.assertEqual(analyze_duplicate_drivers(drivers), [])
        same = drivers[:1] * 2
        self.assertEqual(len(analyze_duplicate_drivers(same)), 1)

    def test_ai_score_does_not_override_measured_score(self):
        from .services import ai_analyzer

        fake = type("R", (), {})()
        fake.choices = [type("C", (), {"message": type("M", (), {"content": '{"summary": "ok", "overall_score": 85, "health_grade": "B"}'})()})()]
        with patch.object(ai_analyzer.settings, "OPENAI_API_KEY", "sk-test"), patch("openai.OpenAI") as client:
            client.return_value.chat.completions.create.return_value = fake
            result = ai_analyzer.analyze_system({"health": {"health_score": 100, "checks": []}})
        self.assertEqual(result["overall_score"], 100)
        self.assertEqual(result["health_grade"], "A")
        self.assertEqual(result["ai_overall_score"], 85)


class MemoryBottleneckTests(SimpleTestCase):
    def _primary(self, mem_pct):
        from .services.scan_insights import analyze_bottleneck
        return analyze_bottleneck({
            "hardware": {"live_metrics": {"cpu_percent": 5, "memory": {"percent_used": mem_pct}}},
            "benchmark": {"cpu_score": 100, "disk_score": 99},
        })["primary_bottleneck"]

    def test_normal_ram_use_is_not_a_bottleneck(self):
        self.assertEqual(self._primary(34), "none")

    def test_high_ram_use_is_a_bottleneck(self):
        self.assertEqual(self._primary(85), "memory")
