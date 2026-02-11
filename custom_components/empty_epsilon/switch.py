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
        # Optimistic state: when user toggles, show the new state immediately until
        # coordinator refresh returns real data (avoids stale/wrong state from immediate refresh).
        self._optimistic_paused: bool | None = None

    @property
    def is_on(self) -> bool:
        """Return True if game is paused."""
        if self._optimistic_paused is not None:
            return self._optimistic_paused
        return bool(self.coordinator.data.get("http", {}).get("paused"))

    def _handle_coordinator_update(self) -> None:
        """Clear optimistic state when we get real data."""
        self._optimistic_paused = None
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs) -> None:
        """Pause the game."""
        await self.coordinator.api.pause_game()
        self._optimistic_paused = True
        self.async_write_ha_state()
        # Delayed refresh so EE has time to process; coordinator will report real state
        self.hass.loop.call_later(1.5, self._delayed_refresh)

    async def async_turn_off(self, **kwargs) -> None:
        """Unpause the game."""
        await self.coordinator.api.unpause_game()
        self._optimistic_paused = False
        self.async_write_ha_state()
        self.hass.loop.call_later(1.5, self._delayed_refresh)

    def _delayed_refresh(self) -> None:
        """Request coordinator refresh after EE has processed pause/unpause."""
        self.hass.async_create_task(self.coordinator.async_request_refresh())
