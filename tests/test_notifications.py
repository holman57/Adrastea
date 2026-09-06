import unittest
from adrastea.config import config
from adrastea.notifications.notifier import Notifier
from adrastea.notifications.sms_service import SMSService


class TestNotifications(unittest.TestCase):
    def setUp(self):
        self.notifier = Notifier()
        self.sms = SMSService()

    def test_status_report_formatting(self):
        system_status = {
            "uptime_seconds": 120,
            "local_llm_online": True,
            "active_tasks": ["task_a"],
            "telemetry": {"total_executions": 5, "total_successes": 4, "total_failures": 1}
        }
        subject, plain_text, html_text = self.notifier.format_status_report(
            system_status, custom_question="What should Adrastea do next?"
        )

        self.assertIn("Adrastea", subject)
        self.assertIn("Alpha Uptime: 120", plain_text)
        self.assertIn("Adrastea Orchestrator", html_text)
        self.assertIn("What should Adrastea do next?", plain_text)

    def test_phone_number_cleaning(self):
        cleaned = self.sms._clean_phone_number("555-019-2834")
        self.assertEqual(cleaned, "5550192834")

        cleaned_plus1 = self.sms._clean_phone_number("+1 (555) 019-2834")
        self.assertEqual(cleaned_plus1, "5550192834")


if __name__ == "__main__":
    unittest.main()
