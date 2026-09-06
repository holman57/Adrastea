import logging
import re
from typing import Dict, List, Optional, Tuple
from ..config import config
from .email_service import EmailService

logger = logging.getLogger("Adrastea.Notifications.SMS")

CARRIER_GATEWAYS: Dict[str, str] = {
    "att": "{number}@txt.att.net",
    "verizon": "{number}@vtext.com",
    "tmobile": "{number}@tmomail.net",
    "sprint": "{number}@messaging.sprintphones.com",
}


class SMSService:
    """Dispatches SMS text messages via Email-to-SMS gateways or Twilio."""

    def __init__(self, email_service: Optional[EmailService] = None):
        self.email_service = email_service or EmailService()
        self.target_phone = config.target_phone
        self.carrier = config.sms_carrier_gateway.lower()
        self.twilio_sid = config.twilio_account_sid
        self.twilio_token = config.twilio_auth_token
        self.twilio_from = config.twilio_from_number

    def _clean_phone_number(self, phone: str) -> str:
        """Strip non-digit characters and return 10-digit number."""
        digits = re.sub(r"\D", "", phone)
        if len(digits) == 11 and digits.startswith("1"):
            digits = digits[1:]
        return digits

    def send_sms(self, message_text: str) -> Tuple[bool, str]:
        """Send an SMS message to the target phone."""
        if not self.target_phone:
            return False, "No target phone number configured."

        clean_number = self._clean_phone_number(self.target_phone)
        if len(clean_number) != 10:
            return False, f"Invalid phone number format: {self.target_phone}"

        # Truncate to standard SMS length if needed (or chunk)
        sms_text = message_text[:320]

        # Method 1: Twilio REST API if configured
        if self.twilio_sid and self.twilio_token and self.twilio_from:
            try:
                import urllib.parse
                import urllib.request
                import base64

                url = f"https://api.twilio.com/2010-04-01/Accounts/{self.twilio_sid}/Messages.json"
                auth = base64.b64encode(f"{self.twilio_sid}:{self.twilio_token}".encode("utf-8")).decode("ascii")
                data = urllib.parse.urlencode({
                    "To": f"+1{clean_number}",
                    "From": self.twilio_from,
                    "Body": sms_text,
                }).encode("utf-8")

                req = urllib.request.Request(url, data=data, headers={"Authorization": f"Basic {auth}"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status in (200, 201):
                        logger.info(f"SMS delivered via Twilio to {self.target_phone}")
                        return True, "Delivered via Twilio"
            except Exception as e:
                logger.warning(f"Twilio SMS delivery failed: {e}. Falling back to Email-to-SMS gateway...")

        # Method 2: Carrier Email-to-SMS Gateway
        gateways_to_try = [self.carrier] if self.carrier in CARRIER_GATEWAYS else ["att", "verizon", "tmobile"]
        success_any = False
        notes = []

        for carrier_key in gateways_to_try:
            gateway_tmpl = CARRIER_GATEWAYS.get(carrier_key)
            if not gateway_tmpl:
                continue
            gateway_email = gateway_tmpl.format(number=clean_number)
            logger.info(f"Dispatching SMS via gateway: {gateway_email}")
            
            sent, status = self.email_service.send_status_email(
                subject="Adrastea Status",
                body_text=sms_text,
                recipient=gateway_email
            )
            if sent:
                success_any = True
                notes.append(f"{carrier_key}: {status}")

        if success_any:
            return True, f"Sent via gateways: {', '.join(notes)}"
        else:
            return False, f"Failed SMS delivery: {', '.join(notes)}"
