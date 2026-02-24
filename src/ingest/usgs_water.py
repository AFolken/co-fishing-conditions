"""Client for the USGS Water Services APIs.

Fetches real-time streamflow and water temperature data for Colorado
gauge stations, plus historical daily statistics (median flow by
day-of-year).  Returns clean pandas DataFrames.

API docs:
  IV:    https://waterservices.usgs.gov/docs/instantaneous-values/
  Stats: https://waterservices.usgs.gov/docs/statistics/statistics-details/
"""

from __future__ import annotations

import io

import pandas as pd
import requests

# USGS no-data sentinel value
_NODATA_VALUE = "-999999"


class USGSWaterClient:
    """Thin client around the USGS Water Services IV and Statistics endpoints."""

    BASE_URL = "https://waterservices.usgs.gov/nwis/iv/"
    STATS_URL = "https://waterservices.usgs.gov/nwis/stat/"

    # Common USGS parameter codes
    PARAM_STREAMFLOW = "00060"  # Discharge, cubic feet per second
    PARAM_TEMPERATURE = "00010"  # Water temperature, degrees Celsius
    PARAM_HEIGHT = "00065" # Water level, feet

    DATAFRAME_COLUMNS = [
        "site_code",
        "site_name",
        "parameter_code",
        "parameter_name",
        "datetime",
        "value",
        "unit",
        "qualifiers",
    ]

    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {"Accept": "application/json", "User-Agent": "co-fishing-conditions/0.1"}
        )

    # -- low-level API call --------------------------------------------------

    def get_instantaneous_values(
        self,
        site: str,
        parameter_codes: list[str],
        period: str = "P7D",
        start_dt: str | None = None,
        end_dt: str | None = None,
    ) -> dict:
        """Fetch raw JSON from the USGS IV endpoint.

        Parameters
        ----------
        site : str
            USGS site number (e.g. ``"07105500"`` for Fountain Creek).
        parameter_codes : list[str]
            USGS parameter codes to request (e.g. ``["00060", "00010"]``).
        period : str
            ISO-8601 duration for a relative window (default ``"P7D"``).
            Ignored when *start_dt* / *end_dt* are provided.
        start_dt, end_dt : str | None
            Explicit date range in ``YYYY-MM-DD`` format. Both must be given
            together; when set they override *period*.

        Returns
        -------
        dict
            The full parsed JSON response from the USGS API.
        """
        params: dict[str, str] = {
            "format": "json",
            "sites": site,
            "parameterCd": ",".join(parameter_codes),
        }

        if start_dt and end_dt:
            params["startDT"] = start_dt
            params["endDT"] = end_dt
        else:
            params["period"] = period

        resp = self.session.get(self.BASE_URL, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    # -- parsing -------------------------------------------------------------

    def parse_timeseries(self, raw_json: dict) -> pd.DataFrame:
        """Convert the nested USGS JSON into a flat DataFrame.

        Parameters
        ----------
        raw_json : dict
            A full USGS IV JSON response (as returned by
            :meth:`get_instantaneous_values`).

        Returns
        -------
        pd.DataFrame
            One row per observation with columns:
            ``site_code``, ``site_name``, ``parameter_code``,
            ``parameter_name``, ``datetime``, ``value``, ``unit``,
            ``qualifiers``.
        """
        time_series_list = raw_json.get("value", {}).get("timeSeries", [])

        if not time_series_list:
            return pd.DataFrame(columns=self.DATAFRAME_COLUMNS)

        rows: list[dict] = []

        for ts in time_series_list:
            source = ts["sourceInfo"]
            variable = ts["variable"]

            site_code = source["siteCode"][0]["value"]
            site_name = source["siteName"]
            param_code = variable["variableCode"][0]["value"]
            param_name = variable["variableName"]
            unit = variable.get("unit", {}).get("unitCode", "")

            for observation in ts["values"][0]["value"]:
                raw_val = observation["value"]
                rows.append(
                    {
                        "site_code": site_code,
                        "site_name": site_name,
                        "parameter_code": param_code,
                        "parameter_name": param_name,
                        "datetime": observation["dateTime"],
                        "value": float("nan")
                        if raw_val == _NODATA_VALUE
                        else float(raw_val),
                        "unit": unit,
                        "qualifiers": ",".join(observation.get("qualifiers", [])),
                    }
                )

        df = pd.DataFrame(rows, columns=self.DATAFRAME_COLUMNS)
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
        return df

    # -- convenience wrappers ------------------------------------------------

    def get_site_data(
        self,
        site: str,
        parameter_codes: list[str] | None = None,
        period: str = "P7D",
        start_dt: str | None = None,
        end_dt: str | None = None,
    ) -> pd.DataFrame:
        """Fetch and parse instantaneous values for a single site.

        This is the primary method most callers should use.  It defaults to
        streamflow (00060), water temperature (00010), and gage height (00065).
        """
        if parameter_codes is None:
            parameter_codes = [self.PARAM_STREAMFLOW, self.PARAM_TEMPERATURE, self.PARAM_HEIGHT]

        raw = self.get_instantaneous_values(
            site=site,
            parameter_codes=parameter_codes,
            period=period,
            start_dt=start_dt,
            end_dt=end_dt,
        )
        return self.parse_timeseries(raw)

    def get_colorado_sites(
        self, parameter_code: str = "00060"
    ) -> pd.DataFrame:
        """Return metadata for all active Colorado gauges with *parameter_code*.

        Useful for discovering which sites report streamflow or temperature.
        """
        params: dict[str, str] = {
            "format": "json",
            "stateCd": "CO",
            "parameterCd": parameter_code,
            "siteStatus": "active",
        }

        resp = self.session.get(self.BASE_URL, params=params, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()

        time_series_list = data.get("value", {}).get("timeSeries", [])
        seen: set[str] = set()
        rows: list[dict] = []

        for ts in time_series_list:
            source = ts["sourceInfo"]
            code = source["siteCode"][0]["value"]
            if code in seen:
                continue
            seen.add(code)

            geo = (
                source.get("geoLocation", {})
                .get("geogLocation", {})
            )
            rows.append(
                {
                    "site_code": code,
                    "site_name": source["siteName"],
                    "latitude": geo.get("latitude"),
                    "longitude": geo.get("longitude"),
                }
            )

        return pd.DataFrame(rows)

    # -- daily flow statistics ------------------------------------------------

    def get_daily_flow_stats(
        self,
        sites: list[str],
        parameter_code: str = "00060",
    ) -> pd.DataFrame:
        """Fetch daily median streamflow statistics from the USGS Statistics Service.

        The Statistics Service returns historical daily medians (p50) by
        day-of-year across the full period of record.  The API accepts at
        most 10 sites per request, so this method batches automatically.

        Parameters
        ----------
        sites : list[str]
            USGS site codes (e.g. ``["07105500", "06696980"]``).
        parameter_code : str
            USGS parameter code (default ``"00060"`` for streamflow).

        Returns
        -------
        pd.DataFrame
            Columns: ``site_code``, ``month_nu``, ``day_nu``, ``median_cfs``.
            One row per site per calendar day (up to 366 rows per site).
        """
        all_frames: list[pd.DataFrame] = []

        # USGS Stats API allows max 10 sites per request
        for i in range(0, len(sites), 10):
            batch = sites[i : i + 10]
            df = self._fetch_daily_stats_batch(batch, parameter_code)
            if not df.empty:
                all_frames.append(df)

        if not all_frames:
            return pd.DataFrame(columns=["site_code", "month_nu", "day_nu", "median_cfs"])

        return pd.concat(all_frames, ignore_index=True)

    def _fetch_daily_stats_batch(
        self,
        sites: list[str],
        parameter_code: str,
    ) -> pd.DataFrame:
        """Fetch and parse one batch (<=10 sites) of daily statistics."""
        params: dict[str, str] = {
            "format": "rdb",
            "sites": ",".join(sites),
            "statReportType": "daily",
            "statTypeCd": "median",
            "parameterCd": parameter_code,
        }

        resp = self.session.get(self.STATS_URL, params=params, timeout=self.timeout)
        resp.raise_for_status()
        return self.parse_daily_stats_rdb(resp.text)

    @staticmethod
    def parse_daily_stats_rdb(rdb_text: str) -> pd.DataFrame:
        """Parse USGS Statistics Service RDB (tab-delimited) output.

        The RDB format has comment lines starting with ``#``, a header
        row, a data-types row (e.g. ``5s  15s  ...``), then data rows.

        Returns
        -------
        pd.DataFrame
            Columns: ``site_code``, ``month_nu``, ``day_nu``, ``median_cfs``.
        """
        # Strip comment lines (start with #)
        lines = [
            line for line in rdb_text.splitlines()
            if line and not line.startswith("#")
        ]

        if len(lines) < 2:
            return pd.DataFrame(columns=["site_code", "month_nu", "day_nu", "median_cfs"])

        # Line 0 = headers, line 1 = data-type descriptors, lines 2+ = data
        df = pd.read_csv(
            io.StringIO("\n".join([lines[0]] + lines[2:])),
            sep="\t",
            dtype=str,
        )

        # The statistics service returns p50_va for median when statTypeCd=median
        # or when statTypeCd=all.  Column names from the API:
        #   site_no, parameter_cd, month_nu, day_nu, p50_va, ...
        required = {"site_no", "month_nu", "day_nu"}
        if not required.issubset(df.columns):
            return pd.DataFrame(columns=["site_code", "month_nu", "day_nu", "median_cfs"])

        # Determine the median column — p50_va when using statTypeCd=all or median
        median_col = "p50_va"
        if median_col not in df.columns:
            # When statTypeCd=median, the value column may just be named differently
            # Fall back to any column ending in _va that looks like the median
            va_cols = [c for c in df.columns if c.endswith("_va") and c.startswith("p")]
            if va_cols:
                median_col = va_cols[0]
            else:
                return pd.DataFrame(columns=["site_code", "month_nu", "day_nu", "median_cfs"])

        result = pd.DataFrame({
            "site_code": df["site_no"],
            "month_nu": pd.to_numeric(df["month_nu"], errors="coerce").astype("Int64"),
            "day_nu": pd.to_numeric(df["day_nu"], errors="coerce").astype("Int64"),
            "median_cfs": pd.to_numeric(df[median_col], errors="coerce"),
        })

        # Drop rows where median is missing or month/day is invalid
        result = result.dropna(subset=["median_cfs", "month_nu", "day_nu"])
        return result


# ---------------------------------------------------------------------------
# Quick smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    client = USGSWaterClient()

    print("Fetching 7-day data for Fountain Creek (07105500)...")
    df = client.get_site_data("07105500")

    print(f"\nRows: {len(df)}")
    print(f"Parameters: {df['parameter_name'].unique().tolist()}")
    print(f"Date range: {df['datetime'].min()} → {df['datetime'].max()}")
    print()
    print(df.head(10).to_string(index=False))
    print("...")
    print(df.tail(5).to_string(index=False))
