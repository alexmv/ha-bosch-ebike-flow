"""Device tracker platform for Bosch eBike Flow (BCM bikes only)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BoschEBikeLocationCoordinator
from .helpers import extract_bike_name


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Bosch eBike device trackers from a config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    bcm_bike_ids: list[str] = entry_data["bcm_bike_ids"]

    if not bcm_bike_ids or "location_coordinator" not in entry_data:
        return

    coordinator: BoschEBikeLocationCoordinator = entry_data["location_coordinator"]
    bikes: list[dict] = entry_data["bikes"]
    bike_map = {b["id"]: b for b in bikes}

    entities: list[BoschEBikeTracker] = []
    for bike_id in bcm_bike_ids:
        bike = bike_map.get(bike_id, {})
        bike_name = extract_bike_name(bike)
        entities.append(
            BoschEBikeTracker(
                coordinator=coordinator,
                bike_id=bike_id,
                bike_name=bike_name,
            )
        )

    async_add_entities(entities)


class BoschEBikeTracker(CoordinatorEntity[BoschEBikeLocationCoordinator], TrackerEntity):
    """GPS tracker for a Bosch eBike with BCM."""

    _attr_has_entity_name = True
    _attr_name = "Location"
    _attr_device_info: DeviceInfo  # type: ignore[assignment]

    def __init__(
        self,
        coordinator: BoschEBikeLocationCoordinator,
        bike_id: str,
        bike_name: str,
    ) -> None:
        """Initialize the tracker."""
        super().__init__(coordinator)
        self._bike_id = bike_id
        self._attr_unique_id = f"bosch_ebike_{bike_id}_location"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, bike_id)},
            name=f"Bosch eBike {bike_name}",
            manufacturer="Bosch",
        )

    @property
    def source_type(self) -> SourceType:
        """Return the source type."""
        return SourceType.GPS

    def _get_location(self) -> dict[str, Any] | None:
        """Extract the first location from the coordinator response.

        Response shape: {"locations": [{"latitude": ..., "longitude": ...,
        "horizontalAccuracy": ..., "altitude": ..., "createdAt": ..., "detectedAt": ...}]}
        """
        if self.coordinator.data is None:
            return None
        resp = self.coordinator.data.get(self._bike_id)
        if not isinstance(resp, dict):
            return None
        loc_list = resp.get("locations")
        if isinstance(loc_list, list) and loc_list:
            result: dict[str, Any] = loc_list[0]
            return result
        return None

    @property
    def latitude(self) -> float | None:
        """Return latitude."""
        loc = self._get_location()
        if loc is None:
            return None
        return loc.get("latitude")

    @property
    def longitude(self) -> float | None:
        """Return longitude."""
        loc = self._get_location()
        if loc is None:
            return None
        return loc.get("longitude")

    @property
    def location_accuracy(self) -> int:
        """Return the location accuracy in meters."""
        loc = self._get_location()
        if loc is None:
            return 0
        return int(loc.get("horizontalAccuracy") or 0)
