"""Unit tests for solunar.calculator."""

from datetime import date, datetime, timedelta, timezone

import pytest

from solunar.calculator import (
    compute_solunar_rating,
    get_feeding_windows,
    get_moon_phase,
    get_moon_times,
    get_sun_times,
)

# Colorado Springs coordinates for all tests
COS_LAT = 38.83
COS_LON = -104.82


class TestGetMoonPhase:
    def test_known_full_moon(self):
        # Jan 13, 2025 was a full moon
        name, illum = get_moon_phase(date(2025, 1, 13))
        assert name == "full"
        assert illum > 0.95

    def test_known_new_moon(self):
        # Jan 29, 2025 was a new moon
        name, illum = get_moon_phase(date(2025, 1, 29))
        assert name == "new"
        assert illum < 0.05

    def test_returns_valid_phase_name(self):
        valid_names = {
            "new",
            "waxing_crescent",
            "first_quarter",
            "waxing_gibbous",
            "full",
            "waning_gibbous",
            "last_quarter",
            "waning_crescent",
        }
        name, illum = get_moon_phase(date(2025, 6, 15))
        assert name in valid_names
        assert 0.0 <= illum <= 1.0

    def test_illumination_range(self):
        # Check several dates produce illumination in [0, 1]
        for day_offset in range(0, 30):
            _, illum = get_moon_phase(date(2025, 3, 1) + timedelta(days=day_offset))
            assert 0.0 <= illum <= 1.0


class TestGetMoonTimes:
    def test_returns_all_keys(self):
        times = get_moon_times(date(2025, 6, 15), COS_LAT, COS_LON)
        assert set(times.keys()) == {"moonrise", "moonset", "transit", "antitransit"}

    def test_times_are_datetimes_or_none(self):
        times = get_moon_times(date(2025, 6, 15), COS_LAT, COS_LON)
        for key, val in times.items():
            assert val is None or isinstance(val, datetime), f"{key} has unexpected type"

    def test_moonrise_before_moonset_typically(self):
        # On most days at Colorado latitudes the moon rises and sets
        times = get_moon_times(date(2025, 6, 15), COS_LAT, COS_LON)
        if times["moonrise"] and times["moonset"]:
            # Just verify they're different (order can vary)
            assert times["moonrise"] != times["moonset"]


class TestGetSunTimes:
    def test_sunrise_before_sunset(self):
        times = get_sun_times(date(2025, 6, 15), COS_LAT, COS_LON)
        assert times["sunrise"] is not None
        assert times["sunset"] is not None
        assert times["sunrise"] < times["sunset"]

    def test_summer_vs_winter_day_length(self):
        summer = get_sun_times(date(2025, 6, 21), COS_LAT, COS_LON)
        winter = get_sun_times(date(2025, 12, 21), COS_LAT, COS_LON)

        summer_len = summer["sunset"] - summer["sunrise"]
        winter_len = winter["sunset"] - winter["sunrise"]
        assert summer_len > winter_len


class TestGetFeedingWindows:
    def test_returns_major_and_minor_keys(self):
        windows = get_feeding_windows(date(2025, 6, 15), COS_LAT, COS_LON)
        assert "major" in windows
        assert "minor" in windows

    def test_major_windows_are_about_2_hours(self):
        windows = get_feeding_windows(date(2025, 6, 15), COS_LAT, COS_LON)
        for start, end in windows["major"]:
            duration = (end - start).total_seconds() / 3600
            assert duration == pytest.approx(2.0, abs=0.01)

    def test_minor_windows_are_about_1_hour(self):
        windows = get_feeding_windows(date(2025, 6, 15), COS_LAT, COS_LON)
        for start, end in windows["minor"]:
            duration = (end - start).total_seconds() / 3600
            assert duration == pytest.approx(1.0, abs=0.01)

    def test_at_least_one_major_window(self):
        windows = get_feeding_windows(date(2025, 6, 15), COS_LAT, COS_LON)
        assert len(windows["major"]) >= 1


class TestComputeSolunarRating:
    def test_score_in_valid_range(self):
        # Check many dates stay within 0-20
        for day_offset in range(0, 30):
            d = date(2025, 3, 1) + timedelta(days=day_offset)
            score = compute_solunar_rating(d, COS_LAT, COS_LON)
            assert 0 <= score <= 20, f"Score {score} out of range for {d}"

    def test_full_moon_scores_high(self):
        # Full moon: Jan 13, 2025
        score = compute_solunar_rating(date(2025, 1, 13), COS_LAT, COS_LON)
        assert score >= 16

    def test_new_moon_scores_high(self):
        # New moon: Jan 29, 2025
        score = compute_solunar_rating(date(2025, 1, 29), COS_LAT, COS_LON)
        assert score >= 16

    def test_quarter_moon_scores_moderate(self):
        # Last quarter: Jan 21, 2025
        score = compute_solunar_rating(date(2025, 1, 21), COS_LAT, COS_LON)
        assert 4 <= score <= 14
