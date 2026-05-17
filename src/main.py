"""CLI entry point for Airbnb Barcelona monitor."""

from __future__ import annotations

import argparse
import sys

import structlog

from src.config import load_config
from src.logging_setup import setup_logging
from src.monitor import MonitorService, install_signal_handlers

logger = structlog.get_logger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Airbnb listing monitor for Barcelona trip"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single scrape cycle and exit",
    )
    parser.add_argument(
        "--test-notify",
        action="store_true",
        help="Send top-scored stored listing to Telegram (test)",
    )
    parser.add_argument(
        "--env-file",
        type=str,
        default=None,
        help="Path to .env file (default: project root .env)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.env_file:
        from pathlib import Path
        from dotenv import load_dotenv
        load_dotenv(Path(args.env_file), override=True)
    config = load_config()

    setup_logging(config.log_level, config.log_file)

    if not config.notifications.telegram_bot_token and not config.notifications.discord_webhook_url:
        logger.warning(
            "no_notification_channel",
            hint="Set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID or DISCORD_WEBHOOK_URL in .env",
        )

    service = MonitorService(config)
    install_signal_handlers(service)

    logger.info(
        "config_loaded",
        trip=f"{config.trip.checkin} → {config.trip.checkout}",
        guests=config.trip.guests,
        max_price=config.trip.max_total_price_eur,
        poll_min=config.polling.interval_minutes,
    )

    if args.test_notify:
        sent = service.send_test_top_notification()
        if not sent:
            logger.error("test_notify_failed")
            return 1
        return 0

    if args.once:
        sent = service.run_once()
        logger.info("single_run_done", alerts_sent=sent)
        return 0

    service.run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
