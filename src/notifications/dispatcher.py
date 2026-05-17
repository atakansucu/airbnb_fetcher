"""Routes alerts to configured notification channels."""

from __future__ import annotations

import structlog

from src.config import AppConfig
from src.models import Alert, AlertType
from src.notifications.base import Notifier
from src.notifications.discord import DiscordNotifier
from src.notifications.telegram import TelegramNotifier
from src.scoring.ranker import ListingRanker
from src.storage.database import ListingStore

logger = structlog.get_logger(__name__)

ALERT_TITLES = {
    AlertType.NEW_LISTING: "Yeni ilan",
    AlertType.PRICE_DROP: "Fiyat düştü",
    AlertType.RARE_DEAL: "Nadir fırsat",
    AlertType.SCORE_MATCH: "Uygun ilan",
}


class NotificationDispatcher:
    def __init__(self, config: AppConfig, store: ListingStore) -> None:
        self.config = config
        self.store = store
        self.notifiers: list[Notifier] = self._build_notifiers()

    def _build_notifiers(self) -> list[Notifier]:
        channels: list[Notifier] = []
        n = self.config.notifications
        if n.telegram_bot_token and n.telegram_chat_id:
            channels.append(TelegramNotifier(n.telegram_bot_token, n.telegram_chat_id))
        if n.discord_webhook_url:
            channels.append(DiscordNotifier(n.discord_webhook_url))
        return channels

    def dispatch(self, alert: Alert, *, force: bool = False) -> bool:
        if not self.notifiers:
            logger.warning("no_notifiers_configured")
            return False

        body = alert.message
        msg_hash = ListingRanker.message_hash(f"{alert.alert_type}:{body}")

        if (
            not force
            and self.store.was_notified(
                alert.scored.listing.listing_id, alert.alert_type.value, msg_hash
            )
        ):
            logger.debug("duplicate_skipped", listing_id=alert.scored.listing.listing_id)
            return False

        title = ALERT_TITLES.get(alert.alert_type, "Airbnb uyarısı")
        success = False
        for notifier in self.notifiers:
            if notifier.send(title, body):
                success = True

        if success:
            self.store.mark_notified(
                alert.scored.listing.listing_id,
                alert.alert_type.value,
                msg_hash,
            )
        return success
