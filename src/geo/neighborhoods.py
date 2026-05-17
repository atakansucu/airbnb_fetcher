"""Approximate coordinates for Barcelona neighborhoods (fallback when scrape lacks lat/lng)."""

from __future__ import annotations

NEIGHBORHOOD_COORDS: dict[str, tuple[float, float]] = {
    "eixample": (41.389, 2.168),
    "gothic": (41.383, 2.176),
    "gòtic": (41.383, 2.176),
    "gotico": (41.383, 2.176),
    "born": (41.384, 2.182),
    "gràcia": (41.403, 2.156),
    "gracia": (41.403, 2.156),
    "sant antoni": (41.379, 2.162),
    "raval": (41.380, 2.168),
    "poble sec": (41.373, 2.165),
    "barceloneta": (41.380, 2.189),
    "poblenou": (41.398, 2.204),
    "sants": (41.375, 2.140),
}


def coords_for_neighborhood(name: str | None) -> tuple[float, float] | None:
    if not name:
        return None
    lower = name.lower()
    for key, coords in NEIGHBORHOOD_COORDS.items():
        if key in lower:
            return coords
    return None
