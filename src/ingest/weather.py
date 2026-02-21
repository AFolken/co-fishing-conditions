"""Client for the Open-Meteo weather forecast API.

Fetches hourly weather data (temperature, pressure, wind, cloud cover,
precipitation) for a given latitude/longitude and returns clean pandas
DataFrames.

API docs: https://open-meteo.com/en/docs
"""

from __future__ import annotations

import pandas as pd
import requests

# Pressure change thresholds (hPa over 6 hours)
_RAPID_FALL_THRESHOLD = 4.0
_FALL_THRESHOLD = 1.0
_RISE_THRESHOLD = 1.0

# Stable pressure classification boundary
_STABLE_LOW_CEILING = 1013.0  # hPa — below this is "stable_low"


class WeatherClient:
    """Fetches weather forecasts from the Open-Meteo API."""

    BASE_URL = "https://api.open-meteo.com/v1/forecast"

    HOURLY_VARIABLES = [
        "temperature_2m",
        "surface_pressure",
        "cloud_cover",
        "wind_speed_10m",
        "precipitation",
    ]

    DATAFRAME_COLUMNS = [
        "datetime",
        "temperature_c",
        "pressure_hpa",
        "cloud_cover_pct",
        "wind_speed_kmh",
        "precipitation_mm",
    ]

    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {"Accept": "application/json", "User-Agent": "co-fishing-conditions/0.1"}
        )

    # -- low-level API call --------------------------------------------------

    def get_forecast_raw(
        self,
        latitude: float,
        longitude: float,
        forecast_days: int = 7,
        timezone: str = "America/Denver",
    ) -> dict:
        """Fetch the raw JSON response from Open-Meteo.

        Parameters
        ----------
        latitude, longitude : float
            Location coordinates.
        forecast_days : int
            Number of days to forecast (1-16).
        timezone : str
            IANA timezone for timestamps.
        """
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": ",".join(self.HOURLY_VARIABLES),
            "timezone": timezone,
            "forecast_days": forecast_days,
        }
        resp = self.session.get(self.BASE_URL, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    # -- parsing -------------------------------------------------------------

    def parse_forecast(self, raw_json: dict) -> pd.DataFrame:
        """Convert Open-Meteo JSON into a flat DataFrame.

        Returns
        -------
        pd.DataFrame
            One row per hour with columns: datetime, temperature_c,
            pressure_hpa, cloud_cover_pct, wind_speed_kmh, precipitation_mm.
        """
        hourly = raw_json.get("hourly", {})
        times = hourly.get("time", [])
        if not times:
            return pd.DataFrame(columns=self.DATAFRAME_COLUMNS)

        df = pd.DataFrame(
            {
                "datetime": pd.to_datetime(times),
                "temperature_c": hourly.get("temperature_2m", []),
                "pressure_hpa": hourly.get("surface_pressure", []),
                "cloud_cover_pct": hourly.get("cloud_cover", []),
                "wind_speed_kmh": hourly.get("wind_speed_10m", []),
                "precipitation_mm": hourly.get("precipitation", []),
            }
        )
        return df

    # -- convenience wrappers ------------------------------------------------

    def get_forecast(
        self,
        latitude: float,
        longitude: float,
        days: int = 7,
    ) -> pd.DataFrame:
        """Fetch and parse a weather forecast for the given location."""
        raw = self.get_forecast_raw(latitude, longitude, forecast_days=days)
        return self.parse_forecast(raw)

    def get_current_conditions(
        self, latitude: float, longitude: float
    ) -> dict:
        """Return the most recent hourly observation as a dict.

        Keys: temperature_c, pressure_hpa, cloud_cover_pct,
              wind_speed_kmh, precipitation_mm.
        """
        df = self.get_forecast(latitude, longitude, days=1)
        if df.empty:
            return {}

        now = pd.Timestamp.now(tz="America/Denver").tz_localize(None)
        past = df[df["datetime"] <= now]
        row = past.iloc[-1] if not past.empty else df.iloc[0]

        return {
            "temperature_c": row["temperature_c"],
            "pressure_hpa": row["pressure_hpa"],
            "cloud_cover_pct": row["cloud_cover_pct"],
            "wind_speed_kmh": row["wind_speed_kmh"],
            "precipitation_mm": row["precipitation_mm"],
        }

    # -- pressure trend analysis ---------------------------------------------

    @staticmethod
    def compute_pressure_trend(pressures: pd.Series) -> str:
        """Classify the barometric pressure trend over a series of readings.

        The series should cover roughly the last 6 hours of hourly
        pressure readings (in hPa).

        Returns one of: ``"falling_rapid"``, ``"falling_steady"``,
        ``"rising_steady"``, ``"stable_low"``, ``"stable_high"``.
        """
        if pressures.empty or len(pressures) < 2:
            return "stable_high"

        change = float(pressures.iloc[-1] - pressures.iloc[0])

        if change <= -_RAPID_FALL_THRESHOLD:
            return "falling_rapid"
        if change <= -_FALL_THRESHOLD:
            return "falling_steady"
        if change >= _RISE_THRESHOLD:
            return "rising_steady"

        # Stable — classify as low or high based on current reading
        current = float(pressures.iloc[-1])
        if current < _STABLE_LOW_CEILING:
            return "stable_low"
        return "stable_high"
