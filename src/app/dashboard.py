"""Streamlit dashboard for Colorado Fishing Conditions.

Five views:
  1. Leaderboard — ranked table of all locations with scores
  2. Map — folium map with color-coded markers
  3. Location Detail — score breakdown, charts, and conditions
  4. This Week — 7-day forecast grid (locations x days)
  5. Best Bets — top picks for the upcoming weekend

Run with:
    streamlit run src/app/dashboard.py
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

# Ensure src/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from locations.colorado_waters import MVP_WATERS
from pipeline import best_bets_weekend, run_forecast, run_pipeline
from storage.models import FishingScore

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="CO Fishing Conditions",
    page_icon="🎣",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Score colour helpers
# ---------------------------------------------------------------------------

_LABEL_COLORS = {
    "Epic": "#22c55e",
    "Good": "#3b82f6",
    "Fair": "#eab308",
    "Tough": "#f97316",
    "Poor": "#ef4444",
}


def _color_for_label(label: str) -> str:
    return _LABEL_COLORS.get(label, "#888888")


# ---------------------------------------------------------------------------
# Data fetching (cached so we don't re-run the pipeline on every interaction)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=900)  # cache for 15 minutes
def load_scores() -> list[dict]:
    """Run the pipeline in dry-run mode and return scores as dicts."""
    scores = run_pipeline(dry_run=True)
    return [
        {
            "location_id": s.location_id,
            "location_name": s.location_name,
            "total": s.total,
            "label": s.label,
            "water_temp_score": s.water_temp_score,
            "flow_score": s.flow_score,
            "weather_score": s.weather_score,
            "solunar_score": s.solunar_score,
            "stocking_score": s.stocking_score,
        }
        for s in scores
    ]


@st.cache_data(ttl=900)
def load_forecast() -> dict[str, list[dict]]:
    """Run the 7-day forecast and return scores as serialisable dicts."""
    forecast = run_forecast(days=7)
    result: dict[str, list[dict]] = {}
    for loc_id, day_scores in forecast.items():
        result[loc_id] = [
            {
                "location_id": s.location_id,
                "location_name": s.location_name,
                "score_date": s.score_date.isoformat(),
                "total": s.total,
                "label": s.label,
                "water_temp_score": s.water_temp_score,
                "flow_score": s.flow_score,
                "weather_score": s.weather_score,
                "solunar_score": s.solunar_score,
                "stocking_score": s.stocking_score,
            }
            for s in day_scores
        ]
    return result


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

st.sidebar.title("CO Fishing Conditions")
page = st.sidebar.radio(
    "Navigate",
    ["Leaderboard", "Map", "Location Detail", "This Week", "Best Bets"],
)
st.sidebar.markdown("---")
st.sidebar.caption("Data: USGS, CPW, Open-Meteo, Solunar")

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

with st.spinner("Fetching conditions..."):
    scores_data = load_scores()

# ---------------------------------------------------------------------------
# Page: Leaderboard
# ---------------------------------------------------------------------------

if page == "Leaderboard":
    st.title("Today's Best Fishing — Colorado")
    st.markdown("Ranked by composite score (0-100). Higher is better.")

    for s in scores_data:
        color = _color_for_label(s["label"])
        col1, col2, col3 = st.columns([1, 4, 3])
        with col1:
            st.markdown(
                f"<h2 style='color:{color}; margin:0'>{s['total']}</h2>",
                unsafe_allow_html=True,
            )
        with col2:
            st.markdown(f"**{s['location_name']}**")
            st.caption(f"{s['label']}")
        with col3:
            st.markdown(
                f"Temp: **{s['water_temp_score']}** | "
                f"Flow: **{s['flow_score']}** | "
                f"Wx: **{s['weather_score']}** | "
                f"Sol: **{s['solunar_score']}** | "
                f"Stock: **{s['stocking_score']}**"
            )
        st.divider()

# ---------------------------------------------------------------------------
# Page: Map
# ---------------------------------------------------------------------------

elif page == "Map":
    st.title("Fishing Conditions Map")

    try:
        import folium
        from streamlit_folium import st_folium

        m = folium.Map(location=[39.0, -105.5], zoom_start=7)

        loc_lookup = {loc.id: loc for loc in MVP_WATERS}
        for s in scores_data:
            loc = loc_lookup.get(s["location_id"])
            if loc is None:
                continue
            color = _color_for_label(s["label"])
            folium.CircleMarker(
                location=[loc.latitude, loc.longitude],
                radius=10 + s["total"] / 10,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.7,
                popup=f"{s['location_name']}: {s['total']} ({s['label']})",
                tooltip=f"{s['location_name']}: {s['total']}",
            ).add_to(m)

        st_folium(m, width=900, height=600)

    except ImportError:
        st.warning(
            "Install `folium` and `streamlit-folium` for map view: "
            "`pip install folium streamlit-folium`"
        )
        # Fallback: simple st.map
        import pandas as pd

        loc_lookup = {loc.id: loc for loc in MVP_WATERS}
        map_data = []
        for s in scores_data:
            loc = loc_lookup.get(s["location_id"])
            if loc:
                map_data.append({"lat": loc.latitude, "lon": loc.longitude})
        if map_data:
            st.map(pd.DataFrame(map_data))

# ---------------------------------------------------------------------------
# Page: Location Detail
# ---------------------------------------------------------------------------

elif page == "Location Detail":
    st.title("Location Detail")

    names = [s["location_name"] for s in scores_data]
    selected = st.selectbox("Select a water body", names)

    score = next((s for s in scores_data if s["location_name"] == selected), None)
    if score is None:
        st.error("Location not found")
    else:
        color = _color_for_label(score["label"])

        st.markdown(
            f"## {score['location_name']} — "
            f"<span style='color:{color}'>{score['total']} ({score['label']})</span>",
            unsafe_allow_html=True,
        )

        st.markdown("### Score Breakdown")
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Water Temp", f"{score['water_temp_score']}/20")
        col2.metric("Flow", f"{score['flow_score']}/20")
        col3.metric("Weather", f"{score['weather_score']}/20")
        col4.metric("Solunar", f"{score['solunar_score']}/20")
        col5.metric("Stocking", f"{score['stocking_score']}/20")

        st.progress(score["total"] / 100)

        # Component bar chart
        import pandas as pd

        components = pd.DataFrame(
            {
                "Component": ["Water Temp", "Flow", "Weather", "Solunar", "Stocking"],
                "Score": [
                    score["water_temp_score"],
                    score["flow_score"],
                    score["weather_score"],
                    score["solunar_score"],
                    score["stocking_score"],
                ],
            }
        )
        st.bar_chart(components, x="Component", y="Score")

# ---------------------------------------------------------------------------
# Page: This Week (7-day forecast)
# ---------------------------------------------------------------------------

elif page == "This Week":
    st.title("This Week's Forecast")
    st.markdown("Projected scores for the next 7 days. Weekend columns are highlighted.")

    with st.spinner("Computing 7-day forecast..."):
        forecast_data = load_forecast()

    if not forecast_data:
        st.warning("No forecast data available.")
    else:
        today = date.today()
        dates = [today + timedelta(days=i) for i in range(7)]
        col_headers = [d.strftime("%a %m/%d") for d in dates]

        # Build a DataFrame: rows = locations, columns = dates
        rows = []
        for loc in MVP_WATERS:
            day_scores = forecast_data.get(loc.id, [])
            row: dict = {"Water": loc.name}
            for i, d in enumerate(dates):
                if i < len(day_scores):
                    row[col_headers[i]] = day_scores[i]["total"]
                else:
                    row[col_headers[i]] = ""
            # Sort key: today's score (first date column)
            row["_sort"] = day_scores[0]["total"] if day_scores else 0
            rows.append(row)

        rows.sort(key=lambda r: r["_sort"], reverse=True)
        for r in rows:
            del r["_sort"]

        df = pd.DataFrame(rows)
        df = df.set_index("Water")

        # Color-code cells based on score labels
        def _score_color(val):
            if not isinstance(val, (int, float)):
                return ""
            if val >= 80:
                return "background-color: #22c55e; color: white"
            if val >= 60:
                return "background-color: #3b82f6; color: white"
            if val >= 40:
                return "background-color: #eab308; color: black"
            if val >= 20:
                return "background-color: #f97316; color: white"
            return "background-color: #ef4444; color: white"

        styled = df.style.map(_score_color)

        # Highlight weekend columns
        weekend_cols = [
            h for h, d in zip(col_headers, dates) if d.weekday() in (5, 6)
        ]
        if weekend_cols:
            styled = styled.set_properties(
                subset=weekend_cols,
                **{"font-weight": "bold"},
            )

        st.dataframe(styled, use_container_width=True, height=600)

        st.caption(
            "Water temp and flow use today's readings (USGS does not forecast). "
            "Weather and solunar scores are projected per day."
        )

# ---------------------------------------------------------------------------
# Page: Best Bets (weekend picks)
# ---------------------------------------------------------------------------

elif page == "Best Bets":
    st.title("Best Bets This Weekend")

    with st.spinner("Computing weekend forecast..."):
        bets_text = best_bets_weekend()

    st.code(bets_text, language=None)
