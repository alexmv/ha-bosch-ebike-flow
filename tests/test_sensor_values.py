"""Tests for sensor value extraction functions."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from custom_components.bosch_ebike.helpers import extract_bike_name
from custom_components.bosch_ebike.sensor import (
    SENSOR_DESCRIPTIONS,
    _get_battery,
    _get_charge_cycles,
    _get_range_attrs,
    _get_range_auto,
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

    def test_falls_back_to_profile_battery_level(self):
        profile = {"batteries": [{"batteryLevel": 64}]}
        assert _get_battery({"battery": None, "profile": profile}) == 64
        assert _get_battery({"battery": {"stateOfCharge": None}, "profile": profile}) == 64
        assert _get_battery({"battery": {"stateOfCharge": 80}, "profile": profile}) == 80


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


class TestRangeSensor:
    def test_returns_auto_range(self, bike_data):
        # Fixture has reachableRange: [52, 38, 25, 21], and no assist modes in
        # the profile, so the default layout puts AUTO at index 1.
        assert _get_range_auto(bike_data[BIKE_ID]) == 38.0

    def test_attrs_contain_all_modes(self, bike_data):
        attrs = _get_range_attrs(bike_data[BIKE_ID])
        assert attrs == {
            "range_eco_km": 52,
            "range_auto_km": 38,
            "range_sport_km": 25,
            "range_turbo_km": 21,
        }

    def test_none_when_no_battery(self):
        assert _get_range_auto({"battery": None}) is None
        assert _get_range_attrs({"battery": None}) == {}

    def test_none_when_range_missing(self):
        assert _get_range_auto({"battery": {}}) is None
        assert _get_range_attrs({"battery": {}}) == {}

    def test_modes_from_profile(self):
        # Mode layout as reported for a Performance Line bike; names come from
        # the last ride's assistModeUsage.
        data = {
            "profile": {
                "driveUnit": {
                    "driveUnitAssistModes": [
                        {"id": "0"},
                        {"id": "A100M40040"},
                        {"id": "A100E3AUTO"},
                        {"id": "A100M40020"},
                        {"id": "A100M40010"},
                    ]
                }
            },
            "battery": {"reachableRange": [33, 25, 16, 12]},
            "latest_ride": {
                "assistModeUsage": [
                    {"assistModeConfigId": "0", "name": "OFF"},
                    {"assistModeConfigId": "A100M40040", "name": "ECO"},
                    {"assistModeConfigId": "A100M40020", "name": "SPORT"},
                    {"assistModeConfigId": "A100M40010", "name": "TURBO"},
                    {"assistModeConfigId": "A100E3AUTO", "name": "AUTO"},
                ]
            },
        }
        assert _get_range_auto(data) == 25.0
        assert _get_range_attrs(data) == {
            "range_eco_km": 33,
            "range_auto_km": 25,
            "range_sport_km": 16,
            "range_turbo_km": 12,
        }

    def test_modes_without_names_or_auto(self):
        data = {
            "profile": {
                "driveUnit": {
                    "driveUnitAssistModes": [
                        {"id": "0"},
                        {"id": "A100M00040"},
                        {"id": "A100MAAAA0"},
                        {"id": "A100E00009"},
                    ]
                }
            },
            "battery": {"reachableRange": [60, 45, 30]},
            "latest_ride": {
                "assistModeUsage": [{"assistModeConfigId": "A100MAAAA0", "name": "TOUR+"}]
            },
        }
        # No AUTO mode, so report the longest range.
        assert _get_range_auto(data) == 60.0
        assert _get_range_attrs(data) == {
            "range_a100m00040_km": 60,
            "range_tour_plus_km": 45,
            "range_a100e00009_km": 30,
        }

    def test_description_has_attrs_fn(self):
        desc = next(d for d in SENSOR_DESCRIPTIONS if d.key == "estimated_range")
        assert desc.attrs_fn is not None


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
            ("last_ride_co2_saved", 712.147),
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


class TestRideCO2Saved:
    def test_none_when_a_field_is_missing(self):
        desc = next(d for d in SENSOR_DESCRIPTIONS if d.key == "last_ride_co2_saved")
        assert desc.value_fn({"latest_ride": {"co2EmissionsCarEquivalentGrams": 725.0}}) is None
        assert desc.value_fn({"latest_ride": {"co2EmissionsGrams": 13.0}}) is None


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
