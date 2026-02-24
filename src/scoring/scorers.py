"""Individual scoring functions for each fishing condition dimension.

Each function returns an integer 0-20.  They are pure functions with
no side effects — they take simple typed inputs and produce a score.
The thresholds come from the scoring algorithm in fishing-analytics-app-plan.md.
"""

from __future__ import annotations


def estimate_water_temp_from_air(air_temp_c: float, elevation_ft: float = 6000.0) -> float:
    """Rough water temp estimate from air temp with elevation adjustment.

    Water temperature lags air temperature by ~4 °C and is slightly
    cooler at higher elevations.  Better than returning neutral (10).
    """
    lag = 4.0
    elevation_adjustment = (elevation_ft - 6000) * 0.001
    return air_temp_c - lag - elevation_adjustment


def score_water_temperature(temp_celsius: float | None) -> int:
    """Score water temperature for trout fishing (0-20).

    Ideal range for Rainbow/Brown Trout is 50-62 F (10-16.7 C).
    """
    if temp_celsius is None:
        return 10  # neutral when data unavailable

    temp_f = temp_celsius * 9 / 5 + 32

    if 50 <= temp_f <= 62:
        return 20
    if 45 <= temp_f < 50:
        return 15
    if 62 < temp_f <= 65:
        return 15
    if 40 <= temp_f < 45:
        return 8
    if 65 < temp_f <= 68:
        return 5
    # < 40 or > 68
    return 0


def score_flow(
    current_cfs: float | None,
    historical_median_cfs: float | None = None,
) -> int:
    """Score streamflow relative to historical median (0-20).

    When historical median is available, uses percentile-style comparison.
    Otherwise returns a neutral score.
    """
    if current_cfs is None:
        return 10  # neutral when data unavailable

    if historical_median_cfs is None or historical_median_cfs <= 0:
        return 10  # neutral when no baseline

    ratio = current_cfs / historical_median_cfs

    # Approximate percentile mapping via ratio to median
    # ratio ~1.0 → near 50th percentile (normal)
    if 0.6 <= ratio <= 1.5:
        return 20  # ~25th-75th percentile (normal)
    if 0.3 <= ratio < 0.6:
        return 14  # ~10th-25th (low but fishable)
    if 1.5 < ratio <= 2.5:
        return 12  # ~75th-90th (high but fishable)
    if ratio < 0.3:
        return 5  # <10th (drought/very low)
    # ratio > 2.5
    return 0  # >90th (flood/blowout)


def score_weather(
    pressure_trend: str,
    cloud_cover_pct: float,
    wind_speed_kmh: float,
) -> int:
    """Score weather conditions for fishing (0-20).

    Based on barometric pressure trend, cloud cover, and wind.
    """
    # Base score from pressure trend
    trend_scores = {
        "falling_steady": 17,
        "stable_low": 14,
        "stable_high": 11,
        "rising_steady": 7,
        "falling_rapid": 4,
    }
    base = trend_scores.get(pressure_trend, 10)

    # Cloud cover modifier
    if cloud_cover_pct >= 80:
        base += 2  # overcast
    elif cloud_cover_pct >= 40:
        base += 1  # partly cloudy

    # Wind modifier
    wind_mph = wind_speed_kmh * 0.621371
    if 5 <= wind_mph <= 15:
        base += 1  # good chop
    elif wind_mph > 25:
        base -= 3  # unfishable

    return max(0, min(20, base))


def score_solunar(solunar_rating: int) -> int:
    """Pass through the solunar rating (already 0-20 from calculator)."""
    return max(0, min(20, solunar_rating))


def score_stocking(
    days_since_stocking: int | None,
    is_gold_medal: bool = False,
    water_type: str = "",
) -> int:
    """Score based on recent stocking and Gold Medal designation (0-20).

    Returns higher scores for recently stocked waters.
    Gold Medal waters get a +5 bonus (they always fish well).
    Rivers without stocking data are treated as productive wild fisheries.
    """
    if days_since_stocking is not None and days_since_stocking <= 3:
        base = 20
    elif days_since_stocking is not None and days_since_stocking <= 7:
        base = 15
    elif days_since_stocking is not None and days_since_stocking <= 14:
        base = 8
    elif days_since_stocking is None and is_gold_medal:
        base = 10  # wild fish / Gold Medal waters
    elif days_since_stocking is None and water_type == "river":
        base = 12  # wild fishery — rivers without stocking are naturally productive
    else:
        base = 5  # no recent stocking

    if is_gold_medal:
        base += 5

    return min(20, base)
