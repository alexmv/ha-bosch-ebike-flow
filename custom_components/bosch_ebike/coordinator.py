"""Data update coordinators for Bosch eBike Flow."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api.auth import create_session, refresh_session_token
from .api.client import BoschEBikeClient
from .const import DATA_UPDATE_INTERVAL, DOMAIN, LOCATION_UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

# Refresh the token when it expires within this many seconds.
_TOKEN_REFRESH_MARGIN = 300


class TokenManager:
    """Serializes token refresh across coordinators.

    A single instance is shared via hass.data so that the data coordinator and
    location coordinator don't race each other when refreshing.
    """

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        self._hass = hass
        self._config_entry = config_entry
        self._lock = asyncio.Lock()

    async def get_client(self) -> BoschEBikeClient:
        """Return an authenticated client, refreshing the token if needed."""
        async with self._lock:
            token = self._config_entry.data["token"]
            expires_at = token.get("expires_at", 0)

            if time.time() < expires_at - _TOKEN_REFRESH_MARGIN:
                # Token is still fresh.
                return BoschEBikeClient(create_session(token))

            # Token is expired or close to expiring — refresh it.
            try:
                session, new_token = await self._hass.async_add_executor_job(
                    refresh_session_token, token
                )
                self._hass.config_entries.async_update_entry(
                    self._config_entry,
                    data={**self._config_entry.data, "token": new_token},
                )
                return BoschEBikeClient(session)
            except Exception:
                _LOGGER.debug("Token refresh failed, using existing token")
                return BoschEBikeClient(create_session(token))


class _BoschEBikeCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Base coordinator that delegates token management to a shared TokenManager."""

    def __init__(
        self,
        hass: HomeAssistant,
        token_manager: TokenManager,
        *,
        name: str,
        update_interval,
        config_entry,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=update_interval,
            config_entry=config_entry,
        )
        self._token_manager = token_manager

    async def _get_client(self) -> BoschEBikeClient:
        try:
            return await self._token_manager.get_client()
        except Exception as err:
            raise UpdateFailed(f"Authentication error: {err}") from err


class BoschEBikeDataCoordinator(_BoschEBikeCoordinator):
    """Coordinator that fetches bike profiles, battery SoC, and latest ride per bike."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        token_manager: TokenManager,
        bike_ids: list[str],
    ) -> None:
        super().__init__(
            hass,
            token_manager,
            name=f"{DOMAIN}_data",
            update_interval=DATA_UPDATE_INTERVAL,
            config_entry=config_entry,
        )
        self._bike_ids = bike_ids

    async def _async_update_data(self) -> dict[str, Any]:
        client = await self._get_client()

        # Fetch activity summaries once for all bikes (sorted newest-first).
        rides_by_bike: dict[str, dict] = {}
        try:
            rides_resp = await self.hass.async_add_executor_job(client.activity.get_summaries)
            for ride in rides_resp.get("data", []):
                attrs = ride.get("attributes", ride)
                bike_id = attrs.get("bikeId")
                # First match per bike is the newest (sorted by -startTime).
                if bike_id and bike_id not in rides_by_bike:
                    rides_by_bike[bike_id] = attrs
        except Exception as err:
            _LOGGER.warning("Failed to fetch activity summaries: %s", err)

        data: dict[str, Any] = {}
        for bike_id in self._bike_ids:
            bike_data: dict[str, Any] = {}

            try:
                bike_data["profile"] = await self.hass.async_add_executor_job(
                    client.bike_profile.get, bike_id
                )
            except Exception as err:
                _LOGGER.warning("Failed to fetch profile for bike %s: %s", bike_id, err)
                bike_data["profile"] = None

            try:
                bike_data["battery"] = await self.hass.async_add_executor_job(
                    client.bike_profile.get_state_of_charge, bike_id
                )
            except Exception as err:
                _LOGGER.warning("Failed to fetch SoC for bike %s: %s", bike_id, err)
                bike_data["battery"] = None

            bike_data["latest_ride"] = rides_by_bike.get(bike_id)
            data[bike_id] = bike_data

        return data


class BoschEBikeLocationCoordinator(_BoschEBikeCoordinator):
    """Coordinator that fetches GPS locations for BCM-registered bikes."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        token_manager: TokenManager,
        bcm_bike_ids: list[str],
    ) -> None:
        super().__init__(
            hass,
            token_manager,
            name=f"{DOMAIN}_location",
            update_interval=LOCATION_UPDATE_INTERVAL,
            config_entry=config_entry,
        )
        self._bcm_bike_ids = bcm_bike_ids

    async def _async_update_data(self) -> dict[str, Any]:
        client = await self._get_client()

        data: dict[str, Any] = {}
        for bike_id in self._bcm_bike_ids:
            try:
                data[bike_id] = await self.hass.async_add_executor_job(
                    client.theft_detection.get_latest_locations, bike_id
                )
            except Exception:
                _LOGGER.warning("Failed to fetch location for bike %s", bike_id)
                data[bike_id] = None

        return data
