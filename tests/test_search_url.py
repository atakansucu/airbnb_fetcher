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
