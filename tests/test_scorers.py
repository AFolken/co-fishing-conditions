"""Unit tests for scoring.scorers — individual scorer functions."""

import pytest

from scoring.scorers import (
    score_flow,
    score_solunar,
    score_stocking,
    score_water_temperature,
    score_weather,
)


# -- score_water_temperature -------------------------------------------------


class TestScoreWaterTemperature:
    @pytest.mark.parametrize(
        "temp_c, expected",
        [
            (12.0, 20),   # ~54 F — ideal range
            (10.0, 20),   # ~50 F — low end of ideal
            (16.5, 20),   # ~61.7 F — high end of ideal
            (7.5, 15),    # ~45.5 F — acceptable low
            (18.0, 15),   # ~64.4 F — acceptable high
            (5.0, 8),     # ~41 F — cold
            (19.5, 5),    # ~67.1 F — warm
            (3.0, 0),     # ~37.4 F — too cold
            (22.0, 0),    # ~71.6 F — too warm
            (None, 10),   # missing data → neutral
        ],
    )
    def test_temperature_thresholds(self, temp_c, expected):
        assert score_water_temperature(temp_c) == expected

    def test_always_returns_0_to_20(self):
        for temp_c in range(-10, 40):
            score = score_water_temperature(float(temp_c))
            assert 0 <= score <= 20


# -- score_flow --------------------------------------------------------------


class TestScoreFlow:
    def test_normal_flow(self):
        assert score_flow(100.0, historical_median_cfs=100.0) == 20

    def test_low_but_fishable(self):
        assert score_flow(40.0, historical_median_cfs=100.0) == 14

    def test_high_but_fishable(self):
        assert score_flow(200.0, historical_median_cfs=100.0) == 12

    def test_drought(self):
        assert score_flow(20.0, historical_median_cfs=100.0) == 5

    def test_flood(self):
        assert score_flow(300.0, historical_median_cfs=100.0) == 0

    def test_missing_current(self):
        assert score_flow(None) == 10

    def test_missing_historical(self):
        assert score_flow(100.0, historical_median_cfs=None) == 10

    def test_zero_historical(self):
        assert score_flow(100.0, historical_median_cfs=0.0) == 10


# -- score_weather -----------------------------------------------------------


class TestScoreWeather:
    def test_falling_steady_overcast_light_wind(self):
        # 20 (pressure) + 2 (overcast) + 1 (good wind) = 23, capped at 20
        assert score_weather("falling_steady", 90.0, 15.0) == 20

    def test_stable_high_clear_calm(self):
        # 12 (stable high) + 0 (clear) + 0 (calm) = 12
        assert score_weather("stable_high", 10.0, 3.0) == 12

    def test_rising_partly_cloudy_heavy_wind(self):
        # 8 (rising) + 1 (partly) - 3 (heavy wind) = 6
        assert score_weather("rising_steady", 50.0, 45.0) == 6

    def test_falling_rapid(self):
        assert score_weather("falling_rapid", 0.0, 0.0) == 5

    def test_unknown_trend_defaults(self):
        assert score_weather("unknown", 0.0, 0.0) == 10

    def test_never_negative(self):
        # Worst case: falling_rapid (5) + heavy wind (-3) = 2
        score = score_weather("falling_rapid", 0.0, 50.0)
        assert score >= 0


# -- score_solunar -----------------------------------------------------------


class TestScoreSolunar:
    def test_passthrough(self):
        assert score_solunar(15) == 15

    def test_clamps_high(self):
        assert score_solunar(25) == 20

    def test_clamps_low(self):
        assert score_solunar(-5) == 0


# -- score_stocking ----------------------------------------------------------


class TestScoreStocking:
    def test_stocked_within_3_days(self):
        assert score_stocking(2) == 20

    def test_stocked_within_7_days(self):
        assert score_stocking(5) == 15

    def test_stocked_within_14_days(self):
        assert score_stocking(10) == 8

    def test_no_recent_stocking(self):
        assert score_stocking(30) == 5

    def test_no_data(self):
        assert score_stocking(None) == 5

    def test_gold_medal_no_stocking(self):
        # Gold Medal, no stocking → base 10 + 5 = 15
        assert score_stocking(None, is_gold_medal=True) == 15

    def test_gold_medal_recently_stocked(self):
        # Stocked 2 days ago (20) + gold medal (5) = 25, capped at 20
        assert score_stocking(2, is_gold_medal=True) == 20

    def test_gold_medal_7_days(self):
        # Stocked 5 days ago (15) + gold medal (5) = 20
        assert score_stocking(5, is_gold_medal=True) == 20
