"""Curated registry of MVP Colorado fishing locations.

Contains the 15+ waters targeted for the Phase 1 MVP, each with
coordinates, USGS gauge site code (if available), and metadata.
"""

from __future__ import annotations

from storage.models import FishingLocation

# ---------------------------------------------------------------------------
# MVP Waters — Near Colorado Springs
# ---------------------------------------------------------------------------

_FOUNTAIN_CREEK = FishingLocation(
    id="fountain-creek-cos",
    name="Fountain Creek at Colorado Springs",
    latitude=38.8339,
    longitude=-104.8253,
    water_type="river",
    usgs_site_code="07105500",
    region="Colorado Springs",
    historical_median_cfs=25.0,
)

_ELEVEN_MILE = FishingLocation(
    id="eleven-mile-reservoir",
    name="Eleven Mile Reservoir",
    latitude=38.9361,
    longitude=-105.5031,
    water_type="reservoir",
    usgs_site_code="06696980",  # S Platte R below Eleven Mile Canyon
    is_gold_medal=False,
    region="Colorado Springs",
    historical_median_cfs=150.0,
)

_SPINNEY_MOUNTAIN = FishingLocation(
    id="spinney-mountain-reservoir",
    name="Spinney Mountain Reservoir",
    latitude=38.9811,
    longitude=-105.5200,
    water_type="reservoir",
    usgs_site_code="06695000",  # S Platte R at Hartsel
    is_gold_medal=False,
    region="Colorado Springs",
    historical_median_cfs=75.0,
)

_NORTH_CATAMOUNT = FishingLocation(
    id="north-catamount-reservoir",
    name="North Catamount Reservoir",
    latitude=38.8275,
    longitude=-105.0000,
    water_type="reservoir",
    usgs_site_code=None,
    region="Colorado Springs",
    elevation_ft=9170.0,
)

_SOUTH_CATAMOUNT = FishingLocation(
    id="south-catamount-reservoir",
    name="South Catamount Reservoir",
    latitude=38.8108,
    longitude=-104.9942,
    water_type="reservoir",
    usgs_site_code=None,
    region="Colorado Springs",
    elevation_ft=9160.0,
)

_RAMPART_RESERVOIR = FishingLocation(
    id="rampart-reservoir",
    name="Rampart Reservoir",
    latitude=38.9167,
    longitude=-105.0833,
    water_type="reservoir",
    usgs_site_code=None,
    region="Colorado Springs",
    elevation_ft=9100.0,
)

_MONUMENT_LAKE = FishingLocation(
    id="monument-lake",
    name="Monument Lake",
    latitude=37.4081,
    longitude=-104.8831,
    water_type="lake",
    usgs_site_code=None,
    region="Colorado Springs",
    elevation_ft=8000.0,
)

_PUEBLO_RESERVOIR = FishingLocation(
    id="pueblo-reservoir",
    name="Pueblo Reservoir",
    latitude=38.2586,
    longitude=-104.8633,
    water_type="reservoir",
    usgs_site_code="07099400",  # Arkansas R above Pueblo
    region="Colorado Springs",
    historical_median_cfs=300.0,
)

# ---------------------------------------------------------------------------
# Popular Statewide — Gold Medal & High-Traffic Waters
# ---------------------------------------------------------------------------

_CHEESMAN_CANYON = FishingLocation(
    id="south-platte-cheesman",
    name="South Platte River — Cheesman Canyon",
    latitude=39.2203,
    longitude=-105.2858,
    water_type="river",
    usgs_site_code="06701900",  # S Platte R at Trumbull
    is_gold_medal=True,
    region="Front Range",
    historical_median_cfs=200.0,
)

_ARKANSAS_SALIDA = FishingLocation(
    id="arkansas-river-salida",
    name="Arkansas River at Salida",
    latitude=38.5347,
    longitude=-106.0047,
    water_type="river",
    usgs_site_code="07091200",  # Arkansas R near Nathrop
    is_gold_medal=True,
    region="Central Mountains",
    historical_median_cfs=450.0,
)

_ARKANSAS_BV = FishingLocation(
    id="arkansas-river-buena-vista",
    name="Arkansas River at Buena Vista",
    latitude=38.8422,
    longitude=-106.1311,
    water_type="river",
    usgs_site_code="07087200",  # Arkansas R at Buena Vista
    is_gold_medal=True,
    region="Central Mountains",
    historical_median_cfs=350.0,
)

_BLUE_RIVER = FishingLocation(
    id="blue-river-silverthorne",
    name="Blue River below Dillon Reservoir",
    latitude=39.6339,
    longitude=-106.0739,
    water_type="river",
    usgs_site_code="09050700",  # Blue R below Dillon
    is_gold_medal=True,
    region="Summit County",
    historical_median_cfs=180.0,
)

_FRYING_PAN = FishingLocation(
    id="frying-pan-river",
    name="Frying Pan River below Ruedi Reservoir",
    latitude=39.3608,
    longitude=-106.8242,
    water_type="river",
    usgs_site_code="09080400",  # Frying Pan R at Basalt
    is_gold_medal=True,
    region="Roaring Fork Valley",
    historical_median_cfs=100.0,
)

_HORSETOOTH = FishingLocation(
    id="horsetooth-reservoir",
    name="Horsetooth Reservoir",
    latitude=40.5481,
    longitude=-105.1739,
    water_type="reservoir",
    usgs_site_code=None,
    region="Front Range",
    elevation_ft=5430.0,
)

_CHATFIELD = FishingLocation(
    id="chatfield-reservoir",
    name="Chatfield Reservoir",
    latitude=39.5331,
    longitude=-105.0733,
    water_type="reservoir",
    usgs_site_code="06711565",  # S Platte R at Chatfield
    region="Denver Metro",
    historical_median_cfs=350.0,
)

# ---------------------------------------------------------------------------
# Public registry
# ---------------------------------------------------------------------------

MVP_WATERS: list[FishingLocation] = [
    # Near Colorado Springs
    _FOUNTAIN_CREEK,
    _ELEVEN_MILE,
    _SPINNEY_MOUNTAIN,
    _NORTH_CATAMOUNT,
    _SOUTH_CATAMOUNT,
    _RAMPART_RESERVOIR,
    _MONUMENT_LAKE,
    _PUEBLO_RESERVOIR,
    # Popular statewide
    _CHEESMAN_CANYON,
    _ARKANSAS_SALIDA,
    _ARKANSAS_BV,
    _BLUE_RIVER,
    _FRYING_PAN,
    _HORSETOOTH,
    _CHATFIELD,
]


def get_location(location_id: str) -> FishingLocation | None:
    """Look up a location by its slug ID."""
    for loc in MVP_WATERS:
        if loc.id == location_id:
            return loc
    return None


def get_locations_with_gauge() -> list[FishingLocation]:
    """Return only locations that have a USGS gauge site code."""
    return [loc for loc in MVP_WATERS if loc.usgs_site_code is not None]
