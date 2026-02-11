"""Binary sensors for EmptyEpsilon (server reachable, has ship, game paused)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import EmptyEpsilonCoordinator
from .entity import EmptyEpsilonEntity


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EmptyEpsilon binary sensors from a config entry."""
    coordinator: EmptyEpsilonCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    config = config_entry.data
    entry_id = config_entry.entry_id

    entities = [
        EmptyEpsilonServerReachableSensor(coordinator, entry_id, config),
        EmptyEpsilonHTTPServerSensor(coordinator, entry_id, config),
        EmptyEpsilonHasShipSensor(coordinator, entry_id, config),
        EmptyEpsilonGamePausedSensor(coordinator, entry_id, config),
        EmptyEpsilonSACNBinarySensor(coordinator, entry_id, "shieldsUp", "Shields up", "mdi:shield"),
        EmptyEpsilonSACNBinarySensor(coordinator, entry_id, "docked", "Docked", "mdi:anchor"),
        EmptyEpsilonSACNBinarySensor(coordinator, entry_id, "docking", "Docking", "mdi:ship-wheel"),
    ]
    async_add_entities(entities)


class EmptyEpsilonServerReachableSensor(EmptyEpsilonEntity, BinarySensorEntity):
    """Whether the EE server is reachable (HTTP responding or sACN packets)."""

    _attr_translation_key = "online"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id, config):
        super().__init__(
            coordinator, entry_id, "server_reachable", "Online", "mdi:server-network"
        )

    @property
    def is_on(self) -> bool:
        http = self.coordinator.data.get("http", {})
        if http.get("server_reachable"):
            return True
        # If we have recent sACN data with hasShip or any channel, consider reachable
        sacn = self.coordinator.data.get("sacn", {})
        return bool(sacn and (sacn.get("hasShip", 0) > 0.5 or sacn.get("hull", 0) >= 0))


class EmptyEpsilonHTTPServerSensor(EmptyEpsilonEntity, BinarySensorEntity):
    """Whether the EE HTTP server (exec.lua) is responding."""

    _attr_translation_key = "httpserver"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id, config):
        super().__init__(
            coordinator, entry_id, "httpserver", "HTTP server", "mdi:server-network"
        )

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("http", {}).get("server_reachable"))


class EmptyEpsilonHasShipSensor(EmptyEpsilonEntity, BinarySensorEntity):
    """Whether a player ship exists (from sACN HasShip)."""

    _attr_translation_key = "has_ship"

    def __init__(self, coordinator, entry_id, config):
        super().__init__(coordinator, entry_id, "has_ship", "Has ship", "mdi:ship")

    @property
    def is_on(self) -> bool:
        sacn = self.coordinator.data.get("sacn", {})
        return (sacn.get("hasShip") or 0) > 0.5


class EmptyEpsilonSACNBinarySensor(EmptyEpsilonEntity, BinarySensorEntity):
    """Binary sensor from sACN channel (0.0–1.0, threshold 0.5)."""

    def __init__(self, coordinator, entry_id, config, key: str, name: str, icon: str | None = None):
        super().__init__(coordinator, entry_id, key, name, icon=icon)
        self._key = key
        self._attr_translation_key = key

    @property
    def is_on(self) -> bool:
        sacn = self.coordinator.data.get("sacn", {})
        return (sacn.get(self._key) or 0) > 0.5


class EmptyEpsilonGamePausedSensor(EmptyEpsilonEntity, BinarySensorEntity):
    """Whether the game is paused (from HTTP API)."""

    _attr_translation_key = "game_paused"

    def __init__(self, coordinator, entry_id, config):
        super().__init__(coordinator, entry_id, "game_paused", "Game paused", "mdi:pause")

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("http", {}).get("paused"))
