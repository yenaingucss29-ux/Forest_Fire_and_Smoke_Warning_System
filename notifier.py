"""Email alerts through the Resend API: https://resend.com/docs/api-reference/emails/send-email"""

import base64
from dataclasses import dataclass
from datetime import datetime
from html import escape

import requests

from detector import DetectionResult

RESEND_URL = "https://api.resend.com/emails"


@dataclass
class EmailStatus:
    sent: bool
    detail: str


def mask_email(address: str) -> str:
    """n***@gmail.com — the page is public, so don't show the author's full address to visitors."""
    name, _, domain = address.partition("@")
    return f"{name[:1]}***@{domain}" if domain else "***"


class EmailNotifier:
    def __init__(self, api_key: str, to: str, sender: str):
        self.api_key = api_key
        self.to = to
        self.sender = sender

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.to)

    def send_smoke_alert(self, result: DetectionResult, source: str, image_jpeg: bytes) -> EmailStatus:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rows = "".join(
            f"<li>{d.label}: {d.confidence:.0%} confidence</li>" for d in result.detections
        )
        html = f"""
            <h2 style="color:#c62828">🔥 Smoke detected</h2>
            <p>The forest smoke warning system found <b>{len(result.smoke)} smoke region(s)</b>
               with up to <b>{result.max_smoke_confidence:.0%}</b> confidence.</p>
            <ul>{rows}</ul>
            <p>Source: {escape(source)}<br>Time: {now}</p>
            <p>The annotated image is attached.</p>
        """
        return self._send(
            subject=f"🔥 SMOKE ALERT – {result.max_smoke_confidence:.0%} confidence ({now})",
            html=html,
            attachment=("smoke-detection.jpg", image_jpeg),
        )

    def send_all_clear(self, source: str) -> EmailStatus:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        html = f"""
            <h2 style="color:#2e7d32">✅ No smoke detected</h2>
            <p>Source: {escape(source)}<br>Time: {now}</p>
            <p>You get this email because "Alert when no smoke is found" is turned on.</p>
        """
        return self._send(subject=f"✅ All clear – no smoke ({now})", html=html)

    def send_test(self) -> EmailStatus:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        html = f"""
            <h2>✅ Test email</h2>
            <p>Email alerts from the forest smoke warning system are working.</p>
            <p>Sent from the admin dashboard at {now}.</p>
        """
        return self._send(subject=f"Test – forest smoke warning ({now})", html=html)

    def _send(self, subject: str, html: str, attachment: tuple[str, bytes] | None = None) -> EmailStatus:
        if not self.configured:
            return EmailStatus(False, "Email is not set up. Add RESEND_API_KEY and ALERT_EMAIL_TO to .env.")

        payload = {"from": self.sender, "to": [self.to], "subject": subject, "html": html}
        if attachment:
            filename, content = attachment
            payload["attachments"] = [{"filename": filename, "content": base64.b64encode(content).decode()}]

        try:
            response = requests.post(
                RESEND_URL,
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=15,
            )
        except requests.RequestException as e:
            return EmailStatus(False, f"Could not reach Resend: {e}")

        if response.ok:
            return EmailStatus(True, f"Email sent to {mask_email(self.to)}")
        try:
            message = response.json().get("message", response.text)
        except ValueError:
            message = response.text
        return EmailStatus(False, f"Resend error {response.status_code}: {message}")
