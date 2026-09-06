import logging
import subprocess
from typing import Any, Dict, Optional
from ..config import config
from .email_service import EmailService
from .sms_service import SMSService

logger = logging.getLogger("Adrastea.Notifications.ContactRelay")


class ContactRelay:
    """Multi-channel outreach engine that systematically contacts Luke across all available channels."""

    def __init__(self, email_service: Optional[EmailService] = None, sms_service: Optional[SMSService] = None):
        self.email_svc = email_service or EmailService()
        self.sms_svc = sms_service or SMSService(email_service=self.email_svc)
        self.target_email = config.target_email
        self.target_phone = config.target_phone

    def speak_desktop_alert(self, text: str = "Adrastea is active and waiting for directions.") -> bool:
        """Speak out loud through Windows audio synthesizer to alert user at their desk."""
        try:
            # Escape single quotes in text
            safe_text = text.replace("'", "")
            cmd = (
                f"Add-Type -AssemblyName System.Speech; "
                f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                f"$s.Speak('{safe_text}')"
            )
            subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, timeout=10)
            logger.info(f"Desktop voice alert spoken: '{safe_text}'")
            return True
        except Exception as e:
            logger.warning(f"Voice alert failed: {e}")
            return False

    def show_desktop_balloon(self, title: str, text: str) -> bool:
        """Display Windows system tray balloon notification."""
        try:
            safe_title = title.replace("'", "")
            safe_text = text.replace("'", "")
            cmd = (
                f"Add-Type -AssemblyName System.Windows.Forms; "
                f"$n = New-Object System.Windows.Forms.NotifyIcon; "
                f"$n.Icon = [System.Drawing.SystemIcons]::Information; "
                f"$n.Visible = $true; "
                f"$n.ShowBalloonTip(5000, '{safe_title}', '{safe_text}', [System.Windows.Forms.ToolTipIcon]::Info)"
            )
            subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, timeout=5)
            logger.info(f"Desktop balloon alert shown: '{safe_title}'")
            return True
        except Exception as e:
            logger.warning(f"Balloon alert failed: {e}")
            return False

    def send_github_email_relay(self, issue_number: int, body_markdown: str) -> Dict[str, Any]:
        """Posts update to GitHub Issue, triggering email and notification relay."""
        try:
            res = subprocess.run(
                ["gh", "issue", "comment", str(issue_number), "--repo", "holman57/Adrastea", "--body", body_markdown],
                capture_output=True,
                text=True,
                timeout=15
            )
            if res.returncode == 0:
                comment_url = res.stdout.strip()
                logger.info(f"GitHub email relay dispatched via {comment_url}")
                return {"success": True, "details": f"Delivered via GitHub Issue #{issue_number} ({comment_url})"}
            else:
                return {"success": False, "details": res.stderr.strip() or "gh CLI non-zero exit"}
        except Exception as e:
            return {"success": False, "details": str(e)}

    def dispatch_all(self, subject: str, body_text: str, custom_question: str) -> Dict[str, Dict[str, Any]]:
        """Dispatch notifications across every possible communication channel."""
        results: Dict[str, Dict[str, Any]] = {}

        # Channel 1: GitHub Verified Email & Mobile App Notification Relay
        gh_body = (
            f"### [Adrastea Autonomous Update]\n\n"
            f"**Notification for Luke Holman (@holman57)**\n\n"
            f"{body_text}\n\n"
            f"**Direction Request:**\n"
            f"> {custom_question}\n\n"
            f"*Reply directly to this email or comment below to steer Adrastea.*"
        )
        results["github_verified_email"] = self.send_github_email_relay(issue_number=1, body_markdown=gh_body)

        # Channel 2: Desktop Voice Synthesizer
        spoken = self.speak_desktop_alert("Adrastea system notification. Operational and awaiting your direction.")
        results["desktop_voice"] = {"success": spoken, "details": "Spoken through Windows audio synthesis" if spoken else "Failed"}

        # Channel 3: Desktop System Tray Balloon
        balloon = self.show_desktop_balloon("Adrastea Alert", "System online. Waiting for your directions.")
        results["desktop_balloon"] = {"success": balloon, "details": "Popped system tray notification" if balloon else "Failed"}

        # Channel 4: SMTP / Direct Email Attempt
        email_sent, email_details = self.email_svc.send_status_email(
            subject=subject,
            body_text=body_text
        )
        results["direct_email"] = {"success": email_sent, "details": email_details}

        # Channel 5: SMS / Carrier Gateway Attempt
        sms_body = "Adrastea Alert: System waiting on your direction. Check notifications or reply."
        sms_sent, sms_details = self.sms_svc.send_sms(sms_body)
        results["sms_carrier"] = {"success": sms_sent, "details": sms_details}

        return results
