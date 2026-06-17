"""Methods to handle developer notifications via Telegram."""

from typing import Optional

import requests

from core.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID

ALERT_APP_NAME = "Market Eye"
TELEGRAM_MESSAGE_LIMIT = 4096
TELEGRAM_API_TIMEOUT_SECONDS = 30


def _format_message(body: Optional[str], subject: Optional[str]) -> str:
    subject_text = subject or "Developer Notification"
    body_text = body or "Test Notification"
    return f"[{ALERT_APP_NAME}] {subject_text}\n\n{body_text}"


def notify_developer(
    body: Optional[str] = "Test Notification",
    subject: Optional[str] = "Developer Notification",
):
    """Send a developer alert to the configured Telegram channel."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
        raise RuntimeError("Telegram notifications are not configured")

    message = _format_message(body, subject)
    if len(message) > TELEGRAM_MESSAGE_LIMIT:
        message = message[:TELEGRAM_MESSAGE_LIMIT]

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    response = requests.post(
        url,
        json={"chat_id": TELEGRAM_CHANNEL_ID, "text": message},
        timeout=TELEGRAM_API_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
