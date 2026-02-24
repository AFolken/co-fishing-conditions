"""Shared test fixtures for USGS Water Services tests."""

import pytest


@pytest.fixture()
def sample_usgs_response() -> dict:
    """Minimal but structurally complete USGS IV JSON response.

    Contains two timeSeries entries: streamflow (00060) and temperature
    (00010) for Fountain Creek gauge 07105500.
    """
    return {
        "name": "ns1:timeSeriesResponseType",
        "declaredType": "org.cuahsi.waterml.TimeSeriesResponseType",
        "value": {
            "queryInfo": {
                "queryURL": (
                    "https://waterservices.usgs.gov/nwis/iv/"
                    "?format=json&sites=07105500"
                    "&parameterCd=00060,00010&period=P7D"
                ),
                "note": [],
            },
            "timeSeries": [
                {
                    "sourceInfo": {
                        "siteName": "FOUNTAIN CREEK AT COLORADO SPRINGS, CO",
                        "siteCode": [
                            {"value": "07105500", "agencyCode": "USGS"}
                        ],
                        "geoLocation": {
                            "geogLocation": {
                                "srs": "EPSG:4326",
                                "latitude": 38.8058,
                                "longitude": -104.8206,
                            }
                        },
                    },
                    "variable": {
                        "variableCode": [
                            {"value": "00060", "variableID": 45807197}
                        ],
                        "variableName": "Streamflow, ft&#179;/s",
                        "variableDescription": (
                            "Discharge, cubic feet per second"
                        ),
                        "unit": {"unitCode": "ft3/s"},
                    },
                    "values": [
                        {
                            "value": [
                                {
                                    "value": "12.3",
                                    "qualifiers": ["P"],
                                    "dateTime": "2026-02-13T00:00:00.000-07:00",
                                },
                                {
                                    "value": "14.7",
                                    "qualifiers": ["P"],
                                    "dateTime": "2026-02-13T00:15:00.000-07:00",
                                },
                                {
                                    "value": "-999999",
                                    "qualifiers": ["P", "Eqp"],
                                    "dateTime": "2026-02-13T00:30:00.000-07:00",
                                },
                            ],
                            "qualifier": [
                                {
                                    "qualifierCode": "P",
                                    "qualifierDescription": "Provisional data",
                                }
                            ],
                            "method": [{"methodID": 1}],
                        }
                    ],
                    "name": "USGS:07105500:00060:00000",
                },
                {
                    "sourceInfo": {
                        "siteName": "FOUNTAIN CREEK AT COLORADO SPRINGS, CO",
                        "siteCode": [
                            {"value": "07105500", "agencyCode": "USGS"}
                        ],
                        "geoLocation": {
                            "geogLocation": {
                                "srs": "EPSG:4326",
                                "latitude": 38.8058,
                                "longitude": -104.8206,
                            }
                        },
                    },
                    "variable": {
                        "variableCode": [
                            {"value": "00010", "variableID": 45807042}
                        ],
                        "variableName": "Temperature, water, &#176;C",
                        "variableDescription": (
                            "Temperature, water, degrees Celsius"
                        ),
                        "unit": {"unitCode": "deg C"},
                    },
                    "values": [
                        {
                            "value": [
                                {
                                    "value": "4.2",
                                    "qualifiers": ["P"],
                                    "dateTime": "2026-02-13T00:00:00.000-07:00",
                                },
                                {
                                    "value": "4.1",
                                    "qualifiers": ["A"],
                                    "dateTime": "2026-02-13T00:15:00.000-07:00",
                                },
                            ],
                            "qualifier": [
                                {
                                    "qualifierCode": "P",
                                    "qualifierDescription": "Provisional data",
                                }
                            ],
                            "method": [{"methodID": 1}],
                        }
                    ],
                    "name": "USGS:07105500:00010:00000",
                },
            ],
        },
    }


@pytest.fixture()
def empty_usgs_response() -> dict:
    """USGS response with an empty timeSeries list."""
    return {
        "value": {
            "queryInfo": {"queryURL": "", "note": []},
            "timeSeries": [],
        }
    }


@pytest.fixture()
def sample_usgs_stats_rdb() -> str:
    """Realistic USGS Statistics Service daily RDB response.

    Contains median (p50) daily statistics for two sites across
    three day-of-year entries each.
    """
    return (
        "# ---------------------------------- WARNING ----------------------------------------\n"
        "# Provisional data are subject to revision.\n"
        "# -----------------------------------------------------------------------------------\n"
        "#\n"
        "agency_cd\tsite_no\tparameter_cd\tts_id\tloc_web_ds\tmonth_nu\tday_nu\t"
        "begin_yr\tend_yr\tcount_nu\tp50_va\n"
        "5s\t15s\t5s\t10n\t12s\t2n\t2n\t4n\t4n\t8n\t12s\n"
        "USGS\t07105500\t00060\t12345\t\t1\t1\t1940\t2024\t85\t15.0\n"
        "USGS\t07105500\t00060\t12345\t\t2\t14\t1940\t2024\t85\t22.5\n"
        "USGS\t07105500\t00060\t12345\t\t6\t15\t1940\t2024\t85\t120.0\n"
        "USGS\t09050700\t00060\t67890\t\t1\t1\t1960\t2024\t65\t95.0\n"
        "USGS\t09050700\t00060\t67890\t\t2\t14\t1960\t2024\t65\t110.0\n"
        "USGS\t09050700\t00060\t67890\t\t6\t15\t1960\t2024\t65\t450.0\n"
    )
