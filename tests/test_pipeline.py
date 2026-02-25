"""Unit tests for pipeline — forecast, best bets, and raw data persistence."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from ingest.weather import WeatherClient
from pipeline import (
    _extract_daily_weather,
    best_bets_weekend,
    fetch_water_data,
    fetch_weather_data,
    find_days_since_stocking,
    run_forecast,
)
from storage.models import FishingLocation, StockingEvent


# -- Fixtures ----------------------------------------------------------------


@pytest.fixture()
def sample_location() -> FishingLocation:
    return FishingLocation(
        id="test-river",
        name="Test River",
        latitude=38.83,
        longitude=-104.82,
        water_type="river",
        usgs_site_code="07105500",
        historical_median_cfs=100.0,
    )


@pytest.fixture()
def sample_wx_df() -> pd.DataFrame:
    """3-day hourly weather DataFrame for testing."""
    today = date.today()
    rows = []
    for day_offset in range(3):
        d = today + timedelta(days=day_offset)
        for hour in range(24):
            rows.append(
                {
                    "datetime": pd.Timestamp(d) + pd.Timedelta(hours=hour),
                    "temperature_c": 10.0 + hour * 0.5,
                    "pressure_hpa": 1013.0 - day_offset * 2,
                    "cloud_cover_pct": 50.0 + day_offset * 10,
                    "wind_speed_kmh": 8.0,
                    "precipitation_mm": 0.0,
                }
            )
    return pd.DataFrame(rows)


# -- fetch_water_data returns tuple ------------------------------------------


class TestFetchWaterDataReturnsTuple:
    def test_returns_tuple_with_no_gauge(self, sample_location):
        loc = FishingLocation(
            id="no-gauge",
            name="No Gauge",
            latitude=38.0,
            longitude=-105.0,
            water_type="reservoir",
        )
        usgs = MagicMock()
        result, df = fetch_water_data(usgs, loc)
        assert isinstance(result, dict)
        assert isinstance(df, pd.DataFrame)
        assert df.empty

    def test_returns_raw_dataframe(self, sample_location):
        raw_df = pd.DataFrame(
            {
                "parameter_code": ["00060", "00010"],
                "datetime": [pd.Timestamp.now(), pd.Timestamp.now()],
                "value": [15.0, 4.2],
                "unit": ["ft3/s", "deg C"],
            }
        )
        usgs = MagicMock()
        usgs.get_site_data.return_value = raw_df
        result, df = fetch_water_data(usgs, sample_location)
        assert not df.empty
        assert result["streamflow_cfs"] == 15.0
        assert result["water_temp_c"] == 4.2


# -- fetch_weather_data returns tuple ----------------------------------------


class TestFetchWeatherDataReturnsTuple:
    def test_returns_tuple_on_success(self, sample_location):
        wx_df = pd.DataFrame(
            {
                "datetime": [pd.Timestamp.now(tz="America/Denver").tz_localize(None)],
                "temperature_c": [12.0],
                "pressure_hpa": [1015.0],
                "cloud_cover_pct": [60.0],
                "wind_speed_kmh": [10.0],
                "precipitation_mm": [0.0],
            }
        )
        weather = MagicMock()
        weather.get_forecast.return_value = wx_df
        result, df = fetch_weather_data(weather, sample_location)
        assert isinstance(result, dict)
        assert not df.empty

    def test_returns_empty_df_on_failure(self, sample_location):
        weather = MagicMock()
        weather.get_forecast.side_effect = Exception("API down")
        result, df = fetch_weather_data(weather, sample_location)
        assert df.empty
        assert result["pressure_trend"] == "stable_high"


# -- _extract_daily_weather --------------------------------------------------


class TestExtractDailyWeather:
    def test_extracts_correct_day(self, sample_wx_df):
        today = date.today()
        weather = WeatherClient()
        result = _extract_daily_weather(sample_wx_df, today, weather)
        assert result["air_temp_c"] is not None
        assert result["cloud_cover_pct"] == pytest.approx(50.0)
        assert result["wind_speed_kmh"] == pytest.approx(8.0)

    def test_future_day_different_weather(self, sample_wx_df):
        tomorrow = date.today() + timedelta(days=1)
        weather = WeatherClient()
        result = _extract_daily_weather(sample_wx_df, tomorrow, weather)
        # Tomorrow has higher cloud cover (60.0 vs 50.0)
        assert result["cloud_cover_pct"] == pytest.approx(60.0)

    def test_empty_df_returns_defaults(self):
        weather = WeatherClient()
        result = _extract_daily_weather(pd.DataFrame(), date.today(), weather)
        assert result["pressure_trend"] == "stable_high"
        assert result["cloud_cover_pct"] == 50.0

    def test_missing_date_returns_defaults(self, sample_wx_df):
        far_future = date.today() + timedelta(days=30)
        weather = WeatherClient()
        result = _extract_daily_weather(sample_wx_df, far_future, weather)
        assert result["air_temp_c"] is None


# -- run_forecast ------------------------------------------------------------


class TestRunForecast:
    @patch("pipeline.CPWStockingClient")
    @patch("pipeline.WeatherClient")
    @patch("pipeline.USGSWaterClient")
    def test_returns_dict_of_location_scores(
        self, mock_usgs_cls, mock_wx_cls, mock_cpw_cls
    ):
        loc = FishingLocation(
            id="test-loc",
            name="Test Location",
            latitude=38.83,
            longitude=-104.82,
            water_type="river",
            historical_median_cfs=100.0,
        )

        # Mock USGS
        usgs_instance = mock_usgs_cls.return_value
        usgs_instance.get_site_data.return_value = pd.DataFrame()

        # Mock Weather — return 7 days of hourly data
        today = date.today()
        wx_rows = []
        for offset in range(7):
            d = today + timedelta(days=offset)
            for hour in range(24):
                wx_rows.append(
                    {
                        "datetime": pd.Timestamp(d) + pd.Timedelta(hours=hour),
                        "temperature_c": 15.0,
                        "pressure_hpa": 1013.0,
                        "cloud_cover_pct": 50.0,
                        "wind_speed_kmh": 10.0,
                        "precipitation_mm": 0.0,
                    }
                )
        wx_instance = mock_wx_cls.return_value
        wx_instance.get_forecast.return_value = pd.DataFrame(wx_rows)

        # Mock CPW
        cpw_instance = mock_cpw_cls.return_value
        cpw_instance.fetch_current_report.return_value = "<html></html>"
        cpw_instance.parse_stocking_report.return_value = []

        with patch("pipeline.MVP_WATERS", [loc]):
            forecast = run_forecast(days=7)

        assert "test-loc" in forecast
        assert len(forecast["test-loc"]) == 7
        # Each score should have the correct date
        for i, score in enumerate(forecast["test-loc"]):
            assert score.score_date == today + timedelta(days=i)
            assert 0 <= score.total <= 100


# -- best_bets_weekend -------------------------------------------------------


class TestBestBetsWeekend:
    @patch("pipeline.run_forecast")
    def test_output_format(self, mock_forecast):
        from storage.models import FishingScore
        from datetime import datetime, timezone

        today = date.today()
        days_until_saturday = (5 - today.weekday()) % 7
        if days_until_saturday == 0 and today.weekday() != 5:
            days_until_saturday = 7
        saturday = today + timedelta(days=days_until_saturday)
        sunday = saturday + timedelta(days=1)

        # Build mock forecast data
        forecast_days = (sunday - today).days + 1
        mock_scores = {}
        from locations.colorado_waters import MVP_WATERS

        for loc in MVP_WATERS:
            day_list = []
            for offset in range(forecast_days):
                d = today + timedelta(days=offset)
                day_list.append(
                    FishingScore(
                        location_id=loc.id,
                        location_name=loc.name,
                        score_date=d,
                        water_temp_score=10,
                        flow_score=10,
                        weather_score=10,
                        solunar_score=10,
                        stocking_score=10,
                        computed_at=datetime.now(tz=timezone.utc),
                    )
                )
            mock_scores[loc.id] = day_list

        mock_forecast.return_value = mock_scores

        output = best_bets_weekend()
        assert "BEST BETS THIS WEEKEND" in output
        assert "SATURDAY" in output
        assert "SUNDAY" in output
        assert "TOP PICK" in output
