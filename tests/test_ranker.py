"""Unit tests for scoring logic."""

from src.config import AppConfig, CenterConfig, ScoringWeights, TripConfig
from src.models import Listing
from src.scoring.ranker import ListingRanker


def _ranker() -> ListingRanker:
    cfg = AppConfig(
        trip=TripConfig(max_total_price_eur=900),
        center=CenterConfig(lat=41.387, lng=2.1701),
        scoring_weights=ScoringWeights(),
    )
    return ListingRanker(cfg)


def test_central_cheap_scores_high():
    ranker = _ranker()
    listing = Listing(
        listing_id="1",
        title="Central flat",
        url="https://airbnb.com/rooms/1",
        total_price_eur=700,
        review_score=4.9,
        lat=41.388,
        lng=2.171,
        free_cancellation=True,
        is_entire_home=True,
    )
    scored = ranker.score_listing(listing)
    assert scored.composite_score >= 75


def test_far_expensive_scores_lower():
    ranker = _ranker()
    listing = Listing(
        listing_id="2",
        title="Far flat",
        url="https://airbnb.com/rooms/2",
        total_price_eur=950,
        review_score=4.0,
        lat=41.35,
        lng=2.25,
    )
    assert not ranker.passes_hard_filters(listing)


def test_haversine_distance():
    from src.geo.distance import haversine_km

    d = haversine_km(41.387, 2.1701, 41.388, 2.171)
    assert d < 0.5
