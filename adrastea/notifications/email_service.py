import email.utils
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, Optional, Tuple
from ..config import config

logger = logging.getLogger("Adrastea.Notifications.Email")


class EmailService:
    """Dispatches status updates and inquiries via SMTP or direct MX delivery."""

    def __init__(self):
        self.host = config.smtp_host
        self.port = config.smtp_port
        self.user = config.smtp_user
        self.password = config.smtp_password
        self.target_email = config.target_email

    def send_status_email(
        self,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
        recipient: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Send an email to the configured target address or specified recipient."""
        dest = recipient or self.target_email
        if not dest:
            return False, "No target recipient email configured."

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        sender_addr = self.user or f"adrastea-agent@{self.host}"
        msg["From"] = f"Adrastea Autonomous Agent <{sender_addr}>"
        msg["To"] = dest
        msg["Message-ID"] = email.utils.make_msgid(domain="adrastea.local")
        msg["Date"] = email.utils.formatdate(localtime=True)

        msg.attach(MIMEText(body_text, "plain"))
        if body_html:
            msg.attach(MIMEText(body_html, "html"))

        # Log dispatch for tracking and verification
        self._log_notification("EMAIL", dest, subject, body_text)

        # Method 1: Authenticated SMTP relay (recommended for Gmail / Inbox delivery)
        if self.user and self.password:
            try:
                logger.info(f"Connecting to SMTP relay {self.host}:{self.port} (user: {self.user})...")
                with smtplib.SMTP(self.host, self.port, timeout=15) as server:
                    if config.smtp_use_tls:
                        server.starttls()
                    server.login(self.user, self.password)
                    server.sendmail(sender_addr, [dest], msg.as_string())
                logger.info(f"Email successfully delivered via authenticated SMTP to {dest}")
                return True, f"Sent via authenticated SMTP to {dest}"
            except Exception as e:
                logger.warning(f"Authenticated SMTP send failed: {e}. Attempting direct delivery...")

        # Method 2: Direct delivery attempt
        domain = dest.split("@")[-1].lower() if "@" in dest else ""
        if domain == "gmail.com":
            mx_server = "aspmx.l.google.com"
            try:
                logger.info(f"Attempting direct MX delivery to {mx_server}:25 for {dest}...")
                with smtplib.SMTP(mx_server, 25, timeout=10) as server:
                    server.ehlo("adrastea.local")
                    server.starttls()
                    server.ehlo("adrastea.local")
                    server.sendmail(sender_addr, [dest], msg.as_string())
                logger.info(f"Email delivered directly via MX to {dest}")
                return True, f"Delivered via direct MX to {dest}"
            except smtplib.SMTPDataError as e:
                err_msg = (
                    f"Gmail requires SMTP authentication (SPF/DKIM). "
                    f"Please add SMTP_USER and SMTP_PASSWORD (a Gmail App Password) to .env to deliver directly to Inbox."
                )
                logger.info(err_msg)
                return False, err_msg
            except Exception as e:
                err_msg = f"Direct MX delivery failed: {e}"
                logger.warning(err_msg)
                return False, err_msg
        else:
            return False, f"Delivery to {dest} requires configured SMTP credentials in .env"

    def _log_notification(self, channel: str, recipient: str, subject: str, content: str) -> None:
        """Write notification to persistent log for audit and verification."""
        log_file = config.logs_dir / "notifications.log"
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"\n[{channel}] TO: {recipient} | SUBJECT: {subject}\n{'-'*60}\n{content}\n{'-'*60}\n")
        except Exception as e:
            logger.error(f"Failed to write notification to log: {e}")
