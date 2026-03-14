"""Tests for device tracker location extraction."""

from __future__ import annotations

from custom_components.bosch_ebike.device_tracker import BoschEBikeTracker

from .conftest import BIKE_ID


class FakeCoordinator:
    """Minimal stand-in for the location coordinator."""

    def __init__(self, data):
        self.data = data
        self.config_entry = None


class TestGetLocation:
    def _make_tracker(self, data):
        coord = FakeCoordinator(data)
        tracker = object.__new__(BoschEBikeTracker)
        tracker.coordinator = coord
        tracker._bike_id = BIKE_ID
        return tracker

    def test_extracts_lat_lon(self, location_data):
        tracker = self._make_tracker(location_data)
        assert tracker.latitude == 48.8566
        assert tracker.longitude == 2.3522

    def test_extracts_accuracy(self, location_data):
        tracker = self._make_tracker(location_data)
        assert tracker.location_accuracy == 10

    def test_none_when_no_data(self):
        tracker = self._make_tracker(None)
        assert tracker.latitude is None
        assert tracker.longitude is None
        assert tracker.location_accuracy == 0

    def test_none_when_empty_locations(self):
        tracker = self._make_tracker({BIKE_ID: {"locations": []}})
        assert tracker.latitude is None

    def test_none_when_bike_missing(self):
        tracker = self._make_tracker({"other-bike": {"locations": []}})
        assert tracker.latitude is None
