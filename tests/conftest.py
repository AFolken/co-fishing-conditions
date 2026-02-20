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
