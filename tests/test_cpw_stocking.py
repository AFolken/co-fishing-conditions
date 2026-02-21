"""Unit tests for ingest.cpw_stocking (CPW stocking report scraper)."""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from ingest.cpw_stocking import CPWStockingClient

_FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def client() -> CPWStockingClient:
    return CPWStockingClient(timeout=5.0)


@pytest.fixture()
def sample_html() -> str:
    return (_FIXTURE_DIR / "cpw_stocking_sample.html").read_text()


# -- fetch_current_report ---------------------------------------------------


class TestFetchCurrentReport:
    def test_returns_html(self, client: CPWStockingClient):
        mock_resp = MagicMock()
        mock_resp.text = "<html><body>test</body></html>"
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client.session, "get", return_value=mock_resp):
            html = client.fetch_current_report()
            assert "<html>" in html

    def test_http_error_propagates(self, client: CPWStockingClient):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("403")

        with patch.object(client.session, "get", return_value=mock_resp):
            with pytest.raises(requests.HTTPError, match="403"):
                client.fetch_current_report()


# -- parse_stocking_report --------------------------------------------------


class TestParseStockingReport:
    def test_correct_event_count(self, client: CPWStockingClient, sample_html: str):
        events = client.parse_stocking_report(sample_html)
        assert len(events) == 8

    def test_water_names_extracted(self, client: CPWStockingClient, sample_html: str):
        events = client.parse_stocking_report(sample_html)
        names = [e.water_name for e in events]
        assert "Eleven Mile Reservoir" in names
        assert "Chatfield Reservoir" in names
        assert "Pueblo Reservoir" in names

    def test_dates_parsed(self, client: CPWStockingClient, sample_html: str):
        events = client.parse_stocking_report(sample_html)
        assert events[0].stocking_date == date(2026, 2, 14)
        assert events[2].stocking_date == date(2026, 2, 13)
        assert events[6].stocking_date == date(2026, 2, 10)

    def test_species_extracted(self, client: CPWStockingClient, sample_html: str):
        events = client.parse_stocking_report(sample_html)
        species_set = {e.species for e in events}
        assert "Rainbow Trout" in species_set
        assert "Cutthroat Trout" in species_set
        assert "Brown Trout" in species_set

    def test_quantity_parsed(self, client: CPWStockingClient, sample_html: str):
        events = client.parse_stocking_report(sample_html)
        # First event: Eleven Mile Reservoir, 5000
        assert events[0].quantity == 5000
        # Blue Mesa: 10,000
        assert events[7].quantity == 10000

    def test_location_id_matched(self, client: CPWStockingClient, sample_html: str):
        events = client.parse_stocking_report(sample_html)
        matched = {e.water_name: e.location_id for e in events}
        assert matched["Eleven Mile Reservoir"] == "eleven-mile-reservoir"
        assert matched["Chatfield Reservoir"] == "chatfield-reservoir"
        assert matched["Pueblo Reservoir"] == "pueblo-reservoir"

    def test_unmatched_water_gets_none(self, client: CPWStockingClient, sample_html: str):
        events = client.parse_stocking_report(sample_html)
        blue_mesa = [e for e in events if e.water_name == "Blue Mesa Reservoir"]
        assert len(blue_mesa) == 1
        assert blue_mesa[0].location_id is None

    def test_empty_html(self, client: CPWStockingClient):
        events = client.parse_stocking_report("<html><body></body></html>")
        assert events == []


# -- match_to_location ------------------------------------------------------


class TestMatchToLocation:
    def test_exact_match(self):
        assert CPWStockingClient.match_to_location("Pueblo Reservoir") == "pueblo-reservoir"

    def test_case_insensitive(self):
        assert CPWStockingClient.match_to_location("pueblo reservoir") == "pueblo-reservoir"

    def test_no_match(self):
        assert CPWStockingClient.match_to_location("Lake Nonexistent") is None

    def test_custom_mapping(self):
        mapping = {"My Lake": "my-lake-id"}
        assert CPWStockingClient.match_to_location("My Lake", mapping=mapping) == "my-lake-id"
