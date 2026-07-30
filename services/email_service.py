import json
import logging
from dataclasses import dataclass
from html import escape
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReceiptResult:
    status: str
    reference: str


class ReceiptEmailService:
    """Small Resend HTTP client with a safe development log fallback."""

    def __init__(self, api_key: str, from_email: str):
        self.api_key = api_key
        self.from_email = from_email

    def send_receipt(
        self,
        *,
        to_email: str,
        member_name: str,
        plan_name: str,
        amount_cents: int,
        credits: int,
        expires_on: str,
    ) -> ReceiptResult:
        amount = amount_cents / 100
        subject = f"Fitness Studio receipt - {plan_name}"
        text = (
            f"Hello {member_name},\n\n"
            f"Thank you for your demo purchase of {plan_name}.\n"
            f"Amount: ${amount:.2f}\n"
            f"Credits added: {credits}\n"
            f"Membership valid through: {expires_on}\n\n"
            "Fitness Studio"
        )
        if not self.api_key:
            logger.info("MOCK EMAIL to=%s subject=%s\n%s", to_email, subject, text)
            return ReceiptResult("mocked", "local-log")

        payload = {
            "from": self.from_email,
            "to": [to_email],
            "subject": subject,
            "text": text,
            "html": (
                f"<h2>Fitness Studio receipt</h2>"
                f"<p>Hello {escape(member_name)},</p>"
                f"<p>Thank you for purchasing <strong>{escape(plan_name)}</strong>.</p>"
                f"<ul><li>Amount: ${amount:.2f}</li>"
                f"<li>Credits added: {credits}</li>"
                f"<li>Valid through: {escape(expires_on)}</li></ul>"
                f"<p>Fitness Studio</p>"
            ),
        }
        request = Request(
            "https://api.resend.com/emails",
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=15) as response:
                result = json.loads(response.read().decode("utf-8"))
            return ReceiptResult("sent", str(result.get("id", "resend")))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            logger.exception("Receipt email failed")
            return ReceiptResult("failed", str(exc)[:255])
