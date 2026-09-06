import logging
import re
from typing import Any, Optional

EMAIL_REGEX = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    re.IGNORECASE
)

PHONE_REGEX = re.compile(
    r"(?:\+?1[-.\s]?)?(?:\([0-9]{3}\)|[0-9]{3})[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b"
)


def sanitize_text(text: str, extra_sensitive: Optional[list] = None) -> str:
    """Sanitize sensitive information (emails, phone numbers, custom secrets) from strings."""
    if not isinstance(text, str):
        return text

    sanitized = EMAIL_REGEX.sub("[REDACTED_EMAIL]", text)
    sanitized = PHONE_REGEX.sub("[REDACTED_PHONE]", sanitized)

    if extra_sensitive:
        for secret in extra_sensitive:
            if secret and isinstance(secret, str) and len(secret) > 2:
                sanitized = re.sub(re.escape(secret), "[REDACTED]", sanitized, flags=re.IGNORECASE)

    return sanitized


def mask_sensitive_value(value: Optional[str]) -> str:
    """Mask a sensitive value for safe display in status logs."""
    if not value:
        return "<not set>"
    if "@" in value:
        parts = value.split("@", 1)
        user, domain = parts[0], parts[1]
        if len(user) <= 2:
            masked_user = user[0] + "*"
        else:
            masked_user = user[0] + "*" * (len(user) - 2) + user[-1]
        return f"{masked_user}@{domain}"
    if len(value) >= 7:
        return f"***-***-{value[-4:]}"
    return "****"


class SensitiveDataFilter(logging.Filter):
    """Logging filter that automatically redacts sensitive data (emails, phone numbers) from log records."""

    def __init__(self, extra_sensitive: Optional[list] = None):
        super().__init__()
        self.extra_sensitive = extra_sensitive or []

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = sanitize_text(record.msg, self.extra_sensitive)

        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: sanitize_text(v, self.extra_sensitive) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    sanitize_text(a, self.extra_sensitive) if isinstance(a, str) else a
                    for a in record.args
                )
            elif isinstance(record.args, list):
                record.args = [
                    sanitize_text(a, self.extra_sensitive) if isinstance(a, str) else a
                    for a in record.args
                ]

        return True
