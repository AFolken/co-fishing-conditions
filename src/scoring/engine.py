"""Composite scoring engine.

Combines all five individual scorers into a single ``FishingScore``
for a given location.  Handles missing data gracefully by using
neutral scores for unavailable components.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from scoring.scorers import (
    score_flow,
    score_solunar,
    score_stocking,
    score_water_temperature,
    score_weather,
)
from storage.models import FishingLocation, FishingScore


def compute_score(
    location: FishingLocation,
    *,
    water_temp_c: float | None = None,
    streamflow_cfs: float | None = None,
    historical_median_cfs: float | None = None,
    pressure_trend: str = "stable_high",
    cloud_cover_pct: float = 50.0,
    wind_speed_kmh: float = 10.0,
    solunar_rating: int = 10,
    days_since_stocking: int | None = None,
) -> FishingScore:
    """Compute the composite fishing score for a single location.

    All data parameters are optional — missing data degrades gracefully
    to neutral (10/20) scores rather than failing.
    """
    wt = score_water_temperature(water_temp_c)
    fl = score_flow(streamflow_cfs, historical_median_cfs)
    wx = score_weather(pressure_trend, cloud_cover_pct, wind_speed_kmh)
    sl = score_solunar(solunar_rating)
    st = score_stocking(days_since_stocking, is_gold_medal=location.is_gold_medal)

    return FishingScore(
        location_id=location.id,
        location_name=location.name,
        score_date=date.today(),
        water_temp_score=wt,
        flow_score=fl,
        weather_score=wx,
        solunar_score=sl,
        stocking_score=st,
        computed_at=datetime.now(tz=timezone.utc),
    )


def label_score(total: int) -> str:
    """Map a total score (0-100) to a human-readable label."""
    if total >= 80:
        return "Epic"
    if total >= 60:
        return "Good"
    if total >= 40:
        return "Fair"
    if total >= 20:
        return "Tough"
    return "Poor"
