"""Tests for the charging binary sensor."""

from __future__ import annotations

from custom_components.bosch_ebike.binary_sensor import BoschEBikeChargingSensor

from .conftest import BIKE_ID


class FakeCoordinator:
    def __init__(self, data):
        self.data = data
        self.config_entry = None


def _make_sensor(data):
    coord = FakeCoordinator(data)
    sensor = object.__new__(BoschEBikeChargingSensor)
    sensor.coordinator = coord
    sensor._bike_id = BIKE_ID
    return sensor


class TestChargingSensor:
    def test_charging_active(self):
        data = {BIKE_ID: {"battery": {"chargingActive": True}}}
        assert _make_sensor(data).is_on is True

    def test_not_charging(self):
        data = {BIKE_ID: {"battery": {"chargingActive": False}}}
        assert _make_sensor(data).is_on is False

    def test_none_when_no_data(self):
        assert _make_sensor(None).is_on is None

    def test_none_when_no_battery(self):
        data = {BIKE_ID: {"battery": None}}
        assert _make_sensor(data).is_on is None

    def test_from_fixture(self, bike_data):
        """Fixture has chargingActive: false."""
        assert _make_sensor(bike_data).is_on is False
