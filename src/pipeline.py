"""Pipeline orchestrator — fetches all data, computes scores, stores results.

This is the main entry point that ties together data ingestion,
scoring, and storage.  Run directly or via ``docker-compose up app``.

Usage:
    python -m pipeline                  # score all MVP waters
    python -m pipeline --dry-run        # print scores without storing to DB
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta

import pandas as pd

from ingest.cpw_stocking import CPWStockingClient
from ingest.usgs_water import USGSWaterClient
from ingest.weather import WeatherClient
from locations.colorado_waters import MVP_WATERS, get_locations_with_gauge
from scoring.engine import compute_score
from solunar.calculator import compute_solunar_rating
from storage.models import FishingLocation, FishingScore, StockingEvent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
log = logging.getLogger(__name__)


def fetch_water_data(
    usgs: USGSWaterClient,
    location: FishingLocation,
) -> dict:
    """Fetch recent USGS water data for a location.

    Returns a dict with keys: water_temp_c, streamflow_cfs.
    Values are None if unavailable.
    """
    result: dict = {"water_temp_c": None, "streamflow_cfs": None}

    if not location.usgs_site_code:
        return result

    try:
        df = usgs.get_site_data(location.usgs_site_code, period="P1D")
    except Exception as exc:
        log.warning("USGS fetch failed for %s: %s", location.id, exc)
        return result

    if df.empty:
        return result

    # Get latest streamflow
    flow = df[df["parameter_code"] == "00060"]
    if not flow.empty:
        latest = flow.sort_values("datetime").iloc[-1]["value"]
        if pd.notna(latest):
            result["streamflow_cfs"] = float(latest)

    # Get latest water temperature
    temp = df[df["parameter_code"] == "00010"]
    if not temp.empty:
        latest = temp.sort_values("datetime").iloc[-1]["value"]
        if pd.notna(latest):
            result["water_temp_c"] = float(latest)

    return result


def fetch_weather_data(
    weather: WeatherClient,
    location: FishingLocation,
) -> dict:
    """Fetch weather conditions for a location.

    Returns a dict with keys: pressure_trend, cloud_cover_pct, wind_speed_kmh.
    """
    result = {
        "pressure_trend": "stable_high",
        "cloud_cover_pct": 50.0,
        "wind_speed_kmh": 10.0,
    }

    try:
        df = weather.get_forecast(location.latitude, location.longitude, days=1)
    except Exception as exc:
        log.warning("Weather fetch failed for %s: %s", location.id, exc)
        return result

    if df.empty:
        return result

    now = pd.Timestamp.now(tz="America/Denver").tz_localize(None)
    past = df[df["datetime"] <= now]

    if not past.empty:
        latest = past.iloc[-1]
        result["cloud_cover_pct"] = float(latest["cloud_cover_pct"])
        result["wind_speed_kmh"] = float(latest["wind_speed_kmh"])

        # Compute pressure trend from last 6 hours
        six_hours_ago = now - pd.Timedelta(hours=6)
        recent_pressure = df[
            (df["datetime"] >= six_hours_ago) & (df["datetime"] <= now)
        ]["pressure_hpa"]
        if len(recent_pressure) >= 2:
            result["pressure_trend"] = weather.compute_pressure_trend(recent_pressure)

    return result


def find_days_since_stocking(
    location: FishingLocation,
    stockings: list[StockingEvent],
) -> int | None:
    """Find how many days since the most recent stocking for this location."""
    today = date.today()
    best: int | None = None

    for event in stockings:
        if event.location_id == location.id:
            days = (today - event.stocking_date).days
            if days >= 0 and (best is None or days < best):
                best = days

    return best


def _init_db():
    """Try to connect to the database and initialise the schema.

    Returns a ``FishingDB`` instance on success, or ``None`` when the
    database is unavailable (e.g. during ``--dry-run``).
    """
    try:
        from storage.db import FishingDB

        db = FishingDB()
        db.init_schema()
        return db
    except Exception as exc:
        log.warning("Database unavailable: %s", exc)
        return None


def _ensure_flow_stats_cached(
    usgs: USGSWaterClient,
    db,
    gauged: list[FishingLocation],
) -> None:
    """Fetch and cache USGS daily flow statistics for any uncached sites."""
    missing_sites = [
        loc.usgs_site_code
        for loc in gauged
        if not db.has_flow_stats(loc.usgs_site_code)
    ]
    if not missing_sites:
        log.info("Daily flow stats already cached for all %d gauges", len(gauged))
        return

    log.info("Fetching daily flow stats for %d uncached gauge(s)...", len(missing_sites))
    try:
        stats_df = usgs.get_daily_flow_stats(missing_sites)
        if not stats_df.empty:
            count = db.save_daily_flow_stats(stats_df)
            log.info("Cached %d daily flow stat rows", count)
        else:
            log.warning("USGS Statistics Service returned no data")
    except Exception as exc:
        log.warning("Failed to fetch daily flow stats: %s", exc)


def _lookup_median(
    loc: FishingLocation,
    db,
    today: date,
) -> float | None:
    """Look up today's historical median flow for a location.

    Tries the DB cache first, then falls back to the hardcoded value
    on the location object.
    """
    if not loc.usgs_site_code:
        return loc.historical_median_cfs

    if db is not None:
        median = db.get_median_flow(loc.usgs_site_code, today.month, today.day)
        if median is not None:
            return median

    # Fallback to hardcoded value
    return loc.historical_median_cfs


def run_pipeline(dry_run: bool = False) -> list[FishingScore]:
    """Execute the full pipeline: fetch data, score, optionally store."""
    log.info("Starting pipeline for %d locations", len(MVP_WATERS))

    usgs = USGSWaterClient()
    weather = WeatherClient()
    cpw = CPWStockingClient()

    # Database — may be None when unavailable or in dry-run mode
    db = None if dry_run else _init_db()

    # Pre-fetch and cache daily flow statistics (median by day-of-year)
    gauged = get_locations_with_gauge()
    if db is not None:
        _ensure_flow_stats_cached(usgs, db, gauged)

    # Fetch stocking report once (shared across all locations)
    stockings: list[StockingEvent] = []
    try:
        html = cpw.fetch_current_report()
        stockings = cpw.parse_stocking_report(html)
        log.info("Fetched %d stocking events", len(stockings))
    except Exception as exc:
        log.warning("CPW stocking fetch failed: %s", exc)

    today = date.today()
    scores: list[FishingScore] = []

    for loc in MVP_WATERS:
        log.info("Processing %s ...", loc.name)

        # 1. Water data
        water = fetch_water_data(usgs, loc)

        # 2. Weather data
        wx = fetch_weather_data(weather, loc)

        # 3. Solunar rating
        solunar_rating = compute_solunar_rating(
            today, loc.latitude, loc.longitude
        )

        # 4. Stocking recency
        days_since = find_days_since_stocking(loc, stockings)

        # 5. Look up today's historical median flow (dynamic > hardcoded)
        median = _lookup_median(loc, db, today)

        # 6. Compute score
        score = compute_score(
            loc,
            water_temp_c=water["water_temp_c"],
            streamflow_cfs=water["streamflow_cfs"],
            historical_median_cfs=median,
            pressure_trend=wx["pressure_trend"],
            cloud_cover_pct=wx["cloud_cover_pct"],
            wind_speed_kmh=wx["wind_speed_kmh"],
            solunar_rating=solunar_rating,
            days_since_stocking=days_since,
        )
        scores.append(score)

    # Sort by total score descending
    scores.sort(key=lambda s: s.total, reverse=True)

    # Store results
    if db is not None:
        try:
            db.upsert_locations(MVP_WATERS)
            db.save_scores(scores)
            log.info("Scores saved to database")
        except Exception as exc:
            log.warning("Database storage failed: %s", exc)
        finally:
            db.close()

    return scores


def print_scores(scores: list[FishingScore]) -> None:
    """Print a ranked leaderboard to stdout."""
    print("\n" + "=" * 70)
    print("  COLORADO FISHING CONDITIONS — TODAY'S SCORES")
    print("=" * 70)
    print(f"  {'Score':>5}  {'Label':6s}  {'Water':<40s}")
    print("-" * 70)
    for s in scores:
        print(f"  {s.total:>5d}  {s.label:6s}  {s.location_name:<40s}")
        print(
            f"         Temp:{s.water_temp_score:2d} "
            f"Flow:{s.flow_score:2d} "
            f"Wx:{s.weather_score:2d} "
            f"Sol:{s.solunar_score:2d} "
            f"Stock:{s.stocking_score:2d}"
        )
    print("=" * 70 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Colorado Fishing Conditions Pipeline")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print scores without storing to database",
    )
    args = parser.parse_args()

    scores = run_pipeline(dry_run=args.dry_run)
    print_scores(scores)
