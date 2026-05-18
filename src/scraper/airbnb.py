"""Airbnb search scraper using Playwright with JSON + DOM fallbacks."""

from __future__ import annotations

import base64
import json
import random
import re
import time
from datetime import datetime
from typing import Any
from urllib.parse import quote_plus, urlencode

import structlog
from playwright.sync_api import Browser, Page, Playwright, sync_playwright

from src.config import AppConfig
from src.models import Listing

logger = structlog.get_logger(__name__)

LISTING_ID_RE = re.compile(r"/rooms/(\d+)")


class AirbnbScraper:
  def __init__(self, config: AppConfig) -> None:
    self.config = config
    self._playwright: Playwright | None = None
    self._browser: Browser | None = None

  def _nights(self) -> int:
    checkin = datetime.strptime(self.config.trip.checkin, "%Y-%m-%d")
    checkout = datetime.strptime(self.config.trip.checkout, "%Y-%m-%d")
    return max(1, (checkout - checkin).days)

  def build_search_url(self, page_offset: int = 0, destination: str | None = None) -> str:
    trip = self.config.trip
    search_destination = destination or trip.destination
    dest_slug = quote_plus(search_destination.replace(", ", "--").replace(" ", "-"))
    params: dict[str, str | int] = {
      "checkin": trip.checkin,
      "checkout": trip.checkout,
      "adults": trip.guests,
      "currency": "EUR",
      "search_type": "filter_change",
    }
    if self.config.filters.require_free_cancellation:
      params["flexible_cancellation"] = "true"
    if page_offset > 0:
      params["items_offset"] = page_offset * 20

    base = f"https://www.airbnb.com/s/{dest_slug}/homes"
    return f"{base}?{urlencode(params)}"

  def _launch_browser(self) -> Browser:
    if self._browser:
      return self._browser
    self._playwright = sync_playwright().start()
    self._browser = self._playwright.chromium.launch(
      headless=self.config.scraper.headless,
      args=[
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
      ],
    )
    return self._browser

  def close(self) -> None:
    if self._browser:
      self._browser.close()
      self._browser = None
    if self._playwright:
      self._playwright.stop()
      self._playwright = None

  def __enter__(self) -> AirbnbScraper:
    return self

  def __exit__(self, *args: Any) -> None:
    self.close()

  def scrape(self, max_pages: int | None = None) -> list[Listing]:
    max_pages = max_pages or self.config.polling.max_pages_per_run
    all_listings: dict[str, Listing] = {}
    total_scraped = 0
    started = time.monotonic()

    try:
      browser = self._launch_browser()
      context = browser.new_context(
        user_agent=self.config.scraper.user_agent,
        locale="en-US",
        viewport={"width": 1440, "height": 900},
      )
      destinations = self._search_destinations()
      for destination_idx, destination in enumerate(destinations, start=1):
        if destination_idx > 1:
          delay = self._page_delay_seconds()
          logger.debug(
            "scraping_destination_delay",
            destination=destination,
            seconds=round(delay, 2),
          )
          time.sleep(delay)

        page = context.new_page()
        page.set_default_timeout(self.config.scraper.browser_timeout_ms)
        destination_scraped_start = total_scraped
        destination_unique_start = len(all_listings)

        for page_idx in range(max_pages):
          requested_url = self.build_search_url(
            page_offset=page_idx,
            destination=destination,
          )
          navigation_method = "initial_url"
          if page_idx == 0:
            url = requested_url
            scrape_page = lambda: self._scrape_page(page, url)
          elif self._go_to_next_results_page(page):
            url = page.url
            navigation_method = "pagination_next"
            scrape_page = lambda: self._extract_current_page(page, url)
          else:
            url = requested_url
            navigation_method = "offset_url_fallback"
            scrape_page = lambda: self._scrape_page(page, url)

          page_started = time.monotonic()
          logger.info(
            "scraping_page",
            destination=destination,
            destination_index=destination_idx,
            destinations_total=len(destinations),
            url=url,
            page=page_idx + 1,
            pages_total=max_pages,
            navigation_method=navigation_method,
            total_scraped=total_scraped,
            total_unique=len(all_listings),
          )
          listings = scrape_page()
          total_scraped += len(listings)
          for lst in listings:
            all_listings[lst.listing_id] = lst
          elapsed = time.monotonic() - started
          page_elapsed = time.monotonic() - page_started
          pages_done = ((destination_idx - 1) * max_pages) + page_idx + 1
          total_pages = len(destinations) * max_pages
          avg_page_seconds = elapsed / pages_done
          estimated_runtime_seconds = avg_page_seconds * total_pages
          duplicates_removed = total_scraped - len(all_listings)
          logger.info(
            "scraping_page_complete",
            destination=destination,
            destination_index=destination_idx,
            destinations_total=len(destinations),
            page=page_idx + 1,
            pages_total=max_pages,
            navigation_method=navigation_method,
            page_listings=len(listings),
            total_scraped=total_scraped,
            total_unique=len(all_listings),
            duplicates_removed=duplicates_removed,
            page_seconds=round(page_elapsed, 2),
            elapsed_seconds=round(elapsed, 2),
            estimated_runtime_seconds=round(estimated_runtime_seconds, 2),
          )
          if page_idx < max_pages - 1:
            delay = self._page_delay_seconds()
            logger.debug("scraping_page_delay", seconds=round(delay, 2))
            time.sleep(delay)

        logger.info(
          "scraping_destination_complete",
          destination=destination,
          destination_index=destination_idx,
          destinations_total=len(destinations),
          pages=max_pages,
          destination_scraped=total_scraped - destination_scraped_start,
          destination_new_unique=len(all_listings) - destination_unique_start,
          total_scraped=total_scraped,
          total_unique=len(all_listings),
        )
        page.close()

      context.close()
    except Exception as exc:
      logger.exception("scrape_failed", error=str(exc))
      raise

    elapsed = time.monotonic() - started
    logger.info(
      "scrape_complete",
      count=len(all_listings),
      total_scraped=total_scraped,
      total_unique=len(all_listings),
      duplicates_removed=total_scraped - len(all_listings),
      pages=max_pages,
      destinations=self._search_destinations(),
      elapsed_seconds=round(elapsed, 2),
    )
    return list(all_listings.values())

  def _search_destinations(self) -> list[str]:
    seen: set[str] = set()
    destinations: list[str] = []
    for raw in self.config.trip.destinations or [self.config.trip.destination]:
      destination = raw.strip()
      key = destination.lower()
      if destination and key not in seen:
        destinations.append(destination)
        seen.add(key)
    return destinations or [self.config.trip.destination]

  def _page_delay_seconds(self) -> float:
    base = max(0.0, self.config.scraper.scrape_delay_seconds)
    jitter = random.uniform(0.5, 1.75)
    return base + jitter

  def _scrape_page(self, page: Page, url: str) -> list[Listing]:
    page.goto(url, wait_until="domcontentloaded")
    return self._extract_current_page(page, url)

  def _go_to_next_results_page(self, page: Page) -> bool:
    started = time.monotonic()
    max_attempt_seconds = 2.5
    selectors = [
      'nav[aria-label="Search results pagination"] a[aria-label="Next"]',
      'nav[aria-label="Search results pagination"] button[aria-label="Next"]:not([disabled])',
      'a[aria-label="Next"]',
      'button[aria-label="Next"]:not([disabled])',
    ]
    for selector in selectors:
      remaining_seconds = max_attempt_seconds - (time.monotonic() - started)
      if remaining_seconds <= 0:
        break
      try:
        next_button = page.locator(selector).last
        timeout_ms = max(100, int(min(remaining_seconds, 0.6) * 1000))
        if not next_button.is_visible(timeout=timeout_ms):
          continue
        next_button.click(timeout=max(500, int(remaining_seconds * 1000)))
        page.wait_for_timeout(1500)
        logger.info(
          "pagination_next_selected",
          selector=selector,
          seconds=round(time.monotonic() - started, 2),
          url=page.url,
        )
        return True
      except Exception as exc:
        logger.debug(
          "pagination_next_selector_failed",
          selector=selector,
          error=str(exc),
          seconds=round(time.monotonic() - started, 2),
        )
        continue
    logger.info(
      "pagination_next_unavailable",
      fallback="offset_url_fallback",
      seconds=round(time.monotonic() - started, 2),
      url=page.url,
    )
    return False

  def _extract_current_page(self, page: Page, url: str) -> list[Listing]:
    listings: list[Listing] = []

    try:
      page.wait_for_timeout(3000)

      # Dismiss cookie/consent banners if present
      for selector in [
        'button:has-text("OK")',
        'button:has-text("Accept")',
        'button:has-text("Accept all")',
        '[data-testid="accept-btn"]',
      ]:
        try:
          btn = page.locator(selector).first
          if btn.is_visible(timeout=1500):
            btn.click()
            page.wait_for_timeout(500)
            break
        except Exception:
          continue

      page.wait_for_timeout(2000)
      page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
      page.wait_for_timeout(1500)

      html = page.content()
      listings.extend(self._extract_from_niobe(html))
      listings.extend(self._extract_from_embedded_json(html))
      listings.extend(self._extract_from_dom(page))

    except Exception as exc:
      logger.warning("page_scrape_partial", url=url, error=str(exc))

    return self._dedupe_listings(listings)

  def _dedupe_listings(self, listings: list[Listing]) -> list[Listing]:
    seen: dict[str, Listing] = {}
    for lst in listings:
      if lst.listing_id not in seen:
        seen[lst.listing_id] = lst
      else:
        existing = seen[lst.listing_id]
        seen[lst.listing_id] = self._merge_listing(existing, lst)
    return list(seen.values())

  def _merge_listing(self, a: Listing, b: Listing) -> Listing:
    for field_name in (
      "total_price_eur",
      "review_score",
      "review_count",
      "lat",
      "lng",
      "neighborhood",
      "room_type",
    ):
      if getattr(a, field_name) is None and getattr(b, field_name) is not None:
        setattr(a, field_name, getattr(b, field_name))
    a.is_entire_home = a.is_entire_home or b.is_entire_home
    a.free_cancellation = a.free_cancellation or b.free_cancellation
    a.is_superhost = a.is_superhost or b.is_superhost
    a.self_check_in = a.self_check_in or b.self_check_in
    return a

  def _extract_from_niobe(self, html: str) -> list[Listing]:
    """Parse Airbnb Niobe staysSearch.searchResults (reliable total prices)."""
    listings: list[Listing] = []

    for match in re.finditer(
      r'<script[^>]*type="application/json"[^>]*>(.*?)</script>',
      html,
      re.DOTALL,
    ):
      blob = match.group(1)
      if "niobeClientData" not in blob or "searchResults" not in blob:
        continue
      try:
        data = json.loads(blob)
      except (json.JSONDecodeError, TypeError):
        continue

      for pair in data.get("niobeClientData", []):
        if not isinstance(pair, list) or len(pair) < 2:
          continue
        payload = pair[1]
        if not isinstance(payload, dict):
          continue
        search_results = (
          payload.get("data", {})
          .get("presentation", {})
          .get("staysSearch", {})
          .get("results", {})
          .get("searchResults")
        )
        if not search_results:
          continue
        for item in search_results:
          if not isinstance(item, dict):
            continue
          parsed = self._search_result_to_listing(item)
          if parsed:
            listings.append(parsed)
      if listings:
        break

    return listings

  def _search_result_to_listing(self, result: dict[str, Any]) -> Listing | None:
    dsl = result.get("demandStayListing") or {}
    listing_id = self._decode_demand_stay_id(str(dsl.get("id") or ""))
    if not listing_id or not listing_id.isdigit():
      return None

    title = str(result.get("title") or "Airbnb listing")
    subtitle = str(result.get("subtitle") or "")
    full_title = f"{title} — {subtitle}" if subtitle else title

    price = self._parse_structured_display_price(result.get("structuredDisplayPrice"))
    rating, review_count = self._parse_rating_localized(
      str(result.get("avgRatingLocalized") or result.get("avgRatingA11yLabel") or "")
    )

    lat, lng = None, None
    location = dsl.get("location") or {}
    coord = location.get("coordinate") or {}
    if coord.get("latitude") is not None and coord.get("longitude") is not None:
      lat = float(coord["latitude"])
      lng = float(coord["longitude"])

    badges_text = " ".join(
      b.get("text", "") for b in (result.get("badges") or []) if isinstance(b, dict)
    ).lower()
    room_blob = f"{title} {subtitle} {badges_text}".lower()

    return Listing(
      listing_id=listing_id,
      title=full_title[:200],
      url=f"https://www.airbnb.com/rooms/{listing_id}{self._trip_query_suffix()}",
      total_price_eur=price,
      review_score=rating,
      review_count=review_count,
      lat=lat,
      lng=lng,
      is_entire_home="entire" in room_blob or "apartment" in room_blob,
      free_cancellation="free cancellation" in room_blob,
      is_superhost="superhost" in badges_text,
      self_check_in="self check-in" in room_blob,
      nights=self._nights(),
      raw={"source": "niobe_search_result"},
    )

  def _decode_demand_stay_id(self, encoded: str) -> str | None:
    if not encoded:
      return None
    if encoded.isdigit():
      return encoded
    try:
      decoded = base64.b64decode(encoded + "==").decode("utf-8", errors="ignore")
      if ":" in decoded:
        tail = decoded.split(":", 1)[1]
        if tail.isdigit():
          return tail
    except Exception:
      pass
    m = re.search(r"(\d{5,})", encoded)
    return m.group(1) if m else None

  def _parse_structured_display_price(self, sdp: Any) -> float | None:
    if not isinstance(sdp, dict):
      return None

    lines = [
      line
      for line in (
        sdp.get("primaryLine"),
        sdp.get("secondaryLine"),
        sdp.get("explanationData"),
      )
      if isinstance(line, dict)
    ]

    # Prefer explicit total labels over a primary nightly price.
    text_candidates: list[str] = []
    for line in lines:
      for key in (
        "accessibilityLabel",
        "price",
        "discountedPrice",
        "originalPrice",
        "qualifier",
        "label",
        "title",
        "subtitle",
      ):
        val = line.get(key)
        if isinstance(val, str) and val.strip():
          text_candidates.append(val)
    parsed_from_text = self._parse_price_from_text(" ".join(text_candidates))
    if parsed_from_text:
      return parsed_from_text

    primary = sdp.get("primaryLine") or {}
    if not isinstance(primary, dict):
      return None
    qualifier = str(primary.get("qualifier") or "").lower()
    if qualifier and not self._has_price_context(qualifier):
      return None

    for key in ("discountedPrice", "price"):
      val = primary.get(key)
      if val:
        parsed = self._parse_price_string(str(val))
        if parsed:
          if self._has_nightly_context(qualifier):
            return parsed * self._nights()
          return parsed
    return None

  def _parse_rating_localized(self, text: str) -> tuple[float | None, int | None]:
    m = re.search(r"(\d\.\d{1,2})\s*\((\d+)\)", text)
    if m:
      return float(m.group(1)), int(m.group(2))
    m = re.search(r"(\d\.\d{1,2})", text)
    return (float(m.group(1)), None) if m else (None, None)

  def _extract_from_embedded_json(self, html: str) -> list[Listing]:
    listings: list[Listing] = []
    patterns = [
      r'<script id="data-deferred-state-[^"]+"[^>]*>(.*?)</script>',
      r'<script type="application/json"[^>]*>(.*?)</script>',
      r'"StaysSearchResults".*?"staysSearch".*?"results"',
    ]

    # Try Niobe / deferred state blobs
    for match in re.finditer(
      r'<script[^>]*type="application/json"[^>]*>(.*?)</script>',
      html,
      re.DOTALL,
    ):
      try:
        blob = json.loads(match.group(1))
        listings.extend(self._walk_json_for_listings(blob))
      except (json.JSONDecodeError, TypeError):
        continue

    # Broader regex for listing IDs with nearby price data
    for block in re.finditer(r'"listingId"\s*:\s*"(\d+)"', html):
      lid = block.group(1)
      window = html[max(0, block.start() - 2000) : block.end() + 4000]
      lst = self._parse_listing_window(lid, window)
      if lst:
        listings.append(lst)

    return listings

  def _walk_json_for_listings(self, obj: Any, depth: int = 0) -> list[Listing]:
    if depth > 25:
      return []
    found: list[Listing] = []

    if isinstance(obj, dict):
      if self._looks_like_listing(obj):
        parsed = self._dict_to_listing(obj)
        if parsed:
          found.append(parsed)
      for v in obj.values():
        found.extend(self._walk_json_for_listings(v, depth + 1))
    elif isinstance(obj, list):
      for item in obj:
        found.extend(self._walk_json_for_listings(item, depth + 1))
    return found

  def _looks_like_listing(self, d: dict[str, Any]) -> bool:
    keys = set(d.keys())
    id_keys = {"listingId", "id", "room_id", "roomId"}
    title_keys = {"title", "name", "primaryLine"}
    return bool(keys & id_keys) and bool(keys & title_keys or "demandStayListing" in keys)

  def _dict_to_listing(self, d: dict[str, Any]) -> Listing | None:
    listing_id = str(
      d.get("listingId")
      or d.get("id")
      or d.get("room_id")
      or d.get("roomId")
      or ""
    )
    if not listing_id.isdigit():
      return None

    title = (
      d.get("title")
      or d.get("name")
      or (d.get("title") if isinstance(d.get("title"), str) else None)
      or "Airbnb listing"
    )
    if isinstance(title, dict):
      title = title.get("localizedString") or title.get("accessibilityLabel") or str(title)

    url = d.get("url") or f"https://www.airbnb.com/rooms/{listing_id}"
    if url.startswith("/"):
      url = f"https://www.airbnb.com{url}"

    price = self._extract_price_from_dict(d)
    rating = self._extract_rating_from_dict(d)
    lat, lng = self._extract_coords_from_dict(d)
    neighborhood = self._extract_neighborhood_from_dict(d)
    room_type = str(d.get("roomTypeCategory") or d.get("room_type") or "")
    badges = json.dumps(d).lower()

    return Listing(
      listing_id=listing_id,
      title=str(title)[:200],
      url=url.split("?")[0] + self._trip_query_suffix(),
      total_price_eur=price,
      review_score=rating,
      lat=lat,
      lng=lng,
      neighborhood=neighborhood,
      room_type=room_type,
      is_entire_home="entire" in room_type.lower() or "entire_home" in badges,
      free_cancellation="free cancellation" in badges or "flexible" in badges,
      is_superhost="superhost" in badges,
      self_check_in="self check-in" in badges or "self_check" in badges,
      nights=self._nights(),
      raw={"source": "json", "keys": list(d.keys())[:20]},
    )

  def _parse_listing_window(self, listing_id: str, window: str) -> Listing | None:
    title_m = re.search(r'"title"\s*:\s*"([^"]{5,200})"', window)
    rating_m = re.search(r'"avgRating(?:Localized)?"\s*:\s*([\d.]+)', window)
    lat_m = re.search(r'"lat(?:itude)?"\s*:\s*([\d.-]+)', window)
    lng_m = re.search(r'"lng|lon(?:gitude)?"\s*:\s*([\d.-]+)', window)

    total = self._parse_price_from_text(window)
    rating = float(rating_m.group(1)) if rating_m else None
    lat = float(lat_m.group(1)) if lat_m else None
    lng = float(lng_m.group(1)) if lng_m else None

    return Listing(
      listing_id=listing_id,
      title=title_m.group(1) if title_m else f"Listing {listing_id}",
      url=f"https://www.airbnb.com/rooms/{listing_id}{self._trip_query_suffix()}",
      total_price_eur=total,
      review_score=rating,
      lat=lat,
      lng=lng,
      nights=self._nights(),
      raw={"source": "regex_window"},
    )

  def _trip_query_suffix(self) -> str:
    t = self.config.trip
    return f"?check_in={t.checkin}&check_out={t.checkout}&adults={t.guests}&currency=EUR"

  def _extract_price_from_dict(self, d: dict[str, Any]) -> float | None:
    if "structuredDisplayPrice" in d:
      parsed = self._parse_structured_display_price(d["structuredDisplayPrice"])
      if parsed:
        return parsed
    candidates: list[Any] = []
    for key in (
      "price",
      "priceTotal",
      "totalPrice",
      "pricingQuote",
      "structuredContent",
      "priceDetails",
    ):
      if key in d:
        candidates.append(d[key])
    for c in candidates:
      parsed = self._parse_price_value(c)
      if parsed:
        return parsed
    return None

  def _parse_price_value(self, val: Any) -> float | None:
    if isinstance(val, (int, float)):
      return float(val)
    if isinstance(val, str):
      return self._parse_price_string(val)
    if isinstance(val, dict):
      for k in (
        "total",
        "amount",
        "price",
        "priceString",
        "discountedPrice",
        "totalPrice",
        "localizedString",
        "accessibilityLabel",
      ):
        if k in val:
          p = self._parse_price_value(val[k])
          if p:
            return p
      text_parts = [str(v) for v in val.values() if isinstance(v, str)]
      if text_parts:
        return self._parse_price_from_text(" ".join(text_parts))
    if isinstance(val, list):
      for item in val:
        p = self._parse_price_value(item)
        if p:
          return p
    return None

  def _parse_price_string(self, s: str) -> float | None:
    cleaned = re.sub(r"[^\d.,]", "", s.replace("\xa0", "").replace(" ", ""))
    if not cleaned:
      return None
    if "," in cleaned and "." in cleaned:
      if cleaned.rfind(",") > cleaned.rfind("."):
        cleaned = cleaned.replace(".", "").replace(",", ".")
      else:
        cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
      parts = cleaned.split(",")
      if len(parts[-1]) == 2 and len(parts) == 2:
        cleaned = ".".join(parts)
      else:
        cleaned = "".join(parts)
    elif "." in cleaned:
      parts = cleaned.split(".")
      if len(parts) > 2 or len(parts[-1]) == 3:
        cleaned = "".join(parts)
    try:
      parsed = float(cleaned)
    except ValueError:
      return None
    return parsed if parsed > 0 else None

  def _extract_rating_from_dict(self, d: dict[str, Any]) -> float | None:
    for key in ("avgRating", "rating", "starRating", "avgRatingLocalized"):
      if key in d:
        try:
          val = d[key]
          if isinstance(val, str):
            val = float(re.sub(r"[^\d.]", "", val) or "0")
          return float(val)
        except (TypeError, ValueError):
          continue
    return None

  def _extract_coords_from_dict(self, d: dict[str, Any]) -> tuple[float | None, float | None]:
    if "lat" in d and "lng" in d:
      return float(d["lat"]), float(d["lng"])
    if "coordinate" in d and isinstance(d["coordinate"], dict):
      c = d["coordinate"]
      return c.get("latitude"), c.get("longitude")
    return None, None

  def _extract_neighborhood_from_dict(self, d: dict[str, Any]) -> str | None:
    for key in ("neighborhood", "publicAddress", "subtitle", "localizedCity"):
      val = d.get(key)
      if isinstance(val, str) and val:
        return val
    return None

  def _extract_from_dom(self, page: Page) -> list[Listing]:
    listings: list[Listing] = []
    nights = self._nights()

    cards = page.locator('[data-testid="card-container"]')
    count = min(cards.count(), 40)

    for i in range(count):
      try:
        card = cards.nth(i)
        link = card.locator('a[href*="/rooms/"]').first
        href = link.get_attribute("href") or ""
        if "/rooms/" not in href:
          href = card.get_attribute("href") or ""
        m = LISTING_ID_RE.search(href)
        if not m:
          continue
        listing_id = m.group(1)

        title = ""
        for sel in ("[data-testid='listing-card-title']", "div[id^='title_']", "span"):
          try:
            t = card.locator(sel).first.inner_text(timeout=500).strip()
            if len(t) > 8:
              title = t[:200]
              break
          except Exception:
            continue

        text_blob = ""
        try:
          text_blob = card.inner_text(timeout=800)
        except Exception:
          pass

        price = self._parse_price_from_text(text_blob)
        rating = self._parse_rating_from_text(text_blob)
        neighborhood = self._parse_neighborhood_from_text(text_blob)

        url = href if href.startswith("http") else f"https://www.airbnb.com{href}"
        if "?" not in url:
          url += self._trip_query_suffix().replace("?", "&" if "?" in url else "?")

        listings.append(
          Listing(
            listing_id=listing_id,
            title=title or f"Listing {listing_id}",
            url=url.split("&")[0] if "check_in" not in url else url,
            total_price_eur=price,
            review_score=rating,
            neighborhood=neighborhood,
            is_entire_home="entire" in text_blob.lower(),
            free_cancellation="free cancellation" in text_blob.lower(),
            is_superhost="superhost" in text_blob.lower(),
            self_check_in="self check-in" in text_blob.lower(),
            nights=nights,
            raw={"source": "dom"},
          )
        )
      except Exception:
        continue

    return listings

  def _parse_price_from_text(self, text: str) -> float | None:
    nights = self._nights()
    normalized = re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()
    amount = r"(\d[\d\s.,]*)"
    currency_before = rf"(?:€|EUR)\s*{amount}"
    currency_after = rf"{amount}\s*(?:€|EUR)"
    total_words = rf"total|for\s+\d+\s+nights?|for\s+{nights}\s+nights?|gesamt|insgesamt|toplam"
    night_words = r"night|nights?|per\s+night|nightly|nacht|gece"
    total_patterns = [
      rf"{currency_before}\s*(?:{total_words})",
      rf"{currency_after}\s*(?:{total_words})",
      rf"(?:{total_words})\s*{currency_before}",
      rf"(?:{total_words})\s*{currency_after}",
    ]
    found: list[float] = []
    for pattern in total_patterns:
      for m in re.finditer(pattern, normalized, re.IGNORECASE):
        p = self._parse_price_string(self._first_capture(m))
        if p and p > 50:
          found.append(p)
    if found:
      return found[-1]

    nightly_patterns = [
      rf"{currency_before}\s*(?:/)?\s*(?:{night_words})",
      rf"{currency_after}\s*(?:/)?\s*(?:{night_words})",
      rf"(?:{night_words})\s*{currency_before}",
      rf"(?:{night_words})\s*{currency_after}",
    ]
    nightly: list[float] = []
    for pattern in nightly_patterns:
      for m in re.finditer(pattern, normalized, re.IGNORECASE):
        p = self._parse_price_string(self._first_capture(m))
        if p and p > 10:
          nightly.append(p)
    if nightly:
      return nightly[-1] * nights

    amounts: list[float] = []
    for pattern in (currency_before, currency_after):
      for m in re.finditer(pattern, normalized, re.IGNORECASE):
        p = self._parse_price_string(self._first_capture(m))
        if p and p > 10:
          amounts.append(p)
    if not amounts:
      return None
    if len(amounts) == 1:
      return amounts[0]
    totals = [p for p in amounts if p > max(50, nights * 15)]
    return totals[-1] if totals else amounts[-1]

  @staticmethod
  def _first_capture(match: re.Match[str]) -> str:
    for group in match.groups():
      if group:
        return group
    return match.group(0)

  @staticmethod
  def _has_price_context(text: str) -> bool:
    return bool(
      re.search(
        r"total|night|nights?|per\s+night|nightly|gesamt|insgesamt|toplam|nacht|gece",
        text,
        re.IGNORECASE,
      )
    )

  @staticmethod
  def _has_nightly_context(text: str) -> bool:
    return bool(
      re.search(r"night|nights?|per\s+night|nightly|nacht|gece", text, re.IGNORECASE)
    )

  def _parse_rating_from_text(self, text: str) -> float | None:
    m = re.search(r"(\d\.\d{1,2})\s*(?:\(|·|out of)", text)
    if m:
      return float(m.group(1))
    m = re.search(r"★\s*(\d\.\d{1,2})", text)
    return float(m.group(1)) if m else None

  def _parse_neighborhood_from_text(self, text: str) -> str | None:
    for hood in self.config.preferred_neighborhoods:
      if hood.lower() in text.lower():
        return hood
    m = re.search(r"in\s+([A-Za-zÀ-ÿ\s]+),", text)
    return m.group(1).strip() if m else None
