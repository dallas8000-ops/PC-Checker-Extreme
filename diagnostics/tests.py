from django.test import SimpleTestCase

from .services.health_checks import run_health_checks
from .services.scan_insights import build_command_playbook


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
