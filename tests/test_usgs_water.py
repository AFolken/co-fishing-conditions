"""Unit tests for co_fishing_conditions.usgs_water."""

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
import requests

from ingest.usgs_water import USGSWaterClient


@pytest.fixture()
def client() -> USGSWaterClient:
    return USGSWaterClient(timeout=5.0)


# -- get_instantaneous_values ------------------------------------------------


class TestGetInstantaneousValues:
    def test_builds_correct_params_with_period(self, client: USGSWaterClient):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"value": {"timeSeries": []}}
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client.session, "get", return_value=mock_resp) as mock_get:
            client.get_instantaneous_values(
                site="07105500",
                parameter_codes=["00060", "00010"],
                period="P7D",
            )

            mock_get.assert_called_once()
            _, kwargs = mock_get.call_args
            params = kwargs["params"]
            assert params["format"] == "json"
            assert params["sites"] == "07105500"
            assert params["parameterCd"] == "00060,00010"
            assert params["period"] == "P7D"
            assert "startDT" not in params
            assert "endDT" not in params

    def test_builds_correct_params_with_date_range(self, client: USGSWaterClient):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"value": {"timeSeries": []}}
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client.session, "get", return_value=mock_resp) as mock_get:
            client.get_instantaneous_values(
                site="07105500",
                parameter_codes=["00060"],
                start_dt="2026-02-01",
                end_dt="2026-02-07",
            )

            _, kwargs = mock_get.call_args
            params = kwargs["params"]
            assert params["startDT"] == "2026-02-01"
            assert params["endDT"] == "2026-02-07"
            assert "period" not in params

    def test_http_error_propagates(self, client: USGSWaterClient):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("500 Server Error")

        with patch.object(client.session, "get", return_value=mock_resp):
            with pytest.raises(requests.HTTPError, match="500"):
                client.get_instantaneous_values(
                    site="07105500", parameter_codes=["00060"]
                )


# -- parse_timeseries --------------------------------------------------------


class TestParseTimeseries:
    def test_returns_correct_columns(
        self, client: USGSWaterClient, sample_usgs_response: dict
    ):
        df = client.parse_timeseries(sample_usgs_response)
        assert list(df.columns) == USGSWaterClient.DATAFRAME_COLUMNS

    def test_correct_row_count(
        self, client: USGSWaterClient, sample_usgs_response: dict
    ):
        df = client.parse_timeseries(sample_usgs_response)
        # 3 streamflow observations + 2 temperature observations
        assert len(df) == 5

    def test_correct_dtypes(
        self, client: USGSWaterClient, sample_usgs_response: dict
    ):
        df = client.parse_timeseries(sample_usgs_response)
        assert pd.api.types.is_datetime64_any_dtype(df["datetime"])
        assert pd.api.types.is_float_dtype(df["value"])
        assert pd.api.types.is_string_dtype(df["site_code"])

    def test_handles_missing_values(
        self, client: USGSWaterClient, sample_usgs_response: dict
    ):
        df = client.parse_timeseries(sample_usgs_response)
        # Third streamflow observation has value "-999999" → NaN
        streamflow = df[df["parameter_code"] == "00060"]
        assert np.isnan(streamflow.iloc[2]["value"])
        # Other values should be valid floats
        assert streamflow.iloc[0]["value"] == pytest.approx(12.3)
        assert streamflow.iloc[1]["value"] == pytest.approx(14.7)

    def test_parses_qualifiers(
        self, client: USGSWaterClient, sample_usgs_response: dict
    ):
        df = client.parse_timeseries(sample_usgs_response)
        streamflow = df[df["parameter_code"] == "00060"]
        assert streamflow.iloc[0]["qualifiers"] == "P"
        # The missing-data observation has two qualifiers
        assert streamflow.iloc[2]["qualifiers"] == "P,Eqp"

    def test_extracts_site_metadata(
        self, client: USGSWaterClient, sample_usgs_response: dict
    ):
        df = client.parse_timeseries(sample_usgs_response)
        assert (df["site_code"] == "07105500").all()
        assert (
            df["site_name"] == "FOUNTAIN CREEK AT COLORADO SPRINGS, CO"
        ).all()

    def test_extracts_units(
        self, client: USGSWaterClient, sample_usgs_response: dict
    ):
        df = client.parse_timeseries(sample_usgs_response)
        streamflow = df[df["parameter_code"] == "00060"]
        temp = df[df["parameter_code"] == "00010"]
        assert (streamflow["unit"] == "ft3/s").all()
        assert (temp["unit"] == "deg C").all()

    def test_empty_response(
        self, client: USGSWaterClient, empty_usgs_response: dict
    ):
        df = client.parse_timeseries(empty_usgs_response)
        assert len(df) == 0
        assert list(df.columns) == USGSWaterClient.DATAFRAME_COLUMNS


# -- get_site_data (integration of fetch + parse) ---------------------------


class TestGetSiteData:
    def test_end_to_end(
        self, client: USGSWaterClient, sample_usgs_response: dict
    ):
        mock_resp = MagicMock()
        mock_resp.json.return_value = sample_usgs_response
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client.session, "get", return_value=mock_resp):
            df = client.get_site_data("07105500")

        assert len(df) == 5
        assert set(df["parameter_code"].unique()) == {"00060", "00010"}

    def test_defaults_to_streamflow_and_temperature(
        self, client: USGSWaterClient, sample_usgs_response: dict
    ):
        mock_resp = MagicMock()
        mock_resp.json.return_value = sample_usgs_response
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client.session, "get", return_value=mock_resp) as mock_get:
            client.get_site_data("07105500")

            _, kwargs = mock_get.call_args
            assert kwargs["params"]["parameterCd"] == "00060,00010"
