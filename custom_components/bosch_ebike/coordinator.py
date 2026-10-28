"""Data update coordinators for Bosch eBike Flow."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import timedelta
from typing import Any, TypeVar

import requests
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api.auth import create_session, is_refresh_token_rejected, refresh_session_token
from .api.client import BoschEBikeClient
from .const import DATA_UPDATE_INTERVAL, DOMAIN, LOCATION_UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

_T = TypeVar("_T")

# Refresh the token when it expires within this many seconds.
_TOKEN_REFRESH_MARGIN = 300

# How many pages of rides to read, looking for each bike's latest ride.
_MAX_RIDE_PAGES = 5


def _retry_after(response: requests.Response, update_interval: timedelta | None) -> float:
    """Seconds until the next update, honoring a Retry-After header.

    Never returns less than the normal update interval: a short Retry-After
    must not make us poll more often than usual.
    """
    try:
        seconds = float(response.headers.get("Retry-After", ""))
    except ValueError:
        seconds = 0
    minimum = update_interval.total_seconds() if update_interval else 0
    return max(seconds, minimum)


def _is_not_found(err: Exception) -> bool:
    return (
        isinstance(err, requests.HTTPError)
        and err.response is not None
        and err.response.status_code == 404
    )


class TokenManager:
    """Serializes token refresh across coordinators.

    A single instance is shared via hass.data so that the data coordinator and
    location coordinator don't race each other when refreshing.
    """

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        self._hass = hass
        self._config_entry = config_entry
        self._lock = asyncio.Lock()

    async def get_client(self, force_refresh: bool = False) -> BoschEBikeClient:
        """Return an authenticated client, refreshing the token if needed."""
        async with self._lock:
            token = self._config_entry.data["token"]
            expires_at = token.get("expires_at", 0)

            if not force_refresh and time.time() < expires_at - _TOKEN_REFRESH_MARGIN:
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
            except Exception as err:
                if is_refresh_token_rejected(err):
                    raise ConfigEntryAuthFailed(
                        "Bosch rejected the refresh token; log in again"
                    ) from err
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
        self._client: BoschEBikeClient | None = None

    async def _get_client(self, force_refresh: bool = False) -> BoschEBikeClient:
        try:
            return await self._token_manager.get_client(force_refresh)
        except ConfigEntryAuthFailed:
            raise
        except Exception as err:
            raise UpdateFailed(f"Authentication error: {err}") from err

    async def _call(
        self, method: Callable[[BoschEBikeClient], Callable[..., _T]], *args: Any
    ) -> _T:
        """Make an API call in the executor.

        If the access token is rejected before it is due to expire, refresh it
        and retry once.  If we are rate-limited, abandon this update and wait
        at least as long as the server asks before the next one.
        """
        if self._client is None:
            self._client = await self._get_client()
        try:
            return await self.hass.async_add_executor_job(method(self._client), *args)
        except requests.HTTPError as err:
            status = err.response.status_code if err.response is not None else None
            if status == 429:
                raise UpdateFailed(
                    "Rate limited by the Bosch cloud",
                    retry_after=_retry_after(err.response, self.update_interval),
                ) from err
            if status != 401:
                raise
        _LOGGER.debug("Access token was rejected; refreshing and retrying")
        self._client = await self._get_client(force_refresh=True)
        return await self.hass.async_add_executor_job(method(self._client), *args)


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
        self._client = await self._get_client()

        # Fetch activity summaries, newest first.  The API has no per-bike
        # filter, so page through them until every bike has a ride -- but only
        # so far, so a bike that is never ridden doesn't make us read the
        # account's entire history on every poll.
        rides_by_bike: dict[str, dict] = {}
        try:
            for page in range(_MAX_RIDE_PAGES):
                rides_resp = await self._call(lambda c: c.activity.get_summaries, page)
                rides = rides_resp.get("data", [])
                for ride in rides:
                    attrs = ride.get("attributes", ride)
                    bike_id = attrs.get("bikeId")
                    # First match per bike is the newest (sorted by -startTime).
                    if bike_id and bike_id not in rides_by_bike:
                        rides_by_bike[bike_id] = attrs
                pages = (rides_resp.get("meta") or {}).get("pages")
                if (
                    rides_by_bike.keys() >= set(self._bike_ids)
                    or not rides
                    or not isinstance(pages, int)
                    or page + 1 >= pages
                ):
                    break
        except ConfigEntryAuthFailed, UpdateFailed:
            raise
        except Exception as err:
            _LOGGER.warning("Failed to fetch activity summaries: %s", err)

        data: dict[str, Any] = {}
        for bike_id in self._bike_ids:
            bike_data: dict[str, Any] = {}

            try:
                bike_data["profile"] = await self._call(lambda c: c.bike_profile.get, bike_id)
            except ConfigEntryAuthFailed, UpdateFailed:
                raise
            except Exception as err:
                _LOGGER.warning("Failed to fetch profile for bike %s: %s", bike_id, err)
                bike_data["profile"] = None

            try:
                bike_data["battery"] = await self._call(
                    lambda c: c.bike_profile.get_state_of_charge, bike_id
                )
            except ConfigEntryAuthFailed, UpdateFailed:
                raise
            except Exception as err:
                # A 404 is normal: there is no state of charge while the bike
                # has been offline for a while.
                log = _LOGGER.debug if _is_not_found(err) else _LOGGER.warning
                log("Failed to fetch SoC for bike %s: %s", bike_id, err)
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
        self._client = await self._get_client()

        data: dict[str, Any] = {}
        for bike_id in self._bcm_bike_ids:
            try:
                data[bike_id] = await self._call(
                    lambda c: c.theft_detection.get_latest_locations, bike_id
                )
            except ConfigEntryAuthFailed, UpdateFailed:
                raise
            except Exception as err:
                # A 404 is normal: the bike has not reported a location yet.
                log = _LOGGER.debug if _is_not_found(err) else _LOGGER.warning
                log("Failed to fetch location for bike %s: %s", bike_id, err)
                data[bike_id] = None

        return data
