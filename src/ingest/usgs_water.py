"""Client for the USGS Water Services Instantaneous Values API.

Fetches real-time streamflow and water temperature data for Colorado
gauge stations and returns clean pandas DataFrames.

API docs: https://waterservices.usgs.gov/docs/instantaneous-values/
"""

from __future__ import annotations

import pandas as pd
import requests

# USGS no-data sentinel value
_NODATA_VALUE = "-999999"


class USGSWaterClient:
    """Thin client around the USGS Water Services IV (instantaneous values) endpoint."""

    BASE_URL = "https://waterservices.usgs.gov/nwis/iv/"

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
