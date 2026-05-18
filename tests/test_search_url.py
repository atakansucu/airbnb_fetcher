from urllib.parse import parse_qs, urlparse

from src.config import AppConfig, TripConfig
from src.scraper.airbnb import AirbnbScraper


def test_search_url_applies_total_price_cap() -> None:
    cfg = AppConfig(trip=TripConfig(max_total_price_eur=900))
    url = AirbnbScraper(cfg).build_search_url()
    query = parse_qs(urlparse(url).query)

    assert query["price_max"] == ["900"]
    assert query["price_filter_input_type"] == ["2"]
    assert query["price_filter_num_nights"] == ["6"]
    assert query["currency"] == ["EUR"]


def test_canonical_room_url_uses_detail_price_base_url() -> None:
    cfg = AppConfig(trip=TripConfig(max_total_price_eur=900))
    scraper = AirbnbScraper(cfg)

    assert scraper._canonical_room_url("887692388841951937").startswith(
        "https://www.airbnb.com/rooms/887692388841951937"
    )
