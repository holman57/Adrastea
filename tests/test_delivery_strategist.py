import unittest
from adrastea.beta.delivery_strategist import DeliveryStrategist


class TestDeliveryStrategist(unittest.TestCase):
    def setUp(self):
        self.strategist = DeliveryStrategist()

    def test_backoff_progression(self):
        self.assertEqual(self.strategist.get_next_wait_interval(), 15 * 60)
        self.strategist.mark_contact_attempted()
        self.assertEqual(self.strategist.get_next_wait_interval(), 30 * 60)
        self.strategist.mark_contact_attempted()
        self.assertEqual(self.strategist.get_next_wait_interval(), 60 * 60)

        # Reset on user directive
        self.strategist.reset_backoff_on_response()
        self.assertEqual(self.strategist.get_next_wait_interval(), 15 * 60)

    def test_adaptation_on_failures(self):
        outreach = {
            "github_verified_email": {"success": True, "details": "Delivered"},
            "direct_email": {"success": False, "details": "Blocked by SPF"},
        }
        analysis = self.strategist.analyze_and_adapt(outreach)
        self.assertIn("best_working_channel", analysis)


if __name__ == "__main__":
    unittest.main()
