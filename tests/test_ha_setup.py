"""Tests for integration setup and unload."""

from __future__ import annotations

import contextlib
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bosch_ebike.const import DOMAIN

from .conftest import BIKE_ID, _load_fixture

FAKE_TOKEN = {
    "access_token": "at",
    "refresh_token": "rt",
    "expires_at": 9999999999,
}


def _make_config_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Bosch eBike (Test)",
        data={"token": FAKE_TOKEN},
        unique_id="test_unique_id",
    )
    entry.add_to_hass(hass)
    return entry


class FakeBikeProfile:
    _bikes = _load_fixture("bike_profiles.json")
    _soc = _load_fixture("state_of_charge.json")

    def get_all(self):
        return self._bikes

    def get(self, bike_id):
        return self._bikes[0]

    def get_state_of_charge(self, bike_id):
        return self._soc


class FakeActivity:
    def get_summaries(self):
        return _load_fixture("activity_summaries.json")


class FakeTheftDetection:
    def get_registrations(self, bike_id):
        return _load_fixture("registrations.json")

    def get_latest_locations(self, bike_id):
        return _load_fixture("latest_locations.json")


class FakeClient:
    def __init__(self, session):
        self.bike_profile = FakeBikeProfile()
        self.activity = FakeActivity()
        self.theft_detection = FakeTheftDetection()


@contextlib.contextmanager
def mock_all_api(client_class=FakeClient):
    """Patch all external API calls for setup + coordinator."""
    session = MagicMock()
    patches = [
        patch(
            "custom_components.bosch_ebike.refresh_session_token",
            return_value=(session, FAKE_TOKEN),
        ),
        patch("custom_components.bosch_ebike.create_session", return_value=session),
        patch("custom_components.bosch_ebike.BoschEBikeClient", client_class),
        patch(
            "custom_components.bosch_ebike.coordinator.refresh_session_token",
            return_value=(session, FAKE_TOKEN),
        ),
        patch("custom_components.bosch_ebike.coordinator.create_session", return_value=session),
        patch("custom_components.bosch_ebike.coordinator.BoschEBikeClient", client_class),
    ]
    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)
        yield


class TestSetupEntry:
    @pytest.mark.asyncio
    async def test_setup_creates_coordinators(self, hass: HomeAssistant) -> None:
        entry = _make_config_entry(hass)
        with mock_all_api():
            assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        entry_data = hass.data[DOMAIN][entry.entry_id]
        assert entry_data["bike_ids"] == [BIKE_ID]
        assert BIKE_ID in entry_data["bcm_bike_ids"]
        assert "data_coordinator" in entry_data
        assert "location_coordinator" in entry_data

    @pytest.mark.asyncio
    async def test_setup_without_bcm(self, hass: HomeAssistant) -> None:
        class FakeClientNoBCM(FakeClient):
            def __init__(self, session):
                super().__init__(session)
                self.theft_detection = type(
                    "td",
                    (),
                    {
                        "get_registrations": lambda self, bike_id: {"registrations": []},
                        "get_latest_locations": lambda self, bike_id: {"locations": []},
                    },
                )()

        entry = _make_config_entry(hass)
        with mock_all_api(FakeClientNoBCM):
            assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        entry_data = hass.data[DOMAIN][entry.entry_id]
        assert entry_data["bcm_bike_ids"] == []
        assert "location_coordinator" not in entry_data


class TestUnloadEntry:
    @pytest.mark.asyncio
    async def test_unload_cleans_up(self, hass: HomeAssistant) -> None:
        entry = _make_config_entry(hass)
        with mock_all_api():
            assert await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()
            assert await hass.config_entries.async_unload(entry.entry_id)
            await hass.async_block_till_done()

        assert entry.entry_id not in hass.data.get(DOMAIN, {})
