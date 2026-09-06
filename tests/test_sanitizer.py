import logging
import io
import unittest
from adrastea.sanitizer import sanitize_text, mask_sensitive_value, SensitiveDataFilter


class TestSanitizer(unittest.TestCase):
    def test_sanitize_email(self):
        raw = "Contact the admin at admin.user@example.com for updates."
        clean = sanitize_text(raw)
        self.assertNotIn("admin.user@example.com", clean)
        self.assertIn("[REDACTED_EMAIL]", clean)

    def test_sanitize_phone(self):
        raw1 = "Call 555-867-5309 immediately."
        clean1 = sanitize_text(raw1)
        self.assertNotIn("555-867-5309", clean1)
        self.assertIn("[REDACTED_PHONE]", clean1)

        raw2 = "Phone: (555) 867-5309 or +1-555-867-5309"
        clean2 = sanitize_text(raw2)
        self.assertNotIn("555-867-5309", clean2)

    def test_mask_sensitive_value(self):
        masked_email = mask_sensitive_value("user@test.org")
        self.assertTrue(masked_email.endswith("@test.org"))
        self.assertNotIn("user@", masked_email)

        masked_phone = mask_sensitive_value("555-867-5309")
        self.assertEqual(masked_phone, "***-***-5309")

    def test_logging_filter(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.addFilter(SensitiveDataFilter())

        logger = logging.getLogger("TestSanitizerLogger")
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        logger.propagate = False

        logger.info("Alert dispatched to admin.user@example.com and 555-867-5309.")
        handler.flush()
        output = stream.getvalue()

        self.assertNotIn("admin.user@example.com", output)
        self.assertNotIn("555-867-5309", output)
        self.assertIn("[REDACTED_EMAIL]", output)
        self.assertIn("[REDACTED_PHONE]", output)


if __name__ == "__main__":
    unittest.main()
