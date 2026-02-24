"""PostgreSQL + PostGIS database access layer.

Provides a ``FishingDB`` class that handles connection management,
schema initialisation, and CRUD operations for all domain objects.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import psycopg2
import psycopg2.extras

from storage.models import FishingLocation, FishingScore, StockingEvent

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")

_DEFAULT_DSN = os.getenv(
    "DATABASE_URL",
    "postgresql://fishing:fishing_dev@localhost:5432/fishing",
)


class FishingDB:
    """Thin wrapper around PostgreSQL for the fishing conditions pipeline."""

    def __init__(self, dsn: str | None = None) -> None:
        self.dsn = dsn or _DEFAULT_DSN
        self.conn = psycopg2.connect(self.dsn)
        self.conn.autocommit = True

    def close(self) -> None:
        self.conn.close()

    # -- schema --------------------------------------------------------------

    def init_schema(self) -> None:
        """Run the DDL from schema.sql to create tables if they don't exist."""
        sql = _SCHEMA_PATH.read_text()
        with self.conn.cursor() as cur:
            cur.execute(sql)

    # -- locations -----------------------------------------------------------

    def upsert_locations(self, locations: list[FishingLocation]) -> int:
        """Insert or update location rows, including PostGIS geometry."""
        sql = """
            INSERT INTO locations (id, name, water_type, usgs_site_code,
                                   is_gold_medal, region, elevation_ft, geom)
            VALUES (%(id)s, %(name)s, %(water_type)s, %(usgs_site_code)s,
                    %(is_gold_medal)s, %(region)s, %(elevation_ft)s,
                    ST_SetSRID(ST_MakePoint(%(longitude)s, %(latitude)s), 4326))
            ON CONFLICT (id) DO UPDATE SET
                name           = EXCLUDED.name,
                water_type     = EXCLUDED.water_type,
                usgs_site_code = EXCLUDED.usgs_site_code,
                is_gold_medal  = EXCLUDED.is_gold_medal,
                region         = EXCLUDED.region,
                elevation_ft   = EXCLUDED.elevation_ft,
                geom           = EXCLUDED.geom
        """
        rows = []
        for loc in locations:
            rows.append(
                {
                    "id": loc.id,
                    "name": loc.name,
                    "water_type": loc.water_type,
                    "usgs_site_code": loc.usgs_site_code,
                    "is_gold_medal": loc.is_gold_medal,
                    "region": loc.region,
                    "elevation_ft": loc.elevation_ft,
                    "latitude": loc.latitude,
                    "longitude": loc.longitude,
                }
            )
        with self.conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, sql, rows)
        return len(rows)

    # -- water observations --------------------------------------------------

    def save_water_observations(self, location_id: str, df: pd.DataFrame) -> int:
        """Upsert water observation rows from a USGS DataFrame.

        Expects columns: parameter_code, datetime, value, unit.
        """
        if df.empty:
            return 0

        sql = """
            INSERT INTO water_observations (location_id, observed_at, parameter_code, value, unit)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (location_id, parameter_code, observed_at) DO UPDATE SET
                value = EXCLUDED.value,
                unit  = EXCLUDED.unit
        """
        rows = [
            (location_id, row["datetime"], row["parameter_code"], row["value"], row["unit"])
            for _, row in df.iterrows()
        ]
        with self.conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, sql, rows)
        return len(rows)

    def get_latest_water_data(self, location_id: str, hours: int = 24) -> pd.DataFrame:
        """Return recent water observations for a location."""
        sql = """
            SELECT parameter_code, observed_at, value, unit
            FROM water_observations
            WHERE location_id = %s
              AND observed_at >= NOW() - INTERVAL '%s hours'
            ORDER BY observed_at DESC
        """
        return pd.read_sql(sql, self.conn, params=(location_id, hours))

    # -- weather forecasts ---------------------------------------------------

    def save_weather_forecast(self, location_id: str, df: pd.DataFrame) -> int:
        """Upsert hourly weather forecast rows.

        Expects columns: datetime, temperature_c, pressure_hpa,
        cloud_cover_pct, wind_speed_kmh, precipitation_mm.
        """
        if df.empty:
            return 0

        sql = """
            INSERT INTO weather_forecasts
                (location_id, forecast_hour, temperature_c, pressure_hpa,
                 cloud_cover_pct, wind_speed_kmh, precipitation_mm)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (location_id, forecast_hour) DO UPDATE SET
                temperature_c    = EXCLUDED.temperature_c,
                pressure_hpa     = EXCLUDED.pressure_hpa,
                cloud_cover_pct  = EXCLUDED.cloud_cover_pct,
                wind_speed_kmh   = EXCLUDED.wind_speed_kmh,
                precipitation_mm = EXCLUDED.precipitation_mm,
                fetched_at       = NOW()
        """
        rows = [
            (
                location_id,
                row["datetime"],
                row["temperature_c"],
                row["pressure_hpa"],
                row["cloud_cover_pct"],
                row["wind_speed_kmh"],
                row["precipitation_mm"],
            )
            for _, row in df.iterrows()
        ]
        with self.conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, sql, rows)
        return len(rows)

    def get_latest_weather(self, location_id: str) -> pd.DataFrame:
        """Return the most recent forecast for a location."""
        sql = """
            SELECT forecast_hour, temperature_c, pressure_hpa,
                   cloud_cover_pct, wind_speed_kmh, precipitation_mm
            FROM weather_forecasts
            WHERE location_id = %s
              AND forecast_hour >= NOW() - INTERVAL '6 hours'
            ORDER BY forecast_hour DESC
        """
        return pd.read_sql(sql, self.conn, params=(location_id,))

    # -- stocking events -----------------------------------------------------

    def save_stocking_events(self, events: list[StockingEvent]) -> int:
        """Insert stocking events (skips duplicates by water_name + date)."""
        if not events:
            return 0

        sql = """
            INSERT INTO stocking_events (location_id, water_name, stocking_date, species, quantity)
            SELECT %(location_id)s, %(water_name)s, %(stocking_date)s, %(species)s, %(quantity)s
            WHERE NOT EXISTS (
                SELECT 1 FROM stocking_events
                WHERE water_name = %(water_name)s
                  AND stocking_date = %(stocking_date)s
                  AND species = %(species)s
            )
        """
        rows = [
            {
                "location_id": e.location_id,
                "water_name": e.water_name,
                "stocking_date": e.stocking_date,
                "species": e.species,
                "quantity": e.quantity,
            }
            for e in events
        ]
        with self.conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, sql, rows)
        return len(rows)

    def get_recent_stockings(self, days: int = 14) -> pd.DataFrame:
        """Return stocking events from the last N days."""
        sql = """
            SELECT location_id, water_name, stocking_date, species, quantity
            FROM stocking_events
            WHERE stocking_date >= CURRENT_DATE - %s
            ORDER BY stocking_date DESC
        """
        return pd.read_sql(sql, self.conn, params=(days,))

    # -- daily flow statistics -----------------------------------------------

    def save_daily_flow_stats(self, df: pd.DataFrame) -> int:
        """Upsert daily flow statistics from the USGS Statistics Service.

        Expects columns: site_code, month_nu, day_nu, median_cfs.
        """
        if df.empty:
            return 0

        sql = """
            INSERT INTO daily_flow_stats (usgs_site_code, month_nu, day_nu, median_cfs)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (usgs_site_code, month_nu, day_nu) DO UPDATE SET
                median_cfs = EXCLUDED.median_cfs,
                fetched_at = NOW()
        """
        rows = [
            (row["site_code"], int(row["month_nu"]), int(row["day_nu"]), float(row["median_cfs"]))
            for _, row in df.iterrows()
        ]
        with self.conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, sql, rows)
        return len(rows)

    def get_median_flow(self, usgs_site_code: str, month: int, day: int) -> float | None:
        """Look up the cached historical median flow for a site and day-of-year."""
        sql = """
            SELECT median_cfs FROM daily_flow_stats
            WHERE usgs_site_code = %s AND month_nu = %s AND day_nu = %s
        """
        with self.conn.cursor() as cur:
            cur.execute(sql, (usgs_site_code, month, day))
            row = cur.fetchone()
        return float(row[0]) if row else None

    def has_flow_stats(self, usgs_site_code: str) -> bool:
        """Check whether daily flow stats are cached for a site."""
        sql = """
            SELECT EXISTS(
                SELECT 1 FROM daily_flow_stats WHERE usgs_site_code = %s
            )
        """
        with self.conn.cursor() as cur:
            cur.execute(sql, (usgs_site_code,))
            return cur.fetchone()[0]

    # -- fishing scores ------------------------------------------------------

    def save_scores(self, scores: list[FishingScore]) -> int:
        """Upsert computed fishing scores."""
        if not scores:
            return 0

        sql = """
            INSERT INTO fishing_scores
                (location_id, score_date, total, label,
                 water_temp_score, flow_score, weather_score,
                 solunar_score, stocking_score)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (location_id, score_date) DO UPDATE SET
                total            = EXCLUDED.total,
                label            = EXCLUDED.label,
                water_temp_score = EXCLUDED.water_temp_score,
                flow_score       = EXCLUDED.flow_score,
                weather_score    = EXCLUDED.weather_score,
                solunar_score    = EXCLUDED.solunar_score,
                stocking_score   = EXCLUDED.stocking_score,
                computed_at      = NOW()
        """
        rows = [
            (
                s.location_id,
                s.score_date,
                s.total,
                s.label,
                s.water_temp_score,
                s.flow_score,
                s.weather_score,
                s.solunar_score,
                s.stocking_score,
            )
            for s in scores
        ]
        with self.conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, sql, rows)
        return len(rows)

    def get_current_scores(self) -> pd.DataFrame:
        """Return the latest scores for all locations."""
        sql = """
            SELECT s.location_id, l.name AS location_name, s.score_date,
                   s.total, s.label,
                   s.water_temp_score, s.flow_score, s.weather_score,
                   s.solunar_score, s.stocking_score,
                   s.computed_at
            FROM fishing_scores s
            JOIN locations l ON l.id = s.location_id
            WHERE s.score_date = CURRENT_DATE
            ORDER BY s.total DESC
        """
        return pd.read_sql(sql, self.conn)

    def get_location_history(self, location_id: str, days: int = 7) -> pd.DataFrame:
        """Return score history for a single location."""
        sql = """
            SELECT score_date, total, label,
                   water_temp_score, flow_score, weather_score,
                   solunar_score, stocking_score
            FROM fishing_scores
            WHERE location_id = %s
              AND score_date >= CURRENT_DATE - %s
            ORDER BY score_date DESC
        """
        return pd.read_sql(sql, self.conn, params=(location_id, days))
