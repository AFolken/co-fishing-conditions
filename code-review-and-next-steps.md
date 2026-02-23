# CO Fishing Conditions — Code Review & Next Steps

## Overall Assessment

This is impressive work. The codebase is clean, well-organized, and demonstrates strong software engineering fundamentals — separation of concerns, proper data modeling, good test coverage, Docker-ready deployment. You're well past "proof of concept" and into "real product" territory. Here's what I'd focus on to take it from good to great.

---

## Code Quality Highlights (What's Working Well)

- **Clean architecture** — ingestion, scoring, storage, and presentation are properly separated
- **Solid data models** — `FishingLocation`, `FishingScore`, `StockingEvent` as frozen/typed dataclasses
- **Good test coverage** — 6 test files covering all core modules with fixtures, parameterized tests, and mock-based API tests
- **Graceful degradation** — missing data defaults to neutral scores (10/20) rather than crashing
- **Proper USGS handling** — sentinel value (-999999) → NaN, UTC datetime parsing, qualifier extraction
- **Well-structured DB layer** — PostGIS-enabled schema with upserts, proper indexes, and constraint handling

---

## Priority 1: Bugs & Issues to Fix Now

### 1A. Flow score always returns neutral (10) in production
**This is your biggest bug.** In `pipeline.py`, `compute_score()` is called without `historical_median_cfs`, so `score_flow()` always gets `None` for the historical baseline and returns 10 (neutral). You're never actually scoring flow conditions.

**Fix:** You need historical median flow data. Options:
- **Quick fix:** Add a `historical_median_cfs` field to `FishingLocation` and hardcode approximate medians for your MVP waters (you can pull these from USGS statistics service)
- **Better fix:** Use the USGS Statistics Service API (`https://waterservices.usgs.gov/nwis/stat/`) to fetch daily median flow by day-of-year for each gauge, store in your DB, and look up dynamically

### 1B. Arkansas River at Buena Vista has wrong gauge
`_ARKANSAS_BV` uses gauge `07087050` (Arkansas R below Pueblo Reservoir), which is ~100 miles downstream from Buena Vista. The correct gauge for BV is likely `07081200` (Arkansas R near Leadville/BV area). Verify the exact site code on the USGS mapper.

### 1C. Docker Compose doesn't launch the dashboard
The app service command is `python -m pipeline` — this runs the pipeline and exits. It never starts Streamlit. Change to:
```yaml
command: >
  bash -c "python -m pipeline && streamlit run src/app/dashboard.py --server.address=0.0.0.0"
```

### 1D. Empty directories in repo
`src/analyze/`, `src/process/`, `src/visualize/` are empty with no `__init__.py`. Either add placeholder code or remove them — empty dirs look like forgotten scaffolding.

---

## Priority 2: Scoring Algorithm Refinements

### 2A. Add air temperature proxy when water temp is missing
Your plan doc mentions this, but it's not implemented. Most reservoirs without gauges (Catamounts, Rampart, Monument Lake, Horsetooth) will always get neutral temp scores. Add a simple thermal lag model:

```python
def estimate_water_temp_from_air(air_temp_c: float, elevation_ft: float) -> float:
    """Rough estimate: water temp lags air temp by ~3-5°C and
    varies by elevation. Better than returning neutral."""
    lag = 4.0  # °C — water is cooler than air
    elevation_adjustment = (elevation_ft - 6000) * 0.001  # slight cooling at altitude
    return air_temp_c - lag - elevation_adjustment
```

### 2B. Solunar scoring has a discontinuity
The intermediate phase scoring uses `proximity = 1.0 - abs(illum - 0.5) * 2`, which means proximity is 1.0 at both new (illum≈0) and full (illum≈1.0) — but the math is: `1.0 - abs(0.0 - 0.5) * 2 = 0.0` for new moon. The formula gives proximity 0 at new/full and 1 at quarters — the opposite of intended.

**Fix:**
```python
# Proximity to new OR full moon (both are high-activity)
proximity = min(illum, 1.0 - illum) * 2  # 0 at new/full, 1 at quarters
proximity = 1.0 - proximity  # invert: 1 at new/full, 0 at quarters
```

### 2C. Weather score can exceed 20 in edge cases
`score_weather` adds cloud (+2) and wind (+1) modifiers to the pressure base (max 20). With `falling_steady` (20) + overcast (2) + good wind (1) = 23, clamped to 20. This is technically correct due to `min(20, ...)`, but it means cloud cover and wind are irrelevant when pressure is already "falling_steady." Consider making the base scores top out at 17 so modifiers always matter.

### 2D. Stocking score penalizes wild-fish waters
Waters that are never stocked (most Gold Medal rivers) max out at 15 with the Gold Medal bonus. Meanwhile, a stocked reservoir gets 20. This means Gold Medal waters like Cheesman Canyon or the Frying Pan are structurally disadvantaged in scoring vs. stocked put-and-take lakes, which doesn't match fishing reality.

**Fix:** For rivers with no stocking data and `water_type == "river"`, consider a "wild fishery" base of 12-14 rather than 5, so the stocking component doesn't drag down inherently productive waters.

---

## Priority 3: Features That Will Make or Break Adoption

### 3A. 7-day forecast view
Your weather client already fetches 7-day forecasts, and solunar data can be computed for any date. Add a "This Week" view to the dashboard showing projected scores for each of the next 7 days. This is the killer feature — it answers the question "Should I go Saturday or Sunday?"

### 3B. The "Best Bets This Weekend" output
Add a simple function that runs the pipeline for Saturday and Sunday, ranks the results, and produces a text/HTML summary. This becomes your weekly newsletter content and your Reddit post template.

### 3C. CPW stocking name matching is fragile
The static `_NAME_TO_LOCATION_ID` dict only covers 10 waters. CPW reports include many more. Consider fuzzy matching (using `difflib.get_close_matches`) as a fallback, and log unmatched water names so you can expand the mapping over time.

### 3D. Store raw data, not just scores
Currently the pipeline computes scores from live API calls every time. Consider also persisting the raw water observations and weather data to your DB (you already have the schema and methods in `db.py` — `save_water_observations`, `save_weather_forecast`, `save_stocking_events`). This gives you:
- Historical trend charts (flow over last 7 days)
- The ability to backtest scoring algorithm changes
- Data for the "this lake usually fishes best in early June" patterns

---

## Priority 4: Dashboard Polish for Launch

### 4A. Add real-time conditions to the detail page
The Location Detail page shows score breakdown but not the actual conditions. Add: current water temp (°F), current flow (cfs), last stocked date, pressure trend, moon phase. These are the numbers anglers care about — the score is a summary, but they want to see the raw data too.

### 4B. Map should be the default view
When sharing on Reddit, the map with color-coded dots is your visual hook. Make it the landing page instead of the leaderboard, or combine them — map on top, ranked list below.

### 4C. Add a "Last Updated" timestamp
Show when the data was last fetched. Anglers need to trust that the data is current.

### 4D. Mobile responsiveness
`layout="wide"` in Streamlit can break on mobile. Since most anglers will check this on their phones, test the mobile Streamlit rendering and consider using `st.columns` sparingly.

---

## Priority 5: Infrastructure & Deployment

### 5A. Deploy to Streamlit Community Cloud (free)
This is the fastest path to a shareable URL. Push your repo, connect it to streamlit.io, and you'll have a live link. You'll need a `requirements.txt` or the `pyproject.toml` for it to pick up dependencies. Note: you won't have PostgreSQL on Streamlit Cloud, so the dry-run pipeline (fetching live from APIs each time) is actually your best option for an MVP launch.

### 5B. Add retry logic to API clients
USGS and Open-Meteo occasionally return 5xx errors. Add `requests.adapters.HTTPAdapter` with `Retry` to your sessions:
```python
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
self.session.mount("https://", HTTPAdapter(max_retries=retry))
```

### 5C. Add rate limiting for USGS
You're hitting the USGS API once per location (15 locations × daily). That's fine now, but if you expand to 50+ waters running every 15 minutes, you'll want to batch requests. The USGS API supports comma-separated site codes: `sites=07105500,06696980,06695000`.

---

## Priority 6: Cleanup

- Remove `src/analyze/`, `src/process/`, `src/visualize/` empty directories
- Remove `src/co_fishing_conditions.egg-info/` from version control (add to `.gitignore`)
- Remove `__pycache__/` directories from the repo (add `__pycache__/` and `*.pyc` to `.gitignore`)
- The `label_score()` function in `engine.py` duplicates the `FishingScore.label` property — remove the standalone function

---

## Suggested Roadmap (Next 4 Weekends)

| Weekend | Focus | Goal |
|---------|-------|------|
| 1 | Fix flow scoring (1A), add historical medians, fix BV gauge (1B), fix Docker (1C) | Pipeline produces accurate, meaningful scores |
| 2 | Add 7-day forecast, air temp proxy (2A), improve detail page (4A) | Dashboard answers "when should I go this week?" |
| 3 | Deploy to Streamlit Cloud, add retry logic, polish mobile view | Live URL you can share |
| 4 | Write "Best Bets" post, share on r/COFishing and Facebook groups, collect feedback | First real users |
