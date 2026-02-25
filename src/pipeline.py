"""Pipeline orchestrator — fetches all data, computes scores, stores results.

This is the main entry point that ties together data ingestion,
scoring, and storage.  Run directly or via ``docker-compose up app``.

Usage:
    python -m pipeline                  # score all MVP waters
    python -m pipeline --dry-run        # print scores without storing to DB
    python -m pipeline --best-bets      # print weekend best-bets summary
    python -m pipeline --forecast 7     # print 7-day forecast
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
) -> tuple[dict, pd.DataFrame]:
    """Fetch recent USGS water data for a location.

    Returns a tuple of (result_dict, raw_dataframe).
    The dict has keys: water_temp_c, streamflow_cfs (None if unavailable).
    The raw DataFrame may be empty if no data is available.
    """
    result: dict = {"water_temp_c": None, "streamflow_cfs": None}
    empty_df = pd.DataFrame()

    if not location.usgs_site_code:
        return result, empty_df

    try:
        df = usgs.get_site_data(location.usgs_site_code, period="P1D")
    except Exception as exc:
        log.warning("USGS fetch failed for %s: %s", location.id, exc)
        return result, empty_df

    if df.empty:
        return result, empty_df

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

    return result, df


def fetch_weather_data(
    weather: WeatherClient,
    location: FishingLocation,
    days: int = 1,
) -> tuple[dict, pd.DataFrame]:
    """Fetch weather conditions for a location.

    Returns a tuple of (result_dict, raw_dataframe).
    The dict has keys: pressure_trend, cloud_cover_pct, wind_speed_kmh, air_temp_c.
    The raw DataFrame contains all hourly forecast rows.
    """
    result = {
        "pressure_trend": "stable_high",
        "cloud_cover_pct": 50.0,
        "wind_speed_kmh": 10.0,
        "air_temp_c": None,
    }
    empty_df = pd.DataFrame()

    try:
        df = weather.get_forecast(location.latitude, location.longitude, days=days)
    except Exception as exc:
        log.warning("Weather fetch failed for %s: %s", location.id, exc)
        return result, empty_df

    if df.empty:
        return result, empty_df

    now = pd.Timestamp.now(tz="America/Denver").tz_localize(None)
    past = df[df["datetime"] <= now]

    if not past.empty:
        latest = past.iloc[-1]
        result["cloud_cover_pct"] = float(latest["cloud_cover_pct"])
        result["wind_speed_kmh"] = float(latest["wind_speed_kmh"])
        result["air_temp_c"] = float(latest["temperature_c"])

        # Compute pressure trend from last 6 hours
        six_hours_ago = now - pd.Timedelta(hours=6)
        recent_pressure = df[
            (df["datetime"] >= six_hours_ago) & (df["datetime"] <= now)
        ]["pressure_hpa"]
        if len(recent_pressure) >= 2:
            result["pressure_trend"] = weather.compute_pressure_trend(recent_pressure)

    return result, df


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

    # Persist stocking events to DB
    if db is not None and stockings:
        try:
            db.save_stocking_events(stockings)
            log.info("Stocking events saved to database")
        except Exception as exc:
            log.warning("Failed to save stocking events: %s", exc)

    today = date.today()
    scores: list[FishingScore] = []

    for loc in MVP_WATERS:
        log.info("Processing %s ...", loc.name)

        # 1. Water data
        water, water_df = fetch_water_data(usgs, loc)

        # Persist raw water observations
        if db is not None and not water_df.empty:
            try:
                db.save_water_observations(loc.id, water_df)
            except Exception as exc:
                log.warning("Failed to save water observations for %s: %s", loc.id, exc)

        # 2. Weather data
        wx, wx_df = fetch_weather_data(weather, loc)

        # Persist raw weather forecast
        if db is not None and not wx_df.empty:
            try:
                db.save_weather_forecast(loc.id, wx_df)
            except Exception as exc:
                log.warning("Failed to save weather forecast for %s: %s", loc.id, exc)

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
            air_temp_c=wx["air_temp_c"],
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


def _extract_daily_weather(
    wx_df: pd.DataFrame,
    target_date: date,
    weather_client: WeatherClient,
) -> dict:
    """Extract weather conditions for a single day from a multi-day forecast DataFrame.

    Filters hourly rows to the target date, computes pressure trend,
    and averages cloud cover and wind speed for the day.
    """
    result = {
        "pressure_trend": "stable_high",
        "cloud_cover_pct": 50.0,
        "wind_speed_kmh": 10.0,
        "air_temp_c": None,
    }
    if wx_df.empty:
        return result

    target_ts = pd.Timestamp(target_date)
    day_rows = wx_df[wx_df["datetime"].dt.date == target_date]
    if day_rows.empty:
        return result

    # Pressure trend: use all hours in the day
    pressures = day_rows["pressure_hpa"].dropna()
    if len(pressures) >= 2:
        result["pressure_trend"] = weather_client.compute_pressure_trend(pressures)

    result["cloud_cover_pct"] = float(day_rows["cloud_cover_pct"].mean())
    result["wind_speed_kmh"] = float(day_rows["wind_speed_kmh"].mean())

    # Use midday temperature (or closest available)
    midday = target_ts + pd.Timedelta(hours=12)
    temps = day_rows["temperature_c"].dropna()
    if not temps.empty:
        closest_idx = (day_rows["datetime"] - midday).abs().idxmin()
        result["air_temp_c"] = float(day_rows.loc[closest_idx, "temperature_c"])

    return result


def run_forecast(days: int = 7) -> dict[str, list[FishingScore]]:
    """Compute projected scores for each location over the next N days.

    Uses today's water data (USGS doesn't forecast) combined with
    per-day weather forecasts and solunar ratings.

    Returns a dict mapping location_id to a list of FishingScore objects,
    one per day (starting from today).
    """
    log.info("Running %d-day forecast for %d locations", days, len(MVP_WATERS))

    usgs = USGSWaterClient()
    weather = WeatherClient()
    cpw = CPWStockingClient()

    today = date.today()

    # Fetch stocking report once
    stockings: list[StockingEvent] = []
    try:
        html = cpw.fetch_current_report()
        stockings = cpw.parse_stocking_report(html)
    except Exception as exc:
        log.warning("CPW stocking fetch failed: %s", exc)

    forecast: dict[str, list[FishingScore]] = {}

    for loc in MVP_WATERS:
        log.info("Forecasting %s ...", loc.name)

        # Water data: today's conditions (best available for all days)
        water, _ = fetch_water_data(usgs, loc)

        # Weather: fetch full multi-day forecast in one call
        _, wx_df = fetch_weather_data(weather, loc, days=days)

        # Stocking recency for today
        base_days_since = find_days_since_stocking(loc, stockings)

        # Historical median flow
        median = loc.historical_median_cfs

        day_scores: list[FishingScore] = []
        for offset in range(days):
            target_date = today + timedelta(days=offset)

            # Extract weather for this specific day
            day_wx = _extract_daily_weather(wx_df, target_date, weather)

            # Solunar rating for this specific day
            solunar_rating = compute_solunar_rating(
                target_date, loc.latitude, loc.longitude
            )

            # Adjust stocking recency by offset
            days_since = None
            if base_days_since is not None:
                days_since = base_days_since + offset

            score = compute_score(
                loc,
                water_temp_c=water["water_temp_c"],
                air_temp_c=day_wx["air_temp_c"],
                streamflow_cfs=water["streamflow_cfs"],
                historical_median_cfs=median,
                pressure_trend=day_wx["pressure_trend"],
                cloud_cover_pct=day_wx["cloud_cover_pct"],
                wind_speed_kmh=day_wx["wind_speed_kmh"],
                solunar_rating=solunar_rating,
                days_since_stocking=days_since,
                score_date=target_date,
            )
            day_scores.append(score)

        forecast[loc.id] = day_scores

    return forecast


def best_bets_weekend() -> str:
    """Find the best fishing spots for the upcoming weekend.

    Runs the forecast, extracts Saturday and Sunday scores, ranks them,
    and returns a formatted text summary suitable for newsletters or
    Reddit posts.
    """
    today = date.today()

    # Find next Saturday (weekday 5) and Sunday (weekday 6)
    days_until_saturday = (5 - today.weekday()) % 7
    if days_until_saturday == 0 and today.weekday() == 5:
        days_until_saturday = 0  # today is Saturday
    elif days_until_saturday == 0:
        days_until_saturday = 7
    saturday = today + timedelta(days=days_until_saturday)
    sunday = saturday + timedelta(days=1)

    # We need enough forecast days to reach Sunday
    forecast_days = (sunday - today).days + 1
    forecast = run_forecast(days=forecast_days)

    # Extract Saturday and Sunday scores
    sat_scores: list[FishingScore] = []
    sun_scores: list[FishingScore] = []
    for loc_id, day_scores in forecast.items():
        for score in day_scores:
            if score.score_date == saturday:
                sat_scores.append(score)
            elif score.score_date == sunday:
                sun_scores.append(score)

    sat_scores.sort(key=lambda s: s.total, reverse=True)
    sun_scores.sort(key=lambda s: s.total, reverse=True)

    # Format output
    lines: list[str] = []
    lines.append("")
    lines.append("=" * 60)
    lines.append(
        f"  BEST BETS THIS WEEKEND -- {saturday.strftime('%b %d')} - {sunday.strftime('%b %d')}"
    )
    lines.append("=" * 60)

    lines.append(f"\n  SATURDAY ({saturday.strftime('%b %d')}):")
    for i, s in enumerate(sat_scores[:5], 1):
        lines.append(f"    {i}. {s.location_name} -- {s.total} ({s.label})")
        lines.append(
            f"       Temp:{s.water_temp_score:2d} Flow:{s.flow_score:2d} "
            f"Wx:{s.weather_score:2d} Sol:{s.solunar_score:2d} "
            f"Stock:{s.stocking_score:2d}"
        )

    lines.append(f"\n  SUNDAY ({sunday.strftime('%b %d')}):")
    for i, s in enumerate(sun_scores[:5], 1):
        lines.append(f"    {i}. {s.location_name} -- {s.total} ({s.label})")
        lines.append(
            f"       Temp:{s.water_temp_score:2d} Flow:{s.flow_score:2d} "
            f"Wx:{s.weather_score:2d} Sol:{s.solunar_score:2d} "
            f"Stock:{s.stocking_score:2d}"
        )

    # Top pick across both days
    all_weekend = sat_scores + sun_scores
    if all_weekend:
        top = max(all_weekend, key=lambda s: s.total)
        day_name = "Saturday" if top.score_date == saturday else "Sunday"
        lines.append(f"\n  TOP PICK: {top.location_name} on {day_name} ({top.total})")

    lines.append("=" * 60)
    lines.append("")

    return "\n".join(lines)


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
    parser.add_argument(
        "--best-bets",
        action="store_true",
        help="Print weekend best-bets summary and exit",
    )
    parser.add_argument(
        "--forecast",
        type=int,
        metavar="DAYS",
        help="Print N-day forecast scores and exit",
    )
    args = parser.parse_args()

    if args.best_bets:
        print(best_bets_weekend())
    elif args.forecast:
        forecast = run_forecast(days=args.forecast)
        today = date.today()
        print("\n" + "=" * 70)
        print(f"  {args.forecast}-DAY FORECAST")
        print("=" * 70)
        for loc in MVP_WATERS:
            day_scores = forecast.get(loc.id, [])
            scores_str = "  ".join(
                f"{s.score_date.strftime('%a'):>3s}:{s.total:2d}" for s in day_scores
            )
            print(f"  {loc.name:<40s}  {scores_str}")
        print("=" * 70 + "\n")
    else:
        scores = run_pipeline(dry_run=args.dry_run)
        print_scores(scores)
