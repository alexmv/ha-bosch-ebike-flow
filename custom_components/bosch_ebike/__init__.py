"""Bosch eBike Flow integration for Home Assistant."""

from __future__ import annotations

import logging

import requests
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .api.auth import create_session, is_refresh_token_rejected, refresh_session_token
from .api.client import BoschEBikeClient
from .const import DOMAIN
from .coordinator import (
    BoschEBikeDataCoordinator,
    BoschEBikeLocationCoordinator,
    TokenManager,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.DEVICE_TRACKER, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Bosch eBike Flow from a config entry."""
    token = entry.data["token"]

    # Refresh token at startup so the coordinators start with a fresh one.
    try:
        session, new_token = await hass.async_add_executor_job(refresh_session_token, token)
        hass.config_entries.async_update_entry(entry, data={**entry.data, "token": new_token})
    except Exception as err:
        if is_refresh_token_rejected(err):
            raise ConfigEntryAuthFailed("Bosch rejected the refresh token; log in again") from err
        _LOGGER.debug("Token refresh at setup failed, using existing token")
        session = create_session(token)

    client = BoschEBikeClient(session)

    # Fetch bike list — response is always a list of profile dicts with "id".
    # A failure here is usually Home Assistant starting before the host has
    # DNS or a route (the common case after a reboot). ConfigEntryNotReady
    # makes HA retry the setup with backoff instead of leaving the entry in a
    # permanent setup error that needs a manual reload.
    try:
        bikes = await hass.async_add_executor_job(client.bike_profile.get_all)
    except requests.exceptions.RequestException as err:
        raise ConfigEntryNotReady(f"Cannot reach Bosch eBike Flow: {err}") from err
    bike_ids = [b["id"] for b in bikes]

    # Detect BCM-registered bikes.
    bcm_bike_ids: list[str] = []
    for bike_id in bike_ids:
        try:
            registrations = await hass.async_add_executor_job(
                client.theft_detection.get_registrations, bike_id
            )
            if registrations.get("registrations"):
                bcm_bike_ids.append(bike_id)
        except Exception:  # noqa: BLE001 - treat any failure as "no BCM"
            _LOGGER.debug("No BCM registration for bike %s", bike_id)

    # Shared token manager prevents coordinator refresh races.
    token_manager = TokenManager(hass, entry)

    # Store bike metadata for platforms.
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "bikes": bikes,
        "bike_ids": bike_ids,
        "bcm_bike_ids": bcm_bike_ids,
    }

    # Create and start data coordinator.
    data_coordinator = BoschEBikeDataCoordinator(hass, entry, token_manager, bike_ids)
    await data_coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id]["data_coordinator"] = data_coordinator

    # Create and start location coordinator (only if BCM bikes exist).
    if bcm_bike_ids:
        location_coordinator = BoschEBikeLocationCoordinator(
            hass, entry, token_manager, bcm_bike_ids
        )
        await location_coordinator.async_config_entry_first_refresh()
        hass.data[DOMAIN][entry.entry_id]["location_coordinator"] = location_coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
