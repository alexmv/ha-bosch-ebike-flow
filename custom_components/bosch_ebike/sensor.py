"""Sensor platform for Bosch eBike Flow."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfLength,
    UnitOfMass,
    UnitOfPower,
    UnitOfSpeed,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import BoschEBikeDataCoordinator
from .helpers import extract_bike_name


@dataclass(frozen=True, kw_only=True)
class BoschEBikeSensorEntityDescription(SensorEntityDescription):
    """Describe a Bosch eBike sensor."""

    value_fn: Callable[[dict[str, Any]], Any]


# --- Value extractors: battery / SoC ---


def _get_battery(data: dict[str, Any]) -> float | None:
    battery = data.get("battery")
    if not isinstance(battery, dict):
        return None
    soc: float | None = battery.get("stateOfCharge")
    if soc is not None:
        return soc
    return battery.get("soc")  # type: ignore[return-value]


# --- Value extractors: profile-based ---


def _get_profile_field(*keys: str) -> Callable[[dict[str, Any]], Any]:
    """Traverse nested profile dict by key path."""

    def _extract(data: dict[str, Any]) -> Any:
        obj = data.get("profile")
        for key in keys:
            if not isinstance(obj, dict):
                return None
            obj = obj.get(key)
        return obj

    return _extract


def _get_battery_field(field: str) -> Callable[[dict[str, Any]], Any]:
    """Get a field from the first battery in the profile."""

    def _extract(data: dict[str, Any]) -> Any:
        profile = data.get("profile")
        if not isinstance(profile, dict):
            return None
        batteries = profile.get("batteries")
        if not isinstance(batteries, list) or not batteries:
            return None
        return batteries[0].get(field)

    return _extract


def _get_charge_cycles(data: dict[str, Any]) -> float | None:
    cycles = _get_battery_field("numberOfFullChargeCycles")(data)
    return cycles.get("total") if isinstance(cycles, dict) else None


# --- Value extractors: ride-based ---


def _get_ride_field(field: str) -> Callable[[dict[str, Any]], Any]:
    def _extract(data: dict[str, Any]) -> Any:
        ride = data.get("latest_ride")
        if ride is None:
            return None
        return ride.get(field)

    return _extract


def _get_ride_timestamp(data: dict[str, Any]) -> datetime | None:
    ride = data.get("latest_ride")
    if ride is None:
        return None
    start_time = ride.get("startTime")
    if not isinstance(start_time, (int, float)):
        return None
    # API returns epoch seconds; guard against milliseconds just in case.
    ts = start_time / 1000 if start_time > 1e12 else start_time
    return datetime.fromtimestamp(ts, tz=UTC)


# --- Sensor descriptions ---

SENSOR_DESCRIPTIONS: tuple[BoschEBikeSensorEntityDescription, ...] = (
    # Profile-based sensors (always available)
    BoschEBikeSensorEntityDescription(
        key="battery",
        name="Battery",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_get_battery,
    ),
    BoschEBikeSensorEntityDescription(
        key="odometer",
        name="Odometer",
        native_unit_of_measurement=UnitOfLength.METERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_get_profile_field("driveUnit", "totalDistanceTraveled"),
    ),
    BoschEBikeSensorEntityDescription(
        key="battery_capacity",
        name="Battery Capacity",
        native_unit_of_measurement="Wh",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_get_battery_field("totalEnergy"),
    ),
    BoschEBikeSensorEntityDescription(
        key="charge_cycles",
        name="Charge Cycles",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_get_charge_cycles,
    ),
    BoschEBikeSensorEntityDescription(
        key="motor_hours",
        name="Motor Hours",
        native_unit_of_measurement=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_get_profile_field("driveUnit", "powerOnTime", "total"),
    ),
    BoschEBikeSensorEntityDescription(
        key="battery_energy_delivered",
        name="Battery Energy Delivered",
        native_unit_of_measurement="Wh",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_get_battery_field("deliveredWhOverLifetime"),
    ),
    # Ride-based sensors (available when activity API works)
    BoschEBikeSensorEntityDescription(
        key="last_ride_distance",
        name="Last Ride Distance",
        native_unit_of_measurement=UnitOfLength.METERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_get_ride_field("distance"),
    ),
    BoschEBikeSensorEntityDescription(
        key="last_ride_duration",
        name="Last Ride Duration",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_get_ride_field("durationWithoutStops"),
    ),
    BoschEBikeSensorEntityDescription(
        key="last_ride_avg_speed",
        name="Last Ride Avg Speed",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_get_ride_field("averageSpeed"),
    ),
    BoschEBikeSensorEntityDescription(
        key="last_ride_max_speed",
        name="Last Ride Max Speed",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_get_ride_field("maximumSpeed"),
    ),
    BoschEBikeSensorEntityDescription(
        key="last_ride_avg_power",
        name="Last Ride Avg Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_get_ride_field("averageRiderPower"),
    ),
    BoschEBikeSensorEntityDescription(
        key="last_ride_calories",
        name="Last Ride Calories",
        native_unit_of_measurement="kcal",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_get_ride_field("caloriesBurnt"),
    ),
    BoschEBikeSensorEntityDescription(
        key="last_ride_co2_saved",
        name="Last Ride CO2 Saved",
        native_unit_of_measurement=UnitOfMass.GRAMS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_get_ride_field("co2EmissionsCarEquivalentGrams"),
    ),
    BoschEBikeSensorEntityDescription(
        key="last_ride_rider_energy_share",
        name="Last Ride Rider Energy",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_get_ride_field("riderEnergyShare"),
    ),
    BoschEBikeSensorEntityDescription(
        key="last_ride_elevation_gain",
        name="Last Ride Elevation Gain",
        native_unit_of_measurement=UnitOfLength.METERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_get_ride_field("elevationGain"),
    ),
    BoschEBikeSensorEntityDescription(
        key="last_ride_timestamp",
        name="Last Ride Time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_get_ride_timestamp,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Bosch eBike sensors from a config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator: BoschEBikeDataCoordinator = entry_data["data_coordinator"]
    bikes: list[dict] = entry_data["bikes"]

    entities: list[BoschEBikeSensor] = []
    for bike in bikes:
        bike_id = bike["id"]
        bike_name = extract_bike_name(bike)
        for description in SENSOR_DESCRIPTIONS:
            entities.append(
                BoschEBikeSensor(
                    coordinator=coordinator,
                    description=description,
                    bike_id=bike_id,
                    bike_name=bike_name,
                )
            )

    async_add_entities(entities)


class BoschEBikeSensor(CoordinatorEntity[BoschEBikeDataCoordinator], SensorEntity):
    """Representation of a Bosch eBike sensor."""

    entity_description: BoschEBikeSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BoschEBikeDataCoordinator,
        description: BoschEBikeSensorEntityDescription,
        bike_id: str,
        bike_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._bike_id = bike_id
        self._attr_unique_id = f"bosch_ebike_{bike_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, bike_id)},
            name=f"Bosch eBike {bike_name}",
            manufacturer="Bosch",
        )

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None
        bike_data = self.coordinator.data.get(self._bike_id)
        if bike_data is None:
            return None
        return self.entity_description.value_fn(bike_data)
