"""Unit tests for co_fishing_conditions.usgs_water."""

from unittest.mock import MagicMock, call, patch

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
                parameter_codes=["00060", "00010", "00065"],
                period="P7D",
            )

            mock_get.assert_called_once()
            _, kwargs = mock_get.call_args
            params = kwargs["params"]
            assert params["format"] == "json"
            assert params["sites"] == "07105500"
            assert params["parameterCd"] == "00060,00010,00065"
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
            assert kwargs["params"]["parameterCd"] == "00060,00010,00065"


# -- parse_daily_stats_rdb ---------------------------------------------------


class TestParseDailyStatsRdb:
    def test_parses_valid_rdb(
        self, sample_usgs_stats_rdb: str
    ):
        df = USGSWaterClient.parse_daily_stats_rdb(sample_usgs_stats_rdb)
        assert list(df.columns) == ["site_code", "month_nu", "day_nu", "median_cfs"]
        # 2 sites x 3 days = 6 rows
        assert len(df) == 6

    def test_correct_values(
        self, sample_usgs_stats_rdb: str
    ):
        df = USGSWaterClient.parse_daily_stats_rdb(sample_usgs_stats_rdb)

        # Fountain Creek Jan 1 median
        fc_jan1 = df[(df["site_code"] == "07105500") & (df["month_nu"] == 1) & (df["day_nu"] == 1)]
        assert len(fc_jan1) == 1
        assert fc_jan1.iloc[0]["median_cfs"] == pytest.approx(15.0)

        # Blue River June 15 median
        br_jun15 = df[(df["site_code"] == "09050700") & (df["month_nu"] == 6) & (df["day_nu"] == 15)]
        assert len(br_jun15) == 1
        assert br_jun15.iloc[0]["median_cfs"] == pytest.approx(450.0)

    def test_correct_dtypes(
        self, sample_usgs_stats_rdb: str
    ):
        df = USGSWaterClient.parse_daily_stats_rdb(sample_usgs_stats_rdb)
        assert pd.api.types.is_integer_dtype(df["month_nu"])
        assert pd.api.types.is_integer_dtype(df["day_nu"])
        assert pd.api.types.is_float_dtype(df["median_cfs"])

    def test_handles_empty_rdb(self):
        rdb = (
            "# Only comments here\n"
            "# No actual data\n"
        )
        df = USGSWaterClient.parse_daily_stats_rdb(rdb)
        assert len(df) == 0
        assert list(df.columns) == ["site_code", "month_nu", "day_nu", "median_cfs"]

    def test_handles_missing_p50(self):
        rdb = (
            "agency_cd\tsite_no\tparameter_cd\tts_id\tloc_web_ds\tmonth_nu\tday_nu\t"
            "begin_yr\tend_yr\tcount_nu\tp50_va\n"
            "5s\t15s\t5s\t10n\t12s\t2n\t2n\t4n\t4n\t8n\t12s\n"
            "USGS\t07105500\t00060\t12345\t\t1\t1\t1940\t2024\t85\t15.0\n"
            "USGS\t07105500\t00060\t12345\t\t1\t2\t1940\t2024\t85\t\n"
            "USGS\t07105500\t00060\t12345\t\t1\t3\t1940\t2024\t85\t18.0\n"
        )
        df = USGSWaterClient.parse_daily_stats_rdb(rdb)
        # Row with blank p50 should be dropped
        assert len(df) == 2
        assert set(df["day_nu"]) == {1, 3}

    def test_handles_missing_columns(self):
        rdb = (
            "agency_cd\tsite_no\tparameter_cd\n"
            "5s\t15s\t5s\n"
            "USGS\t07105500\t00060\n"
        )
        df = USGSWaterClient.parse_daily_stats_rdb(rdb)
        assert len(df) == 0


# -- get_daily_flow_stats -----------------------------------------------------


class TestGetDailyFlowStats:
    def test_batches_sites(self, client: USGSWaterClient, sample_usgs_stats_rdb: str):
        """12 sites should trigger exactly 2 API calls (10 + 2)."""
        mock_resp = MagicMock()
        mock_resp.text = sample_usgs_stats_rdb
        mock_resp.raise_for_status = MagicMock()

        sites = [f"0{i:07d}" for i in range(12)]

        with patch.object(client.session, "get", return_value=mock_resp) as mock_get:
            df = client.get_daily_flow_stats(sites)

        assert mock_get.call_count == 2
        # First batch should have 10 sites, second batch 2
        first_call_sites = mock_get.call_args_list[0][1]["params"]["sites"]
        second_call_sites = mock_get.call_args_list[1][1]["params"]["sites"]
        assert len(first_call_sites.split(",")) == 10
        assert len(second_call_sites.split(",")) == 2

    def test_empty_sites_list(self, client: USGSWaterClient):
        df = client.get_daily_flow_stats([])
        assert len(df) == 0
        assert list(df.columns) == ["site_code", "month_nu", "day_nu", "median_cfs"]

    def test_single_site(self, client: USGSWaterClient, sample_usgs_stats_rdb: str):
        mock_resp = MagicMock()
        mock_resp.text = sample_usgs_stats_rdb
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client.session, "get", return_value=mock_resp) as mock_get:
            df = client.get_daily_flow_stats(["07105500"])

        mock_get.assert_called_once()
        assert not df.empty
