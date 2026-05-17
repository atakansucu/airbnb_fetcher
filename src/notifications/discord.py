"""Discord webhook notifier."""

from __future__ import annotations

import httpx
import structlog

from src.notifications.base import Notifier

logger = structlog.get_logger(__name__)


class DiscordNotifier(Notifier):
    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    def send(self, title: str, body: str) -> bool:
        payload = {
            "embeds": [
                {
                    "title": title,
                    "description": body,
                    "color": 0xFF5A5F,
                }
            ]
        }
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(self.webhook_url, json=payload)
                resp.raise_for_status()
                return True
        except Exception as exc:
            logger.exception("discord_send_failed", error=str(exc))
            return False
