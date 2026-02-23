# CO Fishing Conditions

A Colorado-focused fishing conditions app that aggregates public government and weather data to score fishing locations on a 0–100 scale. It pulls real-time streamflow, water temperature, weather forecasts, CPW stocking reports, and solunar data to help anglers decide where to fish.

## Data Sources

- **USGS Water Services API** — real-time streamflow (CFS), water temperature, and gage height
- **CPW Stocking Reports** — Colorado Parks & Wildlife weekly stocking data (scraped)
- **Open-Meteo Weather API** — hourly forecasts (pressure, cloud cover, wind)
- **Solunar Calculations** — moon phase and feeding windows (computed locally with `ephem`)

## Scoring

Each location receives a composite score (0–100) built from five equally weighted components:

| Component | Range | What it measures |
|---|---|---|
| Water Temperature | 0–20 | Proximity to ideal trout range (50–62 °F) |
| Flow | 0–20 | Current CFS vs. historical median |
| Weather | 0–20 | Barometric pressure trend, cloud cover, wind |
| Solunar | 0–20 | Moon phase alignment with feeding windows |
| Stocking | 0–20 | Recency of CPW stocking events |

Score labels: **Epic** (80–100), **Good** (60–79), **Fair** (40–59), **Tough** (20–39), **Poor** (0–19).

## Prerequisites

- Python 3.10+
- Docker & Docker Compose (recommended) **or** a local PostgreSQL install with the PostGIS extension

## Running Locally

### Option A — Docker (recommended)

```bash
docker-compose up
```

This starts PostgreSQL + PostGIS, initializes the database schema, runs the scoring pipeline, and launches the Streamlit dashboard at **http://localhost:8501**.

### Option B — Without Docker

1. Install dependencies:

   ```bash
   pip install -e ".[dev,app]"
   ```

2. Start PostgreSQL with PostGIS enabled and set the connection string:

   ```bash
   export DATABASE_URL=postgresql://fishing:fishing_dev@localhost:5432/fishing
   ```

3. Run the pipeline:

   ```bash
   python -m pipeline            # fetch data, score, and store
   python -m pipeline --dry-run  # print scores without writing to the database
   ```

4. Start the dashboard:

   ```bash
   streamlit run src/app/dashboard.py
   ```

   Open **http://localhost:8501** in your browser.

## Running Tests

```bash
pytest tests/                  # all tests
pytest --cov=src tests/        # with coverage
```

## Project Structure

```
src/
├── pipeline.py              # Main orchestrator (fetch → score → store)
├── app/
│   └── dashboard.py         # Streamlit dashboard (leaderboard, map, detail)
├── ingest/                  # Data ingestion clients (USGS, CPW, weather)
├── locations/
│   └── colorado_waters.py   # Registry of MVP fishing locations
├── scoring/
│   ├── engine.py            # Composite score orchestrator
│   └── scorers.py           # Individual scoring functions
├── solunar/
│   └── calculator.py        # Moon phase & feeding window calculations
└── storage/
    ├── db.py                # PostgreSQL access layer
    ├── models.py            # Domain dataclasses
    └── schema.sql           # Database DDL
```
