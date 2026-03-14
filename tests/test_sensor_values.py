"""Tests for sensor value extraction functions."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from custom_components.bosch_ebike.helpers import extract_bike_name
from custom_components.bosch_ebike.sensor import (
    SENSOR_DESCRIPTIONS,
    _get_battery,
    _get_charge_cycles,
    _get_ride_timestamp,
)

from .conftest import BIKE_ID


class TestGetBattery:
    def test_extracts_state_of_charge(self, bike_data):
        assert _get_battery(bike_data[BIKE_ID]) == 92

    def test_returns_none_when_missing(self):
        assert _get_battery({}) is None
        assert _get_battery({"battery": None}) is None

    def test_handles_zero_soc(self):
        assert _get_battery({"battery": {"stateOfCharge": 0}}) == 0

    def test_handles_zero_soc_via_fallback_key(self):
        assert _get_battery({"battery": {"soc": 0}}) == 0


class TestProfileSensors:
    @pytest.mark.parametrize(
        ("key", "expected"),
        [
            ("odometer", 2037430.0),
            ("battery_capacity", 560.0),
            ("motor_hours", 202),
            ("battery_energy_delivered", 20742),
        ],
    )
    def test_profile_sensor_value(self, bike_data, key, expected):
        desc = next(d for d in SENSOR_DESCRIPTIONS if d.key == key)
        assert desc.value_fn(bike_data[BIKE_ID]) == expected

    def test_charge_cycles(self, bike_data):
        assert _get_charge_cycles(bike_data[BIKE_ID]) == 36.1

    def test_all_return_none_when_profile_missing(self):
        data = {"profile": None, "battery": None, "latest_ride": None}
        profile_keys = {
            "battery",
            "odometer",
            "battery_capacity",
            "charge_cycles",
            "motor_hours",
            "battery_energy_delivered",
        }
        for desc in SENSOR_DESCRIPTIONS:
            if desc.key in profile_keys:
                assert desc.value_fn(data) is None, desc.key


class TestRideSensors:
    @pytest.mark.parametrize(
        ("key", "expected"),
        [
            ("last_ride_distance", 4369),
            ("last_ride_duration", 713),
            ("last_ride_avg_speed", 22.06),
            ("last_ride_max_speed", 37.77),
            ("last_ride_avg_power", 161.0),
            ("last_ride_calories", 82.0),
            ("last_ride_co2_saved", 725.254),
            ("last_ride_rider_energy_share", 37),
            ("last_ride_elevation_gain", 11),
        ],
    )
    def test_ride_sensor_value(self, bike_data, key, expected):
        desc = next(d for d in SENSOR_DESCRIPTIONS if d.key == key)
        assert desc.value_fn(bike_data[BIKE_ID]) == expected

    def test_all_return_none_when_no_ride(self):
        data = {"profile": None, "battery": None, "latest_ride": None}
        for desc in SENSOR_DESCRIPTIONS:
            if desc.key.startswith("last_ride_"):
                assert desc.value_fn(data) is None, desc.key


class TestRideTimestamp:
    def test_epoch_seconds(self):
        data = {"latest_ride": {"startTime": 1773431458}}
        assert _get_ride_timestamp(data) == datetime(2026, 3, 13, 19, 50, 58, tzinfo=UTC)

    def test_epoch_millis(self):
        data = {"latest_ride": {"startTime": 1773431458000}}
        assert _get_ride_timestamp(data) == datetime(2026, 3, 13, 19, 50, 58, tzinfo=UTC)

    def test_none_when_missing(self):
        assert _get_ride_timestamp({"latest_ride": None}) is None
        assert _get_ride_timestamp({"latest_ride": {}}) is None


class TestExtractBikeName:
    def test_brand_and_product_line(self, bike_profiles):
        assert extract_bike_name(bike_profiles[0]) == "Riese & Müller Cargo Line"

    def test_nickname_preferred(self):
        assert extract_bike_name({"nickname": "My Bike", "brandName": "Bosch"}) == "My Bike"

    def test_fallback_to_id(self):
        assert extract_bike_name({"id": "aabbccdd-1111-2222"}) == "aabbccdd"

    def test_empty_bike(self):
        assert extract_bike_name({}) == "eBike"


class TestSensorDescriptionUniqueness:
    def test_keys_are_unique(self):
        keys = [d.key for d in SENSOR_DESCRIPTIONS]
        assert len(keys) == len(set(keys))

    def test_names_are_unique(self):
        names = [d.name for d in SENSOR_DESCRIPTIONS]
        assert len(names) == len(set(names))
