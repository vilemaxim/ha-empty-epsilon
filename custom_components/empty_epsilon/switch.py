"""Switch for EmptyEpsilon (pause/unpause)."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
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
    """Set up EmptyEpsilon switches from a config entry."""
    coordinator: EmptyEpsilonCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    entry_id = config_entry.entry_id

    async_add_entities([
        EmptyEpsilonPauseSwitch(coordinator, entry_id),
    ])


class EmptyEpsilonPauseSwitch(EmptyEpsilonEntity, SwitchEntity):
    """Switch to pause/unpause the game."""

    _attr_translation_key = "pause"
    _attr_icon = "mdi:pause"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "pause", "Pause", "mdi:pause")

    @property
    def is_on(self) -> bool:
        """Return True if game is paused."""
        return bool(self.coordinator.data.get("http", {}).get("paused"))

    async def async_turn_on(self, **kwargs) -> None:
        """Pause the game."""
        await self.coordinator.api.pause_game()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        """Unpause the game."""
        await self.coordinator.api.unpause_game()
        await self.coordinator.async_request_refresh()
