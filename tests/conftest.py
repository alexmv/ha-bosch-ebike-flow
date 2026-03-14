"""Shared test fixtures for Bosch eBike Flow tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for all tests."""
    yield


FIXTURES_DIR = Path(__file__).parent / "fixtures"

BIKE_ID = "aabbccdd-1111-2222-3333-444455556666"


def _load_fixture(name: str) -> dict | list:
    return json.loads((FIXTURES_DIR / name).read_text())


@pytest.fixture()
def bike_profiles():
    return _load_fixture("bike_profiles.json")


@pytest.fixture()
def state_of_charge():
    return _load_fixture("state_of_charge.json")


@pytest.fixture()
def activity_summaries():
    return _load_fixture("activity_summaries.json")


@pytest.fixture()
def registrations():
    return _load_fixture("registrations.json")


@pytest.fixture()
def latest_locations():
    return _load_fixture("latest_locations.json")


@pytest.fixture()
def bike_data(bike_profiles, state_of_charge, activity_summaries):
    """Coordinator-shaped data dict for a single bike."""
    ride_attrs = activity_summaries["data"][0]["attributes"]
    return {
        BIKE_ID: {
            "profile": bike_profiles[0],
            "battery": state_of_charge,
            "latest_ride": ride_attrs,
        }
    }


@pytest.fixture()
def location_data(latest_locations):
    """Location coordinator-shaped data dict for a single bike."""
    return {BIKE_ID: latest_locations}
