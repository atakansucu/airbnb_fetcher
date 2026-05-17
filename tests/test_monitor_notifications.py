from pathlib import Path

from src.config import AppConfig, CenterConfig, ScoringWeights, TripConfig
from src.models import Listing
from src.monitor import MonitorService


def _service(tmp_path: Path) -> MonitorService:
    cfg = AppConfig(
        trip=TripConfig(max_total_price_eur=900),
        center=CenterConfig(lat=41.387, lng=2.1701),
        scoring_weights=ScoringWeights(),
        database_path=tmp_path / "listings.db",
    )
    return MonitorService(cfg)


def test_expensive_listing_is_stored_but_never_notified(tmp_path: Path) -> None:
    service = _service(tmp_path)
    listing = Listing(
        listing_id="expensive",
        title="Too expensive",
        url="https://airbnb.com/rooms/expensive",
        total_price_eur=1200,
        review_score=5.0,
        lat=41.388,
        lng=2.171,
        free_cancellation=True,
        is_entire_home=True,
    )
    scored = service.ranker.score_listing(listing)

    alerts = service._evaluate_listing(scored)

    assert alerts == []
    assert service.store.count_listings() == 1
