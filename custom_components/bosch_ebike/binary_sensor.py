"""Binary sensor platform for Bosch eBike Flow."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BoschEBikeDataCoordinator
from .helpers import extract_bike_name


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Bosch eBike binary sensors from a config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator: BoschEBikeDataCoordinator = entry_data["data_coordinator"]
    bikes: list[dict] = entry_data["bikes"]

    entities: list[BoschEBikeChargingSensor] = []
    for bike in bikes:
        bike_id = bike["id"]
        bike_name = extract_bike_name(bike)
        entities.append(
            BoschEBikeChargingSensor(
                coordinator=coordinator,
                bike_id=bike_id,
                bike_name=bike_name,
            )
        )

    async_add_entities(entities)


class BoschEBikeChargingSensor(CoordinatorEntity[BoschEBikeDataCoordinator], BinarySensorEntity):
    """Binary sensor that reports whether the bike battery is currently charging."""

    _attr_has_entity_name = True
    _attr_name = "Charging"
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING

    def __init__(
        self,
        coordinator: BoschEBikeDataCoordinator,
        bike_id: str,
        bike_name: str,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._bike_id = bike_id
        self._attr_unique_id = f"bosch_ebike_{bike_id}_charging"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, bike_id)},
            name=f"Bosch eBike {bike_name}",
            manufacturer="Bosch",
        )

    @property
    def is_on(self) -> bool | None:
        """Return true if the battery is charging."""
        if self.coordinator.data is None:
            return None
        bike_data = self.coordinator.data.get(self._bike_id)
        if bike_data is None:
            return None
        battery: Any = bike_data.get("battery")
        if not isinstance(battery, dict):
            return None
        return battery.get("chargingActive")
