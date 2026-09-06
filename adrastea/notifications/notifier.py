import datetime
import logging
from typing import Any, Dict, Optional, Tuple
from ..config import config
from .email_service import EmailService
from .sms_service import SMSService

logger = logging.getLogger("Adrastea.Notifications")


class Notifier:
    """Unified Notification Coordinator for Adrastea."""

    def __init__(self):
        self.email_svc = EmailService()
        self.sms_svc = SMSService(email_service=self.email_svc)

    def format_status_report(self, system_status: Dict[str, Any], custom_question: Optional[str] = None) -> Tuple[str, str, str]:
        """Construct subject, plain-text body, and HTML body."""
        timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        uptime = system_status.get("uptime_seconds", 0)
        active_tasks = system_status.get("active_tasks", [])
        telemetry = system_status.get("telemetry", {})
        total_exec = telemetry.get("total_executions", 0)
        total_succ = telemetry.get("total_successes", 0)
        total_fail = telemetry.get("total_failures", 0)
        local_llm = "ONLINE" if system_status.get("local_llm_online") else "OFFLINE"

        question = custom_question or (
            "Adrastea is currently running stably in its operational loop.\n"
            "What would you like Adrastea to prioritize next?\n"
            "Options: [1] Run codebase diagnostics, [2] Benchmark local LLM throughput, "
            "[3] Discover new optimization workflows, [4] Remain in standby monitoring mode."
        )

        subject = f"[Adrastea] System Status & Direction Request - {timestamp_str}"

        plain_text = (
            f"=== ADRASTEA AUTONOMOUS SYSTEM REPORT ===\n"
            f"Timestamp: {timestamp_str}\n"
            f"System State: HEALTHY / RUNNING\n"
            f"Alpha Uptime: {uptime} seconds\n"
            f"Local LLM (Ollama): {local_llm}\n"
            f"Active In-Flight Tasks: {len(active_tasks)} ({', '.join(active_tasks) if active_tasks else 'None'})\n"
            f"Task Execution Metrics: {total_succ} Succeeded / {total_fail} Failed (Total: {total_exec})\n"
            f"\n"
            f"--------------------------------------------------\n"
            f"DIRECTIVES & DIRECTION REQUEST:\n"
            f"--------------------------------------------------\n"
            f"{question}\n"
            f"\n"
            f"Reply directly to this email or send directives to steer Adrastea's execution plan.\n"
            f"=========================================="
        )

        html_text = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #222;">
            <div style="max-width: 600px; margin: 0 auto; border: 1px solid #e1e4e8; border-radius: 8px; padding: 20px;">
                <h2 style="color: #1a73e8; border-bottom: 2px solid #e1e4e8; padding-bottom: 10px;">Adrastea System Status & Direction Request</h2>
                <p><strong>Timestamp:</strong> {timestamp_str}</p>
                <p><strong>System State:</strong> <span style="color: #28a745; font-weight: bold;">HEALTHY / RUNNING</span></p>
                
                <table style="width: 100%; border-collapse: collapse; margin: 15px 0;">
                    <tr style="background: #f6f8fa;"><th style="padding: 8px; border: 1px solid #ddd; text-align: left;">Component</th><th style="padding: 8px; border: 1px solid #ddd; text-align: left;">Status / Value</th></tr>
                    <tr><td style="padding: 8px; border: 1px solid #ddd;">Alpha Engine Uptime</td><td style="padding: 8px; border: 1px solid #ddd;">{uptime}s</td></tr>
                    <tr><td style="padding: 8px; border: 1px solid #ddd;">Local LLM (Ollama)</td><td style="padding: 8px; border: 1px solid #ddd;">{local_llm}</td></tr>
                    <tr><td style="padding: 8px; border: 1px solid #ddd;">Active Tasks</td><td style="padding: 8px; border: 1px solid #ddd;">{len(active_tasks)}</td></tr>
                    <tr><td style="padding: 8px; border: 1px solid #ddd;">Task Metrics</td><td style="padding: 8px; border: 1px solid #ddd;">{total_succ} Success / {total_fail} Failed</td></tr>
                </table>

                <div style="background: #eef3fc; border-left: 4px solid #1a73e8; padding: 15px; margin: 20px 0; border-radius: 4px;">
                    <h3 style="margin-top: 0; color: #1a73e8;">Directives & Next Steps</h3>
                    <p style="margin-bottom: 0; white-space: pre-line;">{question}</p>
                </div>

                <p style="font-size: 12px; color: #666; border-top: 1px solid #eee; padding-top: 10px;">
                    Generated autonomously by Adrastea Orchestrator. Target: {config.target_email} & {config.target_phone}.
                </p>
            </div>
        </body>
        </html>
        """

        return subject, plain_text, html_text

    def notify_status(self, system_status: Dict[str, Any], custom_question: Optional[str] = None) -> Dict[str, Any]:
        """Dispatch notifications via Email and SMS."""
        subject, plain_text, html_text = self.format_status_report(system_status, custom_question)

        # 1. Send Email
        email_ok, email_msg = self.email_svc.send_status_email(subject, plain_text, html_text)

        # 2. Send SMS (concise summary)
        sms_body = (
            f"Adrastea Status: RUNNING. Active: {len(system_status.get('active_tasks', []))}. "
            f"What should Adrastea do next? Check user@example.com for details."
        )
        sms_ok, sms_msg = self.sms_svc.send_sms(sms_body)

        logger.info(f"Notification summary: Email={'OK' if email_ok else 'FAIL'} ({email_msg}), SMS={'OK' if sms_ok else 'FAIL'} ({sms_msg})")

        return {
            "email_sent": email_ok,
            "email_status": email_msg,
            "sms_sent": sms_ok,
            "sms_status": sms_msg,
            "timestamp": datetime.datetime.now().isoformat()
        }
