"""Solunar feeding-window calculator using PyEphem.

Computes moon phase, rise/set/transit times, and major/minor feeding
periods for a given location and date.  Also provides a composite
0-20 solunar score for use in the scoring engine.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta, timezone

import ephem

# ---------------------------------------------------------------------------
# Phase thresholds (illumination-based, 0–1)
# ---------------------------------------------------------------------------
_PHASE_NAMES = [
    (0.02, "new"),
    (0.24, "waxing_crescent"),
    (0.26, "first_quarter"),
    (0.74, "waxing_gibbous"),
    (0.76, "full"),
    (0.98, "waning_gibbous"),
    (1.00, "last_quarter"),  # technically > 0.98 + waning
]

# Major feeding window: ±1 hour around transit/anti-transit
_MAJOR_HALF_WINDOW = timedelta(hours=1)
# Minor feeding window: ±30 min around moonrise/moonset
_MINOR_HALF_WINDOW = timedelta(minutes=30)

# Dawn/dusk overlap tolerance
_OVERLAP_WINDOW = timedelta(minutes=60)


def _ephem_date(d: date) -> ephem.Date:
    """Convert a Python date to an ephem.Date at noon UTC (to avoid edge cases)."""
    return ephem.Date(datetime(d.year, d.month, d.day, 12, 0, 0, tzinfo=timezone.utc))


def _ephem_to_datetime(e: ephem.Date) -> datetime:
    """Convert ephem.Date to a timezone-aware UTC datetime."""
    return ephem.Date(e).datetime().replace(tzinfo=timezone.utc)


def _make_observer(d: date, lat: float, lon: float) -> ephem.Observer:
    obs = ephem.Observer()
    obs.lat = str(lat)
    obs.lon = str(lon)
    obs.date = _ephem_date(d)
    obs.pressure = 0  # disable atmospheric refraction for consistency
    obs.horizon = "0"
    return obs


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_moon_phase(d: date) -> tuple[str, float]:
    """Return the moon phase name and illumination fraction (0.0-1.0).

    Parameters
    ----------
    d : date
        The date to compute the phase for.

    Returns
    -------
    tuple[str, float]
        (phase_name, illumination) where illumination is 0.0 (new) to 1.0 (full).
    """
    moon = ephem.Moon()
    moon.compute(_ephem_date(d))
    illum = moon.phase / 100.0  # ephem gives 0-100, we want 0-1

    # Determine if waxing or waning by comparing to next day
    moon_next = ephem.Moon()
    moon_next.compute(_ephem_date(d + timedelta(days=1)))
    waxing = moon_next.phase > moon.phase

    name = _classify_phase(illum, waxing)
    return name, illum


def _classify_phase(illum: float, waxing: bool) -> str:
    if illum < 0.02:
        return "new"
    if illum > 0.98:
        return "full"
    if 0.45 <= illum <= 0.55:
        return "first_quarter" if waxing else "last_quarter"
    if waxing:
        return "waxing_crescent" if illum < 0.45 else "waxing_gibbous"
    return "waning_gibbous" if illum > 0.55 else "waning_crescent"


def get_moon_times(d: date, lat: float, lon: float) -> dict[str, datetime | None]:
    """Return moonrise, moonset, transit, and anti-transit times.

    Returns
    -------
    dict
        Keys: ``moonrise``, ``moonset``, ``transit``, ``antitransit``.
        Values are UTC datetimes or ``None`` if the event doesn't occur
        (e.g. circumpolar moon).
    """
    obs = _make_observer(d, lat, lon)
    # Start at 7 AM UTC (~midnight Mountain) so events fall within the local day
    start_utc = ephem.Date(datetime(d.year, d.month, d.day, 7, 0, 0, tzinfo=timezone.utc))
    moon = ephem.Moon()

    result: dict[str, datetime | None] = {
        "moonrise": None,
        "moonset": None,
        "transit": None,
        "antitransit": None,
    }

    obs.date = start_utc
    try:
        result["moonrise"] = _ephem_to_datetime(obs.next_rising(moon))
    except (ephem.AlwaysUpError, ephem.NeverUpError):
        pass

    obs.date = start_utc
    try:
        result["moonset"] = _ephem_to_datetime(obs.next_setting(moon))
    except (ephem.AlwaysUpError, ephem.NeverUpError):
        pass

    obs.date = start_utc
    try:
        result["transit"] = _ephem_to_datetime(obs.next_transit(moon))
    except Exception:
        pass

    obs.date = start_utc
    try:
        result["antitransit"] = _ephem_to_datetime(obs.next_antitransit(moon))
    except Exception:
        pass

    return result


def get_sun_times(d: date, lat: float, lon: float) -> dict[str, datetime | None]:
    """Return sunrise and sunset times.

    Returns
    -------
    dict
        Keys: ``sunrise``, ``sunset``.  Values are UTC datetimes or ``None``.
    """
    obs = _make_observer(d, lat, lon)
    # Start at 7 AM UTC (~midnight Mountain) so both events fall on the local day
    start_utc = ephem.Date(datetime(d.year, d.month, d.day, 7, 0, 0, tzinfo=timezone.utc))
    sun = ephem.Sun()

    result: dict[str, datetime | None] = {"sunrise": None, "sunset": None}

    obs.date = start_utc
    try:
        result["sunrise"] = _ephem_to_datetime(obs.next_rising(sun))
    except (ephem.AlwaysUpError, ephem.NeverUpError):
        pass

    obs.date = start_utc
    try:
        result["sunset"] = _ephem_to_datetime(obs.next_setting(sun))
    except (ephem.AlwaysUpError, ephem.NeverUpError):
        pass

    return result


def get_feeding_windows(
    d: date, lat: float, lon: float
) -> dict[str, list[tuple[datetime, datetime]]]:
    """Compute major and minor solunar feeding windows.

    Major periods (~2 hours) are centred on lunar transit and anti-transit.
    Minor periods (~1 hour) are centred on moonrise and moonset.

    Returns
    -------
    dict
        ``{"major": [...], "minor": [...]}`` where each list contains
        ``(start, end)`` UTC datetime tuples.
    """
    moon_times = get_moon_times(d, lat, lon)

    major: list[tuple[datetime, datetime]] = []
    minor: list[tuple[datetime, datetime]] = []

    for key in ("transit", "antitransit"):
        t = moon_times.get(key)
        if t is not None:
            major.append((t - _MAJOR_HALF_WINDOW, t + _MAJOR_HALF_WINDOW))

    for key in ("moonrise", "moonset"):
        t = moon_times.get(key)
        if t is not None:
            minor.append((t - _MINOR_HALF_WINDOW, t + _MINOR_HALF_WINDOW))

    return {"major": major, "minor": minor}


def _overlaps_dawn_dusk(
    window: tuple[datetime, datetime],
    sun_times: dict[str, datetime | None],
) -> bool:
    """Check if a feeding window overlaps with dawn or dusk (±1 hour)."""
    start, end = window
    for key in ("sunrise", "sunset"):
        t = sun_times.get(key)
        if t is None:
            continue
        dawn_dusk_start = t - _OVERLAP_WINDOW
        dawn_dusk_end = t + _OVERLAP_WINDOW
        if start <= dawn_dusk_end and end >= dawn_dusk_start:
            return True
    return False


def compute_solunar_rating(d: date, lat: float, lon: float) -> int:
    """Compute a 0-20 solunar fishing score for the given date and location.

    Scoring rules (from plan):
      - New/Full moon + major period overlaps dawn/dusk → 20
      - New/Full moon day → 16
      - Quarter moon + major period overlaps dawn/dusk → 12
      - Quarter moon day → 8
      - Worst case (last quarter, no overlaps) → 4
    """
    phase_name, illum = get_moon_phase(d)
    windows = get_feeding_windows(d, lat, lon)
    sun_times = get_sun_times(d, lat, lon)

    # Check if any major period overlaps dawn/dusk
    has_overlap = any(
        _overlaps_dawn_dusk(w, sun_times) for w in windows["major"]
    )

    is_new_or_full = phase_name in ("new", "full")
    is_quarter = phase_name in ("first_quarter", "last_quarter")

    if is_new_or_full and has_overlap:
        return 20
    if is_new_or_full:
        return 16
    if is_quarter and has_overlap:
        return 12
    if is_quarter:
        return 8

    # Intermediate phases — scale between 4 and 14 based on illumination
    # proximity to new/full moon
    proximity = 1.0 - abs(illum - 0.5) * 2  # 1.0 at new/full, 0.0 at quarter
    base = 4 + int(proximity * 10)
    if has_overlap:
        base = min(base + 4, 18)  # overlap bonus, capped below new/full
    return base
