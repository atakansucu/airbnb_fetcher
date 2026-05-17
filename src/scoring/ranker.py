"""Composite scoring and rare-deal detection."""

from __future__ import annotations

import hashlib
import statistics
from typing import Sequence

from src.config import AppConfig
from src.geo.distance import distance_to_center
from src.geo.neighborhoods import coords_for_neighborhood
from src.models import Listing, ScoredListing


class ListingRanker:
    """
    Scoring (0–100 composite):
    - distance: closer to Plaça de Catalunya = higher
    - price: lower vs budget = higher
    - review: higher rating = higher
    - cancellation: free cancel = higher
    - entire_home: bonus if entire place
    - neighborhood_bonus: preferred areas
    """

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.weights = config.scoring_weights
        self.preferred = [n.lower() for n in config.preferred_neighborhoods]

    def enrich_listing(self, listing: Listing) -> Listing:
        if listing.lat is None or listing.lng is None:
            approx = coords_for_neighborhood(listing.neighborhood)
            if approx:
                listing.lat, listing.lng = approx
        listing.distance_km = distance_to_center(
            listing.lat,
            listing.lng,
            self.config.center.lat,
            self.config.center.lng,
        )
        return listing

    def passes_hard_filters(self, listing: Listing) -> bool:
        f = self.config.filters
        t = self.config.trip
        listing = self.enrich_listing(listing)

        if listing.total_price_eur is None:
            return False
        if listing.total_price_eur > t.max_total_price_eur:
            return False
        if f.max_distance_km is not None:
            if listing.distance_km is None or listing.distance_km > f.max_distance_km:
                return False
        if listing.review_score is not None and listing.review_score < f.min_review_score:
            return False
        if f.require_entire_home and not listing.is_entire_home:
            return False
        if f.require_free_cancellation and not listing.free_cancellation:
            return False
        if f.require_superhost and not listing.is_superhost:
            return False
        if f.require_self_check_in and not listing.self_check_in:
            return False
        return True

    def score_distance(self, distance_km: float | None) -> float:
        """0–100; 0 km = 100, 5+ km decays toward 0."""
        if distance_km is None:
            return 40.0
        if distance_km <= 0.5:
            return 100.0
        if distance_km <= 1.0:
            return 95.0
        if distance_km <= 2.0:
            return 85.0
        if distance_km <= 3.0:
            return 70.0
        if distance_km <= 5.0:
            return 50.0
        return max(0.0, 50.0 - (distance_km - 5.0) * 10.0)

    def score_price(self, total_price: float | None, max_price: float) -> float:
        if total_price is None:
            return 30.0
        if total_price <= 0:
            return 0.0
        ratio = total_price / max_price
        if ratio <= 0.6:
            return 100.0
        if ratio <= 0.75:
            return 90.0
        if ratio <= 0.85:
            return 80.0
        if ratio <= 1.0:
            return max(40.0, 100.0 - ratio * 40.0)
        return max(0.0, 40.0 - (ratio - 1.0) * 80.0)

    def score_review(self, review_score: float | None) -> float:
        if review_score is None:
            return 50.0
        if review_score >= 4.95:
            return 100.0
        if review_score >= 4.8:
            return 90.0
        if review_score >= 4.5:
            return 75.0
        return max(0.0, (review_score - 3.0) / 2.0 * 100.0)

    def score_cancellation(self, free_cancellation: bool) -> float:
        return 100.0 if free_cancellation else 35.0

    def score_entire_home(self, is_entire: bool) -> float:
        return 100.0 if is_entire else 55.0

    def neighborhood_bonus(self, neighborhood: str | None) -> float:
        if not neighborhood:
            return 0.0
        n = neighborhood.lower()
        for pref in self.preferred:
            if pref in n:
                return 8.0
        return 0.0

    def score_listing(self, listing: Listing) -> ScoredListing:
        listing = self.enrich_listing(listing)
        w = self.weights
        max_price = self.config.trip.max_total_price_eur

        d_score = self.score_distance(listing.distance_km)
        p_score = self.score_price(listing.total_price_eur, max_price)
        r_score = self.score_review(listing.review_score)
        c_score = self.score_cancellation(listing.free_cancellation)
        e_score = self.score_entire_home(listing.is_entire_home)
        n_bonus = self.neighborhood_bonus(listing.neighborhood)

        composite = (
            d_score * w.distance
            + p_score * w.price
            + r_score * w.review
            + c_score * w.cancellation
            + e_score * w.entire_home
            + n_bonus
        )
        composite = min(100.0, composite)

        return ScoredListing(
            listing=listing,
            composite_score=round(composite, 2),
            distance_score=round(d_score, 2),
            price_score=round(p_score, 2),
            review_score=round(r_score, 2),
            cancellation_score=round(c_score, 2),
            entire_home_score=round(e_score, 2),
            neighborhood_bonus=n_bonus,
        )

    def detect_rare_deals(
        self, scored_listings: Sequence[ScoredListing]
    ) -> list[ScoredListing]:
        """
        Flag listings in central zone (<=3km) priced below percentile
        of comparable central listings.
        """
        central = [
            s
            for s in scored_listings
            if s.listing.distance_km is not None
            and s.listing.distance_km <= 3.0
            and s.listing.total_price_eur is not None
        ]
        if len(central) < 5:
            return []

        prices = sorted(s.listing.total_price_eur for s in central)  # type: ignore
        pct = self.config.rare_deal_percentile / 100.0
        idx = max(0, int(len(prices) * pct) - 1)
        threshold = prices[idx]
        median_price = statistics.median(prices)

        rare: list[ScoredListing] = []
        for s in central:
            price = s.listing.total_price_eur
            if price is not None and price <= threshold:
                s.is_rare_deal = True
                savings = median_price - price
                s.rare_deal_reason = (
                    f"Merkezi bölgede alt %{self.config.rare_deal_percentile:.0f} "
                    f"(€{price:.0f} vs medyan €{median_price:.0f}, ~€{savings:.0f} tasarruf)"
                )
                rare.append(s)
        return rare

    @staticmethod
    def message_hash(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()[:16]
