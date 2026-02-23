"""Unit tests for ingest.weather (Open-Meteo client)."""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import requests

from ingest.weather import WeatherClient


@pytest.fixture()
def client() -> WeatherClient:
    return WeatherClient(timeout=5.0)


@pytest.fixture()
def sample_weather_response() -> dict:
    """Minimal but realistic Open-Meteo forecast response."""
    return {
        "latitude": 38.83,
        "longitude": -104.82,
        "timezone": "America/Denver",
        "hourly": {
            "time": [
                "2026-02-20T00:00",
                "2026-02-20T01:00",
                "2026-02-20T02:00",
                "2026-02-20T03:00",
                "2026-02-20T04:00",
                "2026-02-20T05:00",
                "2026-02-20T06:00",
            ],
            "temperature_2m": [-2.1, -2.5, -3.0, -3.2, -3.5, -3.0, -2.0],
            "surface_pressure": [812.0, 811.5, 811.0, 810.5, 810.0, 809.5, 809.0],
            "cloud_cover": [75, 80, 85, 90, 95, 100, 100],
            "wind_speed_10m": [8.2, 9.1, 10.5, 11.0, 12.3, 11.5, 10.0],
            "precipitation": [0.0, 0.0, 0.1, 0.3, 0.2, 0.0, 0.0],
        },
    }


@pytest.fixture()
def empty_weather_response() -> dict:
    return {"hourly": {"time": []}}


# -- get_forecast_raw -------------------------------------------------------


class TestGetForecastRaw:
    def test_builds_correct_params(self, client: WeatherClient):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"hourly": {"time": []}}
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client.session, "get", return_value=mock_resp) as mock_get:
            client.get_forecast_raw(38.83, -104.82, forecast_days=3)

            mock_get.assert_called_once()
            _, kwargs = mock_get.call_args
            params = kwargs["params"]
            assert params["latitude"] == 38.83
            assert params["longitude"] == -104.82
            assert params["forecast_days"] == 3
            assert "temperature_2m" in params["hourly"]
            assert "surface_pressure" in params["hourly"]

    def test_http_error_propagates(self, client: WeatherClient):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("500 Server Error")

        with patch.object(client.session, "get", return_value=mock_resp):
            with pytest.raises(requests.HTTPError, match="500"):
                client.get_forecast_raw(38.83, -104.82)


# -- parse_forecast ----------------------------------------------------------


class TestParseForecast:
    def test_returns_correct_columns(
        self, client: WeatherClient, sample_weather_response: dict
    ):
        df = client.parse_forecast(sample_weather_response)
        assert list(df.columns) == WeatherClient.DATAFRAME_COLUMNS

    def test_correct_row_count(
        self, client: WeatherClient, sample_weather_response: dict
    ):
        df = client.parse_forecast(sample_weather_response)
        assert len(df) == 7

    def test_correct_dtypes(
        self, client: WeatherClient, sample_weather_response: dict
    ):
        df = client.parse_forecast(sample_weather_response)
        assert pd.api.types.is_datetime64_any_dtype(df["datetime"])
        assert pd.api.types.is_float_dtype(df["temperature_c"])
        assert pd.api.types.is_float_dtype(df["pressure_hpa"])

    def test_values_match(
        self, client: WeatherClient, sample_weather_response: dict
    ):
        df = client.parse_forecast(sample_weather_response)
        assert df.iloc[0]["temperature_c"] == pytest.approx(-2.1)
        assert df.iloc[0]["pressure_hpa"] == pytest.approx(812.0)
        assert df.iloc[0]["wind_speed_kmh"] == pytest.approx(8.2)

    def test_empty_response(
        self, client: WeatherClient, empty_weather_response: dict
    ):
        df = client.parse_forecast(empty_weather_response)
        assert len(df) == 0
        assert list(df.columns) == WeatherClient.DATAFRAME_COLUMNS


# -- get_forecast (integration of fetch + parse) ----------------------------


class TestGetForecast:
    def test_end_to_end(
        self, client: WeatherClient, sample_weather_response: dict
    ):
        mock_resp = MagicMock()
        mock_resp.json.return_value = sample_weather_response
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client.session, "get", return_value=mock_resp):
            df = client.get_forecast(38.83, -104.82, days=1)

        assert len(df) == 7
        assert "temperature_c" in df.columns


# -- compute_pressure_trend --------------------------------------------------


class TestComputePressureTrend:
    def test_falling_rapid(self):
        pressures = pd.Series([1015.0, 1014.0, 1013.0, 1012.0, 1011.0, 1010.5, 1010.0])
        assert WeatherClient.compute_pressure_trend(pressures) == "falling_rapid"

    def test_falling_steady(self):
        pressures = pd.Series([1015.0, 1014.8, 1014.5, 1014.2, 1014.0, 1013.8, 1013.5])
        assert WeatherClient.compute_pressure_trend(pressures) == "falling_steady"

    def test_rising_steady(self):
        pressures = pd.Series([1010.0, 1010.5, 1011.0, 1011.5, 1012.0, 1012.5, 1013.0])
        assert WeatherClient.compute_pressure_trend(pressures) == "rising_steady"

    def test_stable_high(self):
        pressures = pd.Series([1016.0, 1016.1, 1016.0, 1015.9, 1016.0, 1016.1, 1016.2])
        assert WeatherClient.compute_pressure_trend(pressures) == "stable_high"

    def test_stable_low(self):
        pressures = pd.Series([1010.0, 1010.1, 1010.0, 1009.9, 1010.0, 1010.1, 1010.2])
        assert WeatherClient.compute_pressure_trend(pressures) == "stable_low"

    def test_empty_series(self):
        assert WeatherClient.compute_pressure_trend(pd.Series([], dtype=float)) == "stable_high"

    def test_single_value(self):
        assert WeatherClient.compute_pressure_trend(pd.Series([1013.0])) == "stable_high"
