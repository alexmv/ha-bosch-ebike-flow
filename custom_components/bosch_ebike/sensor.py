"""Sensor platform for Bosch eBike Flow."""

from __future__ import annotations

import re
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
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


# --- Value extractors: battery / SoC ---


def _get_battery(data: dict[str, Any]) -> float | None:
    battery = data.get("battery")
    if isinstance(battery, dict):
        soc: float | None = battery.get("stateOfCharge")
        if soc is None:
            soc = battery.get("soc")
        if soc is not None:
            return soc
    # No live state of charge (e.g. the SoC endpoint 404s when the bike has
    # been offline); fall back to the level last recorded in the profile.
    level: float | None = _get_battery_field("batteryLevel")(data)
    return level


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


def _get_odometer(data: dict[str, Any]) -> float | None:
    """Total distance, from whichever of SoC and profile is further along.

    The SoC endpoint's odometer is updated by the ConnectModule and is usually
    fresher than the profile's.  But the sensor is TOTAL_INCREASING, where any
    decrease reads as a meter reset, so never let switching sources make the
    value go backwards.
    """
    battery = data.get("battery")
    readings = [
        battery.get("odometer") if isinstance(battery, dict) else None,
        _get_profile_field("driveUnit", "totalDistanceTraveled")(data),
    ]
    known = [float(r) for r in readings if isinstance(r, (int, float))]
    return max(known) if known else None


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


# --- Value extractors: range estimate ---

# The reachableRange array from the SoC API (in km) lines up with the bike's
# assist modes, as listed in the profile's driveUnit.driveUnitAssistModes,
# minus the "0" (OFF) mode.  Which modes a bike has, and in what order,
# depends on the drive unit.  If the profile does not list them, assume the
# common ECO/AUTO/SPORT/TURBO layout.
_DEFAULT_RANGE_MODES = (("eco", False), ("auto", True), ("sport", False), ("turbo", False))


def _profile_assist_modes(data: dict[str, Any]) -> list[dict[str, Any]] | None:
    """The profile's assist modes, minus OFF, or None if it does not list them."""
    profile = data.get("profile")
    drive_unit = profile.get("driveUnit") if isinstance(profile, dict) else None
    modes = drive_unit.get("driveUnitAssistModes") if isinstance(drive_unit, dict) else None
    if not isinstance(modes, list):
        return None
    return [
        mode
        for mode in modes
        if isinstance(mode, dict) and isinstance(mode.get("id"), str) and mode["id"] != "0"
    ]


def _get_ranges(data: dict[str, Any]) -> list[Any] | None:
    battery = data.get("battery")
    ranges = battery.get("reachableRange") if isinstance(battery, dict) else None
    if isinstance(ranges, list):
        return ranges
    # No live SoC (e.g. the bike has been offline for a while); fall back to
    # the per-mode ranges from the profile, as of its last sync.
    modes = _profile_assist_modes(data)
    if not modes:
        return None
    return [mode.get("reachableRange") for mode in modes]


def _assist_mode_names(data: dict[str, Any]) -> dict[str, str]:
    """Map assist mode IDs to their display names, as recorded on the last ride."""
    ride = data.get("latest_ride")
    usage = ride.get("assistModeUsage") if isinstance(ride, dict) else None
    if not isinstance(usage, list):
        return {}
    return {
        u["assistModeConfigId"]: u["name"]
        for u in usage
        if isinstance(u, dict)
        and isinstance(u.get("assistModeConfigId"), str)
        and isinstance(u.get("name"), str)
    }


def _range_modes(data: dict[str, Any]) -> tuple[tuple[str, bool], ...]:
    """Return (attribute-name, is-auto) for each entry in reachableRange."""
    modes = _profile_assist_modes(data)
    if modes is None:
        return _DEFAULT_RANGE_MODES
    names = _assist_mode_names(data)
    result = []
    for mode in modes:
        mode_id = mode["id"]
        name = names.get(mode_id, mode_id).lower().replace("+", "_plus")
        result.append((re.sub(r"[^a-z0-9_]+", "_", name), mode_id.endswith("AUTO")))
    return tuple(result)


def _get_range_auto(data: dict[str, Any]) -> float | None:
    """Range in AUTO mode, or the longest range if the bike has no AUTO mode."""
    ranges = _get_ranges(data)
    if not ranges:
        return None
    modes = _range_modes(data)
    if any(is_auto for _, is_auto in modes):
        for (_, is_auto), km in zip(modes, ranges, strict=False):
            if is_auto:
                return float(km) if km is not None else None
        return None
    known = [km for km in ranges if isinstance(km, (int, float))]
    return float(max(known)) if known else None


def _get_range_attrs(data: dict[str, Any]) -> dict[str, Any]:
    ranges = _get_ranges(data)
    if ranges is None:
        return {}
    return {
        f"range_{name}_km": km for (name, _), km in zip(_range_modes(data), ranges, strict=False)
    }


# --- Value extractors: ride-based ---


def _get_ride_field(field: str) -> Callable[[dict[str, Any]], Any]:
    def _extract(data: dict[str, Any]) -> Any:
        ride = data.get("latest_ride")
        if ride is None:
            return None
        return ride.get(field)

    return _extract


def _get_ride_co2_saved(data: dict[str, Any]) -> float | None:
    """CO2 saved relative to making the same trip by car.

    The API reports the car-equivalent emissions and the ride's own emissions
    (from charging the battery) separately; the saving is the difference.
    """
    ride = data.get("latest_ride")
    if ride is None:
        return None
    car = ride.get("co2EmissionsCarEquivalentGrams")
    ebike = ride.get("co2EmissionsGrams")
    if not isinstance(car, (int, float)) or not isinstance(ebike, (int, float)):
        return None
    return round(car - ebike, 3)


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
        value_fn=_get_odometer,
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
    BoschEBikeSensorEntityDescription(
        key="estimated_range",
        name="Estimated Range",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_get_range_auto,
        attrs_fn=_get_range_attrs,
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
        value_fn=_get_ride_co2_saved,
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
        bike_data = self._bike_data()
        if bike_data is None:
            return None
        return self.entity_description.value_fn(bike_data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra state attributes, if the description provides them."""
        if self.entity_description.attrs_fn is None:
            return None
        bike_data = self._bike_data()
        if bike_data is None:
            return None
        return self.entity_description.attrs_fn(bike_data)

    def _bike_data(self) -> dict[str, Any] | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._bike_id)
