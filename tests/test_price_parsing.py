"""Unit tests for Airbnb price extraction helpers."""

from __future__ import annotations

import pytest

from src.config import load_config
from src.scraper.airbnb import AirbnbScraper


@pytest.fixture
def scraper() -> AirbnbScraper:
    return AirbnbScraper(load_config())


def test_decode_demand_stay_id(scraper: AirbnbScraper) -> None:
    assert scraper._decode_demand_stay_id("RGVtYW5kU3RheUxpc3Rpbmc6MjE0NjQ2ODY=") == "21464686"
    assert scraper._decode_demand_stay_id("21464686") == "21464686"


def test_parse_structured_display_price_qualified(scraper: AirbnbScraper) -> None:
    sdp = {
        "primaryLine": {
            "__typename": "QualifiedDisplayPriceLine",
            "price": "€\xa01,735",
            "qualifier": "total",
        }
    }
    assert scraper._parse_structured_display_price(sdp) == 1735.0


def test_parse_structured_display_price_discounted(scraper: AirbnbScraper) -> None:
    sdp = {
        "primaryLine": {
            "__typename": "DiscountedDisplayPriceLine",
            "discountedPrice": "€\xa01,075",
            "originalPrice": "€\xa01,244",
            "qualifier": "total",
        }
    }
    assert scraper._parse_structured_display_price(sdp) == 1075.0


def test_parse_price_from_text_picks_discounted_total(scraper: AirbnbScraper) -> None:
    text = "€\xa02,814 \n€\xa02,167\xa0total"
    assert scraper._parse_price_from_text(text) == 2167.0
