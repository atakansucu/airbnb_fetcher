"""Domain models for listings and alerts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class AlertType(str, Enum):
    NEW_LISTING = "new_listing"
    PRICE_DROP = "price_drop"
    RARE_DEAL = "rare_deal"
    SCORE_MATCH = "score_match"


@dataclass
class Listing:
    listing_id: str
    title: str
    url: str
    total_price_eur: float | None = None
    price_per_night_eur: float | None = None
    currency: str = "EUR"
    review_score: float | None = None
    review_count: int | None = None
    lat: float | None = None
    lng: float | None = None
    neighborhood: str | None = None
    room_type: str | None = None
    is_entire_home: bool = False
    free_cancellation: bool = False
    is_superhost: bool = False
    self_check_in: bool = False
    distance_km: float | None = None
    nights: int = 6
    raw: dict[str, Any] = field(default_factory=dict)
    scraped_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def price_per_night_computed(self) -> float | None:
        if self.price_per_night_eur is not None:
            return self.price_per_night_eur
        if self.total_price_eur and self.nights > 0:
            return self.total_price_eur / self.nights
        return None


@dataclass
class ScoredListing:
    listing: Listing
    composite_score: float
    distance_score: float
    price_score: float
    review_score: float
    cancellation_score: float
    entire_home_score: float
    neighborhood_bonus: float = 0.0
    is_rare_deal: bool = False
    rare_deal_reason: str | None = None

    def summary_lines(self) -> list[str]:
        l = self.listing
        lines = [
            f"*{l.title[:80]}*",
            f"Skor: {self.composite_score:.1f}/100",
            f"Fiyat: €{l.total_price_eur:.0f} toplam" if l.total_price_eur else "Fiyat: bilinmiyor",
        ]
        if l.review_score:
            lines.append(f"Puan: {l.review_score:.2f} ({l.review_count or '?'} yorum)")
        if l.distance_km is not None:
            lines.append(f"Plaja uzaklık: {l.distance_km:.2f} km ({l.neighborhood or '?'})")
        flags = []
        if l.is_entire_home:
            flags.append("Tüm daire")
        if l.free_cancellation:
            flags.append("Ücretsiz iptal")
        if l.is_superhost:
            flags.append("Superhost")
        if l.self_check_in:
            flags.append("Self check-in")
        if flags:
            lines.append(" | ".join(flags))
        if self.is_rare_deal and self.rare_deal_reason:
            lines.append(f"Fırsat: {self.rare_deal_reason}")
        lines.append(l.url)
        return lines


@dataclass
class Alert:
    alert_type: AlertType
    scored: ScoredListing
    message: str
    created_at: datetime = field(default_factory=datetime.utcnow)
