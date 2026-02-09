"""Sensors for EmptyEpsilon (game status, hull, shields, scenario time, etc.)."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    GAME_STATUS_GAME_OVER_DEFEAT,
    GAME_STATUS_GAME_OVER_VICTORY,
    GAME_STATUS_PAUSED,
    GAME_STATUS_PLAYING,
    GAME_STATUS_SETUP,
)
from .coordinator import EmptyEpsilonCoordinator
from .entity import EmptyEpsilonEntity


def _game_status_native_value(status: str | None) -> str:
    if not status:
        return GAME_STATUS_SETUP
    return status


def _sensor_state(value, decimals: int = 0) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), decimals)
    except (TypeError, ValueError):
        return None


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EmptyEpsilon sensors from a config entry."""
    coordinator: EmptyEpsilonCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    config = config_entry.data
    entry_id = config_entry.entry_id

    entities: list[SensorEntity] = []

    # Game status (required)
    entities.append(
        EmptyEpsilonGameStatusSensor(coordinator, entry_id, "game_status", "Game status")
    )
    entities.append(
        EmptyEpsilonPlayerShipCountSensor(
            coordinator, entry_id, "player_ship_count", "Player ship count"
        )
    )

    # Server-level from HTTP
    entities.append(
        EmptyEpsilonScenarioTimeSensor(
            coordinator, entry_id, "scenario_time", "Scenario time"
        )
    )
    entities.append(
        EmptyEpsilonSensor(
            coordinator, entry_id, "active_scenario", "Active scenario",
            icon="mdi:file-document-outline"
        )
    )
    entities.append(
        EmptyEpsilonSensor(
            coordinator, entry_id, "total_objects", "Total objects",
            unit="objects", icon="mdi:counter", state_class=SensorStateClass.MEASUREMENT
        )
    )
    entities.append(
        EmptyEpsilonSensor(
            coordinator, entry_id, "enemy_ship_count", "Enemy ships",
            unit="ships", icon="mdi:target", state_class=SensorStateClass.MEASUREMENT
        )
    )
    entities.append(
        EmptyEpsilonSensor(
            coordinator, entry_id, "friendly_station_count", "Friendly stations",
            unit="stations", icon="mdi:domain", state_class=SensorStateClass.MEASUREMENT
        )
    )

    # Primary ship from HTTP (callsign, type, sector, ammo)
    entities.append(
        EmptyEpsilonPrimaryShipSensor(
            coordinator, entry_id, "callsign", "Callsign", icon="mdi:badge-account"
        )
    )
    entities.append(
        EmptyEpsilonPrimaryShipSensor(
            coordinator, entry_id, "ship_type", "Ship type", icon="mdi:ship-wheel"
        )
    )
    entities.append(
        EmptyEpsilonPrimaryShipSensor(
            coordinator, entry_id, "sector", "Sector", icon="mdi:map-marker"
        )
    )
    entities.append(
        EmptyEpsilonPrimaryShipSensor(
            coordinator, entry_id, "homing", "Homing missiles",
            numeric=True, icon="mdi:missile"
        )
    )
    entities.append(
        EmptyEpsilonPrimaryShipSensor(
            coordinator, entry_id, "nuke", "Nukes",
            numeric=True, icon="mdi:atom"
        )
    )
    entities.append(
        EmptyEpsilonPrimaryShipSensor(
            coordinator, entry_id, "emp", "EMPs",
            numeric=True, icon="mdi:flash"
        )
    )
    entities.append(
        EmptyEpsilonPrimaryShipSensor(
            coordinator, entry_id, "mine", "Mines",
            numeric=True, icon="mdi:land-mine-on"
        )
    )
    entities.append(
        EmptyEpsilonPrimaryShipSensor(
            coordinator, entry_id, "hvli", "HVLIs",
            numeric=True, icon="mdi:bullet"
        )
    )
    entities.append(
        EmptyEpsilonPrimaryShipSensor(
            coordinator, entry_id, "reputation", "Reputation",
            numeric=True, icon="mdi:star"
        )
    )

    # Primary ship from sACN (hull, shields, energy, impulse, warp)
    entities.append(
        EmptyEpsilonSACNSensor(
            coordinator, entry_id, "hull", "Hull", PERCENTAGE, 0, 100
        )
    )
    entities.append(
        EmptyEpsilonSACNSensor(
            coordinator, entry_id, "frontShield", "Front shields", PERCENTAGE, 0, 100
        )
    )
    entities.append(
        EmptyEpsilonSACNSensor(
            coordinator, entry_id, "rearShield", "Rear shields", PERCENTAGE, 0, 100
        )
    )
    entities.append(
        EmptyEpsilonSACNSensor(
            coordinator, entry_id, "energy", "Energy", PERCENTAGE, 0, 100
        )
    )
    entities.append(
        EmptyEpsilonSACNSensor(
            coordinator, entry_id, "impulse", "Impulse", None, 0, 100
        )
    )
    entities.append(
        EmptyEpsilonSACNSensor(
            coordinator, entry_id, "warp", "Warp", None, 0, 100
        )
    )

    async_add_entities(entities)


class EmptyEpsilonGameStatusSensor(EmptyEpsilonEntity, SensorEntity):
    """Game status: setup, playing, paused, game_over_victory, game_over_defeat."""

    _attr_translation_key = "game_status"

    def __init__(self, coordinator, entry_id, key, name):
        super().__init__(coordinator, entry_id, key, name, icon="mdi:gamepad-variant")

    @property
    def native_value(self) -> str:
        return _game_status_native_value(self.coordinator.data.get("game_status"))

    @property
    def native_unit_of_measurement(self) -> None:
        return None


class EmptyEpsilonPlayerShipCountSensor(EmptyEpsilonEntity, SensorEntity):
    """Number of active player ships."""

    _attr_native_unit_of_measurement = "ships"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry_id, key, name):
        super().__init__(coordinator, entry_id, key, name, icon="mdi:ship")

    @property
    def native_value(self) -> int | None:
        count = self.coordinator.data.get("http", {}).get("player_ship_count")
        return int(count) if count is not None else 0


class EmptyEpsilonSensor(EmptyEpsilonEntity, SensorEntity):
    """Generic sensor reading from coordinator.data['http'][key]."""

    def __init__(
        self,
        coordinator,
        entry_id,
        key: str,
        name: str,
        unit: str | None = None,
        icon: str | None = None,
        state_class: str | None = None,
    ):
        super().__init__(coordinator, entry_id, key, name, icon=icon)
        self._unit = unit
        self._key = key
        self._state_class = state_class
        self._attr_translation_key = key

    @property
    def native_value(self) -> str | int | float | None:
        val = self.coordinator.data.get("http", {}).get(self._key)
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return val
        return str(val)

    @property
    def native_unit_of_measurement(self) -> str | None:
        return self._unit

    @property
    def state_class(self) -> str | None:
        return self._state_class


class EmptyEpsilonPrimaryShipSensor(EmptyEpsilonEntity, SensorEntity):
    """Sensor for primary ship data from coordinator.data['http']['primary_ship']."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator,
        entry_id,
        key: str,
        name: str,
        numeric: bool = False,
        icon: str | None = None,
    ):
        super().__init__(coordinator, entry_id, key, name, icon=icon)
        self._key = key
        self._numeric = numeric
        self._attr_translation_key = key

    @property
    def native_value(self) -> str | int | None:
        ship = self.coordinator.data.get("http", {}).get("primary_ship") or {}
        val = ship.get(self._key)
        if val is None:
            return None
        if self._numeric:
            return int(val) if isinstance(val, (int, float)) else (int(val) if str(val).isdigit() else 0)
        return str(val)

    @property
    def native_unit_of_measurement(self) -> str | None:
        return None

    @property
    def state_class(self) -> str | None:
        return SensorStateClass.MEASUREMENT if self._numeric else None


class EmptyEpsilonScenarioTimeSensor(EmptyEpsilonEntity, SensorEntity):
    """Elapsed scenario time in seconds."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = "s"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coordinator, entry_id, key, name):
        super().__init__(coordinator, entry_id, key, name, icon="mdi:clock-outline")

    @property
    def native_value(self) -> float | None:
        return _sensor_state(self.coordinator.data.get("http", {}).get("scenario_time"), 1)


class EmptyEpsilonSACNSensor(EmptyEpsilonEntity, SensorEntity):
    """Sensor from sACN channel (0.0–1.0 mapped to native range)."""

    def __init__(
        self,
        coordinator,
        entry_id,
        key: str,
        name: str,
        unit: str | None,
        min_val: float,
        max_val: float,
    ):
        super().__init__(coordinator, entry_id, key, name)
        self._unit = unit
        self._min_val = min_val
        self._max_val = max_val

    @property
    def native_value(self) -> float | None:
        sacn = self.coordinator.data.get("sacn", {})
        raw = sacn.get(self._key)
        if raw is None:
            return None
        # raw is 0.0–1.0 from sACN
        val = self._min_val + raw * (self._max_val - self._min_val)
        return _sensor_state(val, 1)

    @property
    def native_unit_of_measurement(self) -> str | None:
        return self._unit

    @property
    def state_class(self) -> str | None:
        return SensorStateClass.MEASUREMENT if self._unit else None
