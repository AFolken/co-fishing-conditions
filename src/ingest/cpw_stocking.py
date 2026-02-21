"""Scraper for Colorado Parks & Wildlife stocking reports.

Fetches the HTML stocking report from cpw.state.co.us, parses the table,
and returns structured StockingEvent objects.

CPW publishes weekly stocking reports (updated Fridays during fishing season)
listing which waters were stocked with catchable trout.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import requests
from bs4 import BeautifulSoup

from storage.models import FishingLocation, StockingEvent

# Static mapping from CPW water names to location IDs.
# CPW names are informal; this maps them to our FishingLocation slugs.
_NAME_TO_LOCATION_ID: dict[str, str] = {
    "Eleven Mile Reservoir": "eleven-mile-reservoir",
    "Spinney Mountain Reservoir": "spinney-mountain-reservoir",
    "North Catamount Reservoir": "north-catamount-reservoir",
    "South Catamount Reservoir": "south-catamount-reservoir",
    "Fountain Creek": "fountain-creek-cos",
    "Rampart Reservoir": "rampart-reservoir",
    "Monument Lake": "monument-lake",
    "Pueblo Reservoir": "pueblo-reservoir",
    "Chatfield Reservoir": "chatfield-reservoir",
    "Horsetooth Reservoir": "horsetooth-reservoir",
}


class CPWStockingClient:
    """Fetches and parses CPW fish stocking reports."""

    BASE_URL = "https://cpw.state.co.us/fishing/stocking-report"

    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (compatible; co-fishing-conditions/0.1; "
                    "+https://github.com/AFolken/co-fishing-conditions)"
                ),
                "Accept": "text/html",
            }
        )

    # -- fetching ------------------------------------------------------------

    def fetch_current_report(self) -> str:
        """Fetch the raw HTML of the current CPW stocking report page."""
        resp = self.session.get(self.BASE_URL, timeout=self.timeout)
        resp.raise_for_status()
        return resp.text

    # -- parsing -------------------------------------------------------------

    def parse_stocking_report(self, html: str) -> list[StockingEvent]:
        """Parse a CPW stocking report HTML page into StockingEvent objects.

        The CPW page contains a table with columns:
        Date | Water | County | Species | Number
        """
        soup = BeautifulSoup(html, "lxml")

        # Find the stocking table — try multiple selectors for robustness
        table = (
            soup.select_one("table.stocking-table")
            or soup.select_one(".stocking-report table")
            or soup.find("table")
        )

        if table is None:
            return []

        rows = table.select("tbody tr")
        if not rows:
            rows = table.find_all("tr")[1:]  # skip header row

        events: list[StockingEvent] = []
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 4:
                continue

            date_str = cells[0].get_text(strip=True)
            water_name = cells[1].get_text(strip=True)
            # cells[2] is county — we skip it
            species = cells[3].get_text(strip=True)

            quantity: int | None = None
            if len(cells) >= 5:
                qty_text = cells[4].get_text(strip=True).replace(",", "")
                try:
                    quantity = int(qty_text)
                except ValueError:
                    pass

            stocking_date = _parse_date(date_str)
            if stocking_date is None:
                continue

            location_id = self.match_to_location(water_name)

            events.append(
                StockingEvent(
                    water_name=water_name,
                    stocking_date=stocking_date,
                    species=species,
                    location_id=location_id,
                    quantity=quantity,
                )
            )

        return events

    # -- convenience ---------------------------------------------------------

    def get_recent_stockings(self, days: int = 14) -> list[StockingEvent]:
        """Fetch the stocking report and return events within the last N days."""
        html = self.fetch_current_report()
        events = self.parse_stocking_report(html)
        cutoff = date.today() - timedelta(days=days)
        return [e for e in events if e.stocking_date >= cutoff]

    # -- name matching -------------------------------------------------------

    @staticmethod
    def match_to_location(
        water_name: str,
        mapping: dict[str, str] | None = None,
    ) -> str | None:
        """Match a CPW water name to a FishingLocation ID.

        Uses the static ``_NAME_TO_LOCATION_ID`` mapping by default.
        Returns ``None`` if no match is found.
        """
        lookup = mapping or _NAME_TO_LOCATION_ID
        # Exact match first
        if water_name in lookup:
            return lookup[water_name]

        # Case-insensitive match
        lower_name = water_name.lower()
        for key, loc_id in lookup.items():
            if key.lower() == lower_name:
                return loc_id

        return None


def _parse_date(text: str) -> date | None:
    """Try common date formats used in CPW reports."""
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None
