"""Telegram Bot API notifier."""

from __future__ import annotations

import httpx
import structlog

from src.notifications.base import Notifier

logger = structlog.get_logger(__name__)


class TelegramNotifier(Notifier):
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    def send(self, title: str, body: str) -> bool:
        text = f"*{title}*\n\n{body}"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False,
        }
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(self.api_url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                if not data.get("ok"):
                    logger.error("telegram_api_error", response=data)
                    return False
                return True
        except Exception as exc:
            logger.exception("telegram_send_failed", error=str(exc))
            return False
