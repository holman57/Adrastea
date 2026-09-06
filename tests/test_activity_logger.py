import tempfile
import time
import unittest
from pathlib import Path
from adrastea.activity_logger import ActivityLogger


class TestActivityLogger(unittest.TestCase):
    def test_log_cycle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "TEST_ACTIVITY.md"
            logger = ActivityLogger(log_path=log_file)
            self.assertTrue(log_file.exists())

            alpha_status = {
                "uptime_seconds": 60,
                "active_tasks": ["task_1"],
                "telemetry": {"total_executions": 2, "total_successes": 2, "total_failures": 0}
            }
            outreach = {
                "github_verified_email": {"success": True, "details": "Delivered"}
            }

            logger.log_cycle(
                alpha_status=alpha_status,
                beta_action="Test Action",
                outreach_results=outreach,
                pending_directive_prompt="What next?"
            )

            content = log_file.read_text(encoding="utf-8")
            self.assertIn("Test Action", content)
            self.assertIn("- **github_verified_email**: OK", content)
            self.assertIn("What next?", content)

    def test_cooldown_suppression(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "TEST_ACTIVITY.md"
            logger = ActivityLogger(log_path=log_file)
            logger.last_push_time = time.time()  # just pushed

            # Without bypass, cooldown should suppress push
            pushed = logger.commit_and_push_significant_event(
                "minor event",
                min_cooldown_seconds=1800.0,
                bypass_cooldown=False
            )
            self.assertFalse(pushed)


if __name__ == "__main__":
    unittest.main()
