"""Configuration loader: YAML defaults + environment overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _env_bool(key: str, default: bool = False) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    return float(raw) if raw else default


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    return int(raw) if raw else default


@dataclass
class TripConfig:
    destination: str = "Barcelona, Spain"
    destinations: list[str] = field(default_factory=lambda: ["Barcelona, Spain"])
    checkin: str = "2026-06-16"
    checkout: str = "2026-06-22"
    guests: int = 3
    max_total_price_eur: float = 900.0


@dataclass
class PollingConfig:
    interval_minutes: int = 20
    max_pages_per_run: int = 5


@dataclass
class ScraperConfig:
    headless: bool = True
    browser_timeout_ms: int = 60000
    scrape_delay_seconds: float = 2.0
    detail_price_verify_margin_eur: float = 25.0
    max_detail_price_verifications: int = 8
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )


@dataclass
class ScoringWeights:
    distance: float = 0.30
    price: float = 0.30
    review: float = 0.15
    cancellation: float = 0.15
    entire_home: float = 0.10


@dataclass
class CenterConfig:
    name: str = "Plaça de Catalunya"
    lat: float = 41.387
    lng: float = 2.1701


@dataclass
class NotificationConfig:
    min_score_to_notify: float = 55.0
    notify_on_price_drop: bool = True
    notify_on_new_listing: bool = True
    notify_on_rare_deal: bool = True
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    discord_webhook_url: str | None = None


@dataclass
class FilterConfig:
    require_entire_home: bool = False
    require_free_cancellation: bool = False
    require_superhost: bool = False
    require_self_check_in: bool = False
    min_review_score: float = 4.5
    max_distance_km: float | None = 4.0


@dataclass
class DebugConfig:
    tracked_listing_ids: list[str] = field(default_factory=list)
    tracked_listing_urls: list[str] = field(default_factory=list)


@dataclass
class AppConfig:
    trip: TripConfig = field(default_factory=TripConfig)
    polling: PollingConfig = field(default_factory=PollingConfig)
    scraper: ScraperConfig = field(default_factory=ScraperConfig)
    scoring_weights: ScoringWeights = field(default_factory=ScoringWeights)
    scoring_min_review: float = 4.5
    rare_deal_percentile: float = 15.0
    center: CenterConfig = field(default_factory=CenterConfig)
    filters: FilterConfig = field(default_factory=FilterConfig)
    debug: DebugConfig = field(default_factory=DebugConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    preferred_neighborhoods: list[str] = field(default_factory=list)
    database_path: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "listings.db")
    log_level: str = "INFO"
    log_file: Path = field(default_factory=lambda: PROJECT_ROOT / "logs" / "monitor.log")


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config(env_file: Path | None = None) -> AppConfig:
    """Load configuration from config.yaml and environment variables."""
    if env_file is None:
        env_file = PROJECT_ROOT / ".env"
    load_dotenv(env_file)

    raw = _load_yaml(PROJECT_ROOT / "config.yaml")
    trip_raw = raw.get("trip", {})
    poll_raw = raw.get("polling", {})
    scraper_raw = raw.get("scraper", {})
    scoring_raw = raw.get("scoring", {})
    weights_raw = scoring_raw.get("weights", {})
    filters_raw = raw.get("filters", {})
    debug_raw = raw.get("debug", {})
    center_raw = raw.get("center", {})
    notif_raw = raw.get("notifications", {})

    destination = os.getenv("TRIP_DESTINATION", trip_raw.get("destination", "Barcelona, Spain"))
    destinations_raw = os.getenv("TRIP_DESTINATIONS")
    if destinations_raw:
        destinations = [d.strip() for d in destinations_raw.split(";") if d.strip()]
    else:
        destinations = trip_raw.get("destinations") or [destination]

    cfg = AppConfig(
        trip=TripConfig(
            destination=destination,
            destinations=destinations,
            checkin=os.getenv("TRIP_CHECKIN", trip_raw.get("checkin", "2026-06-16")),
            checkout=os.getenv("TRIP_CHECKOUT", trip_raw.get("checkout", "2026-06-22")),
            guests=_env_int("TRIP_GUESTS", trip_raw.get("guests", 3)),
            max_total_price_eur=_env_float(
                "MAX_TOTAL_PRICE_EUR", trip_raw.get("max_total_price_eur", 900)
            ),
        ),
        polling=PollingConfig(
            interval_minutes=_env_int("POLL_INTERVAL_MINUTES", poll_raw.get("interval_minutes", 20)),
            max_pages_per_run=_env_int("MAX_PAGES_PER_RUN", poll_raw.get("max_pages_per_run", 5)),
        ),
        scraper=ScraperConfig(
            headless=_env_bool("HEADLESS", scraper_raw.get("headless", True)),
            browser_timeout_ms=_env_int(
                "BROWSER_TIMEOUT_MS", scraper_raw.get("browser_timeout_ms", 60000)
            ),
            scrape_delay_seconds=_env_float(
                "SCRAPE_DELAY_SECONDS", scraper_raw.get("scrape_delay_seconds", 2)
            ),
            detail_price_verify_margin_eur=_env_float(
                "DETAIL_PRICE_VERIFY_MARGIN_EUR",
                scraper_raw.get("detail_price_verify_margin_eur", 25),
            ),
            max_detail_price_verifications=_env_int(
                "MAX_DETAIL_PRICE_VERIFICATIONS",
                scraper_raw.get("max_detail_price_verifications", 8),
            ),
            user_agent=os.getenv(
                "USER_AGENT",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            ),
        ),
        scoring_weights=ScoringWeights(
            distance=weights_raw.get("distance", 0.30),
            price=weights_raw.get("price", 0.30),
            review=weights_raw.get("review", 0.15),
            cancellation=weights_raw.get("cancellation", 0.15),
            entire_home=weights_raw.get("entire_home", 0.10),
        ),
        scoring_min_review=_env_float("MIN_REVIEW_SCORE", scoring_raw.get("min_review_score", 4.5)),
        rare_deal_percentile=_env_float(
            "RARE_DEAL_PERCENTILE", scoring_raw.get("rare_deal_percentile", 15)
        ),
        center=CenterConfig(
            name=center_raw.get("name", "Plaça de Catalunya"),
            lat=_env_float("CENTER_LAT", center_raw.get("lat", 41.387)),
            lng=_env_float("CENTER_LNG", center_raw.get("lng", 2.1701)),
        ),
        filters=FilterConfig(
            require_entire_home=_env_bool(
                "REQUIRE_ENTIRE_HOME", filters_raw.get("require_entire_home", False)
            ),
            require_free_cancellation=_env_bool(
                "REQUIRE_FREE_CANCELLATION", filters_raw.get("require_free_cancellation", False)
            ),
            require_superhost=_env_bool(
                "REQUIRE_SUPERHOST", filters_raw.get("require_superhost", False)
            ),
            require_self_check_in=_env_bool(
                "REQUIRE_SELF_CHECK_IN", filters_raw.get("require_self_check_in", False)
            ),
            min_review_score=_env_float("MIN_REVIEW_SCORE", scoring_raw.get("min_review_score", 4.5)),
            max_distance_km=_env_float(
                "MAX_DISTANCE_KM", filters_raw.get("max_distance_km", 4.0)
            ),
        ),
        debug=DebugConfig(
            tracked_listing_ids=_split_env_list(
                "TRACKED_LISTING_IDS", debug_raw.get("tracked_listing_ids", [])
            ),
            tracked_listing_urls=_split_env_list(
                "TRACKED_LISTING_URLS", debug_raw.get("tracked_listing_urls", [])
            ),
        ),
        notifications=NotificationConfig(
            min_score_to_notify=notif_raw.get("min_score_to_notify", 55),
            notify_on_price_drop=notif_raw.get("notify_on_price_drop", True),
            notify_on_new_listing=notif_raw.get("notify_on_new_listing", True),
            notify_on_rare_deal=notif_raw.get("notify_on_rare_deal", True),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID"),
            discord_webhook_url=os.getenv("DISCORD_WEBHOOK_URL"),
        ),
        preferred_neighborhoods=raw.get("preferred_neighborhoods", []),
        database_path=Path(os.getenv("DATABASE_PATH", str(PROJECT_ROOT / "data" / "listings.db"))),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_file=Path(os.getenv("LOG_FILE", str(PROJECT_ROOT / "logs" / "monitor.log"))),
    )
    return cfg


def _split_env_list(key: str, default: list[str] | str | None) -> list[str]:
    raw = os.getenv(key)
    if raw:
        return [item.strip() for item in raw.split(";") if item.strip()]
    if isinstance(default, str):
        return [default.strip()] if default.strip() else []
    return [str(item).strip() for item in (default or []) if str(item).strip()]
