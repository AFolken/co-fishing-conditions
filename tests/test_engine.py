"""Unit tests for scoring.engine — composite scoring."""

import pytest

from scoring.engine import compute_score, label_score
from storage.models import FishingLocation


@pytest.fixture()
def sample_location() -> FishingLocation:
    return FishingLocation(
        id="test-river",
        name="Test River",
        latitude=38.83,
        longitude=-104.82,
        water_type="river",
        usgs_site_code="12345678",
    )


@pytest.fixture()
def gold_medal_location() -> FishingLocation:
    return FishingLocation(
        id="gold-medal-river",
        name="Gold Medal River",
        latitude=39.22,
        longitude=-105.28,
        water_type="river",
        is_gold_medal=True,
    )


class TestComputeScore:
    def test_all_defaults_produce_valid_score(self, sample_location):
        score = compute_score(sample_location)
        assert 0 <= score.total <= 100
        assert score.label in ("Epic", "Good", "Fair", "Tough", "Poor")

    def test_perfect_conditions(self, sample_location):
        score = compute_score(
            sample_location,
            water_temp_c=12.0,          # ideal range
            streamflow_cfs=100.0,        # normal
            historical_median_cfs=100.0,
            pressure_trend="falling_steady",
            cloud_cover_pct=90.0,
            wind_speed_kmh=15.0,
            solunar_rating=20,
            days_since_stocking=2,
        )
        assert score.total >= 80
        assert score.label == "Epic"

    def test_terrible_conditions(self, sample_location):
        score = compute_score(
            sample_location,
            water_temp_c=25.0,           # way too hot
            streamflow_cfs=500.0,         # flood
            historical_median_cfs=100.0,
            pressure_trend="falling_rapid",
            cloud_cover_pct=0.0,
            wind_speed_kmh=50.0,
            solunar_rating=4,
            days_since_stocking=30,
        )
        assert score.total <= 20
        assert score.label in ("Tough", "Poor")

    def test_total_equals_sum_of_components(self, sample_location):
        score = compute_score(
            sample_location,
            water_temp_c=12.0,
            streamflow_cfs=100.0,
            historical_median_cfs=100.0,
            solunar_rating=15,
        )
        expected = (
            score.water_temp_score
            + score.flow_score
            + score.weather_score
            + score.solunar_score
            + score.stocking_score
        )
        assert score.total == expected

    def test_gold_medal_bonus(self, gold_medal_location):
        score = compute_score(gold_medal_location)
        # Gold Medal with no stocking data → stocking_score should be 15
        assert score.stocking_score == 15

    def test_air_temp_fallback_when_water_temp_missing(self):
        """When water_temp_c is None but air_temp_c is available,
        the engine estimates water temp from air temp."""
        loc = FishingLocation(
            id="no-gauge-reservoir",
            name="No Gauge Reservoir",
            latitude=38.83,
            longitude=-104.82,
            water_type="reservoir",
            elevation_ft=9000.0,
        )
        # air_temp_c=20 at 9000ft → estimated water = 20 - 4 - 3 = 13°C (~55°F)
        # → ideal range → water_temp_score = 20
        score = compute_score(loc, air_temp_c=20.0)
        assert score.water_temp_score == 20

    def test_air_temp_not_used_when_water_temp_available(self):
        """When water_temp_c IS available, air_temp_c should be ignored."""
        loc = FishingLocation(
            id="gauged-river",
            name="Gauged River",
            latitude=38.83,
            longitude=-104.82,
            water_type="river",
        )
        # water_temp_c=3.0 (~37°F) → too cold → 0
        # air_temp_c=20.0 would give ideal range if used — but it shouldn't be
        score = compute_score(loc, water_temp_c=3.0, air_temp_c=20.0)
        assert score.water_temp_score == 0

    def test_wild_river_stocking_score(self):
        """Non-Gold-Medal rivers with no stocking data get wild fishery base."""
        loc = FishingLocation(
            id="wild-river",
            name="Wild River",
            latitude=38.83,
            longitude=-104.82,
            water_type="river",
        )
        score = compute_score(loc)
        assert score.stocking_score == 12

    def test_location_metadata(self, sample_location):
        score = compute_score(sample_location)
        assert score.location_id == "test-river"
        assert score.location_name == "Test River"
        assert score.computed_at is not None


class TestLabelScore:
    @pytest.mark.parametrize(
        "total, expected",
        [
            (95, "Epic"),
            (80, "Epic"),
            (79, "Good"),
            (60, "Good"),
            (59, "Fair"),
            (40, "Fair"),
            (39, "Tough"),
            (20, "Tough"),
            (19, "Poor"),
            (0, "Poor"),
        ],
    )
    def test_label_boundaries(self, total, expected):
        assert label_score(total) == expected
