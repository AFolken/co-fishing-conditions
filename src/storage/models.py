"""Domain data classes shared across all modules.

These define the common vocabulary for locations, observations,
scores, and events used throughout the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True)
class FishingLocation:
    """A fishable water body in Colorado."""

    id: str  # slug, e.g. "fountain-creek-cos"
    name: str  # human-readable, e.g. "Fountain Creek at Colorado Springs"
    latitude: float
    longitude: float
    water_type: str  # "river" | "lake" | "reservoir"
    usgs_site_code: str | None = None
    is_gold_medal: bool = False
    region: str = ""
    elevation_ft: float | None = None
    historical_median_cfs: float | None = None


@dataclass
class WaterConditions:
    """Current or recent water data for a location."""

    location_id: str
    timestamp: datetime
    streamflow_cfs: float | None = None
    water_temp_c: float | None = None
    gage_height_ft: float | None = None


@dataclass
class WeatherConditions:
    """Weather observation or forecast for a location."""

    location_id: str
    timestamp: datetime
    air_temp_c: float
    pressure_hpa: float
    pressure_trend: str  # "falling_steady", "falling_rapid", "stable_low", "stable_high", "rising_steady"
    wind_speed_kmh: float
    cloud_cover_pct: float
    precipitation_mm: float


@dataclass
class SolunarData:
    """Solunar feeding window data for a location and date."""

    location_id: str
    date: date
    moon_phase: str  # "new", "waxing_crescent", "first_quarter", etc.
    moon_illumination: float  # 0.0 - 1.0
    major_periods: list[tuple[datetime, datetime]] = field(default_factory=list)
    minor_periods: list[tuple[datetime, datetime]] = field(default_factory=list)


@dataclass
class StockingEvent:
    """A CPW fish stocking record."""

    water_name: str
    stocking_date: date
    species: str
    location_id: str | None = None  # matched to a FishingLocation, if possible
    quantity: int | None = None


@dataclass
class FishingScore:
    """Composite fishing score for a location at a point in time."""

    location_id: str
    location_name: str
    score_date: date
    water_temp_score: int  # 0-20
    flow_score: int  # 0-20
    weather_score: int  # 0-20
    solunar_score: int  # 0-20
    stocking_score: int  # 0-20
    computed_at: datetime | None = None

    @property
    def total(self) -> int:
        return (
            self.water_temp_score
            + self.flow_score
            + self.weather_score
            + self.solunar_score
            + self.stocking_score
        )

    @property
    def label(self) -> str:
        t = self.total
        if t >= 80:
            return "Epic"
        if t >= 60:
            return "Good"
        if t >= 40:
            return "Fair"
        if t >= 20:
            return "Tough"
        return "Poor"
