"""Core monitoring loop: scrape, score, alert."""

from __future__ import annotations

import signal
import time
import traceback
from typing import Callable

import structlog

from src.config import AppConfig
from src.models import Alert, AlertType, ScoredListing
from src.notifications.dispatcher import NotificationDispatcher
from src.scoring.ranker import ListingRanker
from src.scraper.airbnb import AirbnbScraper
from src.storage.database import ListingStore

logger = structlog.get_logger(__name__)


class MonitorService:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.store = ListingStore(config.database_path)
        self.ranker = ListingRanker(config)
        self.dispatcher = NotificationDispatcher(config, self.store)
        self._running = True

    def stop(self) -> None:
        self._running = False

    def run_once(self) -> int:
        """Single scrape cycle. Returns number of alerts sent."""
        alerts_sent = 0
        scraper = AirbnbScraper(self.config)

        try:
            with scraper:
                listings = scraper.scrape()
        except Exception:
            logger.error("scrape_cycle_failed", traceback=traceback.format_exc())
            return 0

        if not listings:
            logger.warning("no_listings_found")
            return 0

        scored: list[ScoredListing] = []
        invalid_count = 0
        notification_gated_count = 0
        for listing in listings:
            invalid_reason = self.ranker.invalid_reason(listing)
            gate_reason = self.ranker.notification_gate_reason(listing)
            if invalid_reason is None and gate_reason is not None:
                notification_gated_count += 1
            logger.debug(
                "listing_debug",
                listing_id=listing.listing_id,
                title=listing.title,
                url=listing.url,
                total_price_eur=listing.total_price_eur,
                price_per_night_eur=listing.price_per_night_computed,
                rating=listing.review_score,
                room_type=listing.room_type,
                is_entire_home=listing.is_entire_home,
                free_cancellation=listing.free_cancellation,
                cancellation_info="free_cancellation"
                if listing.free_cancellation
                else "not_detected",
                neighborhood=listing.neighborhood,
                location={
                    "lat": listing.lat,
                    "lng": listing.lng,
                    "distance_km": listing.distance_km,
                },
                filtered_out=invalid_reason is not None,
                filter_reason=invalid_reason or "valid_for_scoring_and_storage",
                storage_candidate=invalid_reason is None,
                notification_gate_reason=gate_reason,
                notification_candidate=invalid_reason is None and gate_reason is None,
                max_total_price_eur=self.config.trip.max_total_price_eur,
            )
            if invalid_reason is not None:
                invalid_count += 1
                continue
            scored.append(self.ranker.score_listing(listing))

        rare_ids = {s.listing.listing_id for s in self.ranker.detect_rare_deals(scored)}
        for s in scored:
            if s.listing.listing_id in rare_ids:
                s.is_rare_deal = True

        scored.sort(key=lambda x: x.composite_score, reverse=True)
        logger.info(
            "cycle_scored",
            total=len(listings),
            matched=len(scored),
            invalid=invalid_count,
            notification_gated=notification_gated_count,
            top_score=scored[0].composite_score if scored else None,
        )

        for s in scored:
            alerts = self._evaluate_listing(s)
            for alert in alerts:
                if self.dispatcher.dispatch(alert):
                    alerts_sent += 1

        logger.info(
            "cycle_complete",
            stored=self.store.count_listings(),
            alerts_sent=alerts_sent,
        )
        return alerts_sent

    def send_test_top_notification(self) -> bool:
        """Send the highest-scored listing matching filters (DB, then live scrape)."""
        max_price = self.config.trip.max_total_price_eur
        max_dist = self.config.filters.max_distance_km

        scored = self._best_scored_for_test(from_store=True)
        if scored is None:
            scored = self._best_scored_for_test(from_store=False)

        if scored is None:
            logger.warning("test_notify_no_listings", max_price_eur=max_price)
            return False

        note = "🧪 Test bildirimi — en yüksek skorlu ilan"
        if not self.ranker.passes_hard_filters(scored.listing):
            note = (
                "🧪 Test bildirimi (örnek)\n"
                f"Şu an €{max_price:.0f} altı ilan yok; plaja yakın en ucuz örnek:"
            )
        body = "\n".join(scored.summary_lines())
        alert = Alert(AlertType.SCORE_MATCH, scored, f"{note}\n\n{body}")
        sent = self.dispatcher.dispatch(alert, force=True)
        logger.info(
            "test_notify_sent",
            sent=sent,
            listing_id=scored.listing.listing_id,
            score=scored.composite_score,
        )
        return sent

    def _best_scored_for_test(self, *, from_store: bool) -> ScoredListing | None:
        max_price = self.config.trip.max_total_price_eur
        max_dist = self.config.filters.max_distance_km

        if from_store:
            listing = self.store.get_top_listing_by_score(max_price, max_dist)
            if listing and self.ranker.passes_hard_filters(listing):
                return self.ranker.score_listing(listing)
            return None

        scraper = AirbnbScraper(self.config)
        try:
            with scraper:
                listings = scraper.scrape(max_pages=1)
        except Exception:
            logger.error("test_notify_scrape_failed", traceback=traceback.format_exc())
            return None

        passing: list[ScoredListing] = []
        fallback_near: list[ScoredListing] = []
        for listing in listings:
            scored = self.ranker.score_listing(listing)
            if self.ranker.passes_hard_filters(listing):
                passing.append(scored)
            elif (
                max_dist is not None
                and listing.total_price_eur is not None
                and listing.distance_km is not None
                and listing.distance_km <= max_dist
            ):
                fallback_near.append(scored)

        if passing:
            passing.sort(key=lambda s: s.composite_score, reverse=True)
            return passing[0]
        if fallback_near:
            fallback_near.sort(
                key=lambda s: (
                    s.listing.total_price_eur or 99999,
                    s.listing.distance_km or 99,
                )
            )
            return fallback_near[0]
        return None

    def _evaluate_listing(self, scored: ScoredListing) -> list[Alert]:
        listing = scored.listing
        is_new, price_dropped = self.store.upsert_listing(listing, scored.composite_score)
        alerts: list[Alert] = []
        body = "\n".join(scored.summary_lines())
        ncfg = self.config.notifications
        gate_reason = self.ranker.notification_gate_reason(listing)

        if gate_reason is not None:
            logger.info(
                "notification_skipped_by_gate",
                listing_id=listing.listing_id,
                reason=gate_reason,
                total_price_eur=listing.total_price_eur,
                max_total_price_eur=self.config.trip.max_total_price_eur,
                score=scored.composite_score,
            )
            return alerts

        if scored.is_rare_deal and ncfg.notify_on_rare_deal:
            alerts.append(
                Alert(AlertType.RARE_DEAL, scored, f"🔥 {body}")
            )

        if is_new and ncfg.notify_on_new_listing:
            if scored.composite_score >= ncfg.min_score_to_notify:
                alerts.append(
                    Alert(AlertType.NEW_LISTING, scored, f"🆕 {body}")
                )

        if price_dropped and ncfg.notify_on_price_drop:
            alerts.append(
                Alert(AlertType.PRICE_DROP, scored, f"📉 {body}")
            )

        return alerts

    def run_forever(self, on_cycle: Callable[[], None] | None = None) -> None:
        interval = self.config.polling.interval_minutes * 60
        logger.info(
            "monitor_started",
            interval_minutes=self.config.polling.interval_minutes,
            destination=self.config.trip.destination,
        )

        while self._running:
            started = time.time()
            try:
                self.run_once()
            except Exception:
                logger.error("unexpected_cycle_error", traceback=traceback.format_exc())
            if on_cycle:
                on_cycle()

            elapsed = time.time() - started
            sleep_for = max(30.0, interval - elapsed)
            logger.info("sleeping", seconds=round(sleep_for))
            self._interruptible_sleep(sleep_for)

    def _interruptible_sleep(self, seconds: float) -> None:
        end = time.time() + seconds
        while self._running and time.time() < end:
            time.sleep(min(1.0, end - time.time()))


def install_signal_handlers(service: MonitorService) -> None:
    def _handler(signum: int, frame: object) -> None:
        logger.info("shutdown_signal", signum=signum)
        service.stop()

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)
