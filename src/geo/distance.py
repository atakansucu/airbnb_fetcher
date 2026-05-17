"""Distance calculations to city center (Plaça de Catalunya)."""

from __future__ import annotations

import math


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two WGS84 points in kilometers."""
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(min(1.0, a)))


def distance_to_center(
    lat: float | None,
    lng: float | None,
    center_lat: float,
    center_lng: float,
) -> float | None:
    if lat is None or lng is None:
        return None
    return round(haversine_km(lat, lng, center_lat, center_lng), 3)
