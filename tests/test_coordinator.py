"""Tests for the data update coordinators."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
import requests
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bosch_ebike.const import DOMAIN
from custom_components.bosch_ebike.coordinator import BoschEBikeDataCoordinator

from .conftest import BIKE_ID


def _http_error(status: int) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status
    return requests.HTTPError(f"{status} error", response=response)


def _client(profile_side_effect) -> MagicMock:
    client = MagicMock()
    client.activity.get_summaries.return_value = {"data": []}
    client.bike_profile.get.side_effect = profile_side_effect
    client.bike_profile.get_state_of_charge.return_value = {"stateOfCharge": 50}
    return client


def _coordinator(hass: HomeAssistant, token_manager) -> BoschEBikeDataCoordinator:
    entry = MockConfigEntry(domain=DOMAIN, data={"token": {}})
    entry.add_to_hass(hass)
    return BoschEBikeDataCoordinator(hass, entry, token_manager, [BIKE_ID])


class TestRetryOnUnauthorized:
    @pytest.mark.asyncio
    async def test_refreshes_and_retries_once(self, hass: HomeAssistant) -> None:
        stale = _client([_http_error(401)])
        fresh = _client([{"id": BIKE_ID}])
        token_manager = MagicMock()
        token_manager.get_client = AsyncMock(side_effect=[stale, fresh])

        data = await _coordinator(hass, token_manager)._async_update_data()

        assert data[BIKE_ID]["profile"] == {"id": BIKE_ID}
        assert data[BIKE_ID]["battery"] == {"stateOfCharge": 50}
        token_manager.get_client.assert_awaited_with(True)
        # Calls after the retry use the refreshed client.
        stale.bike_profile.get_state_of_charge.assert_not_called()

    @pytest.mark.asyncio
    async def test_gives_up_after_one_retry(self, hass: HomeAssistant) -> None:
        stale = _client([_http_error(401)])
        still_stale = _client([_http_error(401)])
        token_manager = MagicMock()
        token_manager.get_client = AsyncMock(side_effect=[stale, still_stale])

        data = await _coordinator(hass, token_manager)._async_update_data()

        assert data[BIKE_ID]["profile"] is None
        assert token_manager.get_client.await_count == 2

    @pytest.mark.asyncio
    async def test_other_errors_are_not_retried(self, hass: HomeAssistant) -> None:
        client = _client([_http_error(500)])
        token_manager = MagicMock()
        token_manager.get_client = AsyncMock(return_value=client)

        data = await _coordinator(hass, token_manager)._async_update_data()

        assert data[BIKE_ID]["profile"] is None
        token_manager.get_client.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rejected_refresh_requires_reauth(self, hass: HomeAssistant) -> None:
        stale = _client([_http_error(401)])
        token_manager = MagicMock()
        token_manager.get_client = AsyncMock(side_effect=[stale, ConfigEntryAuthFailed()])

        with pytest.raises(ConfigEntryAuthFailed):
            await _coordinator(hass, token_manager)._async_update_data()
