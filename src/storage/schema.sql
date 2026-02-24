-- Fishing Conditions MVP schema
-- Runs automatically on first docker-compose up via init script

CREATE EXTENSION IF NOT EXISTS postgis;

-- ---------------------------------------------------------------------------
-- Locations
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS locations (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    water_type      TEXT NOT NULL,          -- 'river', 'lake', 'reservoir'
    usgs_site_code  TEXT,
    is_gold_medal   BOOLEAN DEFAULT FALSE,
    region          TEXT DEFAULT '',
    elevation_ft    DOUBLE PRECISION,
    geom            GEOMETRY(Point, 4326)   -- PostGIS point (lon/lat WGS84)
);

CREATE INDEX IF NOT EXISTS idx_locations_geom ON locations USING GIST (geom);

-- ---------------------------------------------------------------------------
-- Water observations (from USGS)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS water_observations (
    location_id     TEXT NOT NULL REFERENCES locations(id),
    observed_at     TIMESTAMPTZ NOT NULL,
    parameter_code  TEXT NOT NULL,           -- '00060', '00010', '00065'
    value           DOUBLE PRECISION,
    unit            TEXT,
    PRIMARY KEY (location_id, parameter_code, observed_at)
);

-- ---------------------------------------------------------------------------
-- Weather forecasts (from Open-Meteo)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS weather_forecasts (
    location_id     TEXT NOT NULL REFERENCES locations(id),
    forecast_hour   TIMESTAMPTZ NOT NULL,
    temperature_c   DOUBLE PRECISION,
    pressure_hpa    DOUBLE PRECISION,
    cloud_cover_pct DOUBLE PRECISION,
    wind_speed_kmh  DOUBLE PRECISION,
    precipitation_mm DOUBLE PRECISION,
    fetched_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (location_id, forecast_hour)
);

-- ---------------------------------------------------------------------------
-- Stocking events (from CPW)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stocking_events (
    id              SERIAL PRIMARY KEY,
    location_id     TEXT REFERENCES locations(id),
    water_name      TEXT NOT NULL,
    stocking_date   DATE NOT NULL,
    species         TEXT NOT NULL,
    quantity        INTEGER
);

CREATE INDEX IF NOT EXISTS idx_stocking_date ON stocking_events (stocking_date);

-- ---------------------------------------------------------------------------
-- Daily flow statistics (from USGS Statistics Service)
-- Historical median (p50) streamflow by day-of-year, cached locally.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS daily_flow_stats (
    usgs_site_code  TEXT NOT NULL,
    month_nu        SMALLINT NOT NULL,          -- 1-12
    day_nu          SMALLINT NOT NULL,           -- 1-31
    median_cfs      DOUBLE PRECISION NOT NULL,
    fetched_at      TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (usgs_site_code, month_nu, day_nu)
);

-- ---------------------------------------------------------------------------
-- Fishing scores (computed by scoring engine)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fishing_scores (
    location_id         TEXT NOT NULL REFERENCES locations(id),
    score_date          DATE NOT NULL,
    total               INTEGER NOT NULL,
    label               TEXT NOT NULL,
    water_temp_score    INTEGER NOT NULL,
    flow_score          INTEGER NOT NULL,
    weather_score       INTEGER NOT NULL,
    solunar_score       INTEGER NOT NULL,
    stocking_score      INTEGER NOT NULL,
    computed_at         TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (location_id, score_date)
);
