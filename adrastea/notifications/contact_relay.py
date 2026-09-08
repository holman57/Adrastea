import logging
import subprocess
from typing import Any, Dict, Optional
from ..config import config
from .email_service import EmailService
from .sms_service import SMSService
from .issue_manager import GitHubTopicManager, AUTHORIZED_OPERATOR

logger = logging.getLogger("Adrastea.Notifications.ContactRelay")


def is_speech_flow_running(host: str = "127.0.0.1", port: Optional[int] = None) -> bool:
    """Checks if speech-flow service is actively listening on its port."""
    import socket
    target_port = port or config.speech_flow_port
    try:
        with socket.create_connection((host, target_port), timeout=0.3):
            return True
    except (OSError, ConnectionRefusedError):
        return False


class ContactRelay:
    """Multi-channel outreach engine that systematically contacts Luke across all available channels."""

    def __init__(
        self,
        email_service: Optional[EmailService] = None,
        sms_service: Optional[SMSService] = None,
        topic_manager: Optional[GitHubTopicManager] = None,
    ):
        self.email_svc = email_service or EmailService()
        self.sms_svc = sms_service or SMSService(email_service=self.email_svc)
        self.topic_mgr = topic_manager or GitHubTopicManager()
        self.target_email = config.target_email
        self.target_phone = config.target_phone

    def speak_desktop_alert(self, text: str = "Adrastea is active and waiting for directions.") -> bool:
        """Speak out loud through Windows audio synthesizer ONLY if speech-flow is actively running."""
        if not config.enable_voice_notifications:
            logger.info("Desktop voice alert skipped: voice notifications disabled in configuration.")
            return False

        if not is_speech_flow_running():
            logger.info("Desktop voice alert skipped: speech-flow is not running.")
            return False

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

    def send_github_email_relay(
        self,
        issue_number: int = 1,
        body_markdown: str = "",
        topic_title: Optional[str] = None,
        is_pulse_status: bool = True
    ) -> Dict[str, Any]:
        """Posts update to GitHub Issue or creates a new dedicated topic issue, respecting wait-for-response."""
        if topic_title and not is_pulse_status:
            return self.topic_mgr.post_or_create_discussion(
                topic_title=topic_title,
                body_markdown=body_markdown,
                is_pulse_status=False
            )

        # For Issue #1 or standard pulse: check if already waiting on Luke
        waiting, reason = self.topic_mgr.is_waiting_for_user_response(issue_number)
        if waiting:
            logger.info(f"GitHub relay suppressed on Issue #{issue_number}: {reason}")
            return {
                "success": False,
                "suppressed": True,
                "issue_number": issue_number,
                "details": reason
            }

        return self.topic_mgr._post_comment(issue_number, body_markdown)

    def dispatch_all(
        self,
        subject: str,
        body_text: str,
        custom_question: str,
        topic_title: Optional[str] = None,
        is_pulse: bool = True,
        force: bool = False,
    ) -> Dict[str, Dict[str, Any]]:
        """Dispatch notifications across communication channels, adhering strictly to wait-for-response."""
        target_issue = 1
        if topic_title and not is_pulse:
            found = self.topic_mgr.find_topic_issue(topic_title)
            if found:
                target_issue = found

        waiting, reason = self.topic_mgr.is_waiting_for_user_response(target_issue)
        if not force and waiting:
            logger.info(f"Outreach suppressed across all channels: {reason}")
            return {
                "github_verified_email": {"success": False, "suppressed": True, "issue_number": target_issue, "details": reason},
                "desktop_voice": {"success": False, "suppressed": True, "details": "Suppressed: awaiting user response"},
                "desktop_balloon": {"success": False, "suppressed": True, "details": "Suppressed: awaiting user response"},
                "direct_email": {"success": False, "suppressed": True, "details": "Suppressed: awaiting user response"},
                "sms_carrier": {"success": False, "suppressed": True, "details": "Suppressed: awaiting user response"},
            }

        results: Dict[str, Dict[str, Any]] = {}

        # Channel 1: GitHub Verified Email & Mobile App Notification Relay
        gh_body = (
            f"### [Adrastea Autonomous Update]\n\n"
            f"**Notification for Luke Holman (@{AUTHORIZED_OPERATOR})**\n\n"
            f"{body_text}\n\n"
            f"**Direction Request:**\n"
            f"> {custom_question}\n\n"
            f"*Reply directly to this email or comment below to steer Adrastea.*"
        )
        results["github_verified_email"] = self.send_github_email_relay(
            issue_number=1,
            body_markdown=gh_body,
            topic_title=topic_title,
            is_pulse_status=is_pulse
        )

        # Channel 2: Desktop Voice Synthesizer (Only if speech-flow is actively running and voice enabled)
        if config.enable_voice_notifications and is_speech_flow_running():
            spoken = self.speak_desktop_alert("Adrastea system notification. Operational and awaiting your direction.")
            results["desktop_voice"] = {"success": spoken, "details": "Spoken through Windows audio synthesis" if spoken else "Failed"}
        else:
            results["desktop_voice"] = {"success": False, "details": "Desktop voice disabled (speech-flow not running)"}

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
