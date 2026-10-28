"""Tests for the data update coordinators."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
import requests
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bosch_ebike.const import DATA_UPDATE_INTERVAL, DOMAIN
from custom_components.bosch_ebike.coordinator import BoschEBikeDataCoordinator

from .conftest import BIKE_ID


def _http_error(status: int, headers: dict[str, str] | None = None) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status
    response.headers.update(headers or {})
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


class TestRateLimit:
    @pytest.mark.parametrize(
        ("headers", "expected"),
        [
            ({"Retry-After": "900"}, 900),
            ({"Retry-After": "10"}, DATA_UPDATE_INTERVAL.total_seconds()),
            (
                {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"},
                DATA_UPDATE_INTERVAL.total_seconds(),
            ),
            ({}, DATA_UPDATE_INTERVAL.total_seconds()),
        ],
    )
    @pytest.mark.asyncio
    async def test_backs_off(self, hass: HomeAssistant, headers, expected) -> None:
        client = _client([_http_error(429, headers)])
        token_manager = MagicMock()
        token_manager.get_client = AsyncMock(return_value=client)

        with pytest.raises(UpdateFailed) as exc_info:
            await _coordinator(hass, token_manager)._async_update_data()

        assert exc_info.value.retry_after == expected
        client.bike_profile.get_state_of_charge.assert_not_called()


class TestNotFound:
    @pytest.mark.asyncio
    async def test_soc_404_is_not_a_warning(self, hass: HomeAssistant, caplog) -> None:
        client = _client([{"id": BIKE_ID}])
        client.bike_profile.get_state_of_charge.side_effect = _http_error(404)
        token_manager = MagicMock()
        token_manager.get_client = AsyncMock(return_value=client)

        with caplog.at_level(logging.WARNING):
            data = await _coordinator(hass, token_manager)._async_update_data()

        assert data[BIKE_ID]["battery"] is None
        assert data[BIKE_ID]["profile"] == {"id": BIKE_ID}
        assert "Failed to fetch SoC" not in caplog.text

    @pytest.mark.asyncio
    async def test_soc_500_is_a_warning(self, hass: HomeAssistant, caplog) -> None:
        client = _client([{"id": BIKE_ID}])
        client.bike_profile.get_state_of_charge.side_effect = _http_error(500)
        token_manager = MagicMock()
        token_manager.get_client = AsyncMock(return_value=client)

        with caplog.at_level(logging.WARNING):
            await _coordinator(hass, token_manager)._async_update_data()

        assert "Failed to fetch SoC" in caplog.text
