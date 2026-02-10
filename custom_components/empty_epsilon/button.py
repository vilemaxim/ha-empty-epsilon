"""Buttons for EmptyEpsilon quick GM actions."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
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
    """Set up EmptyEpsilon buttons from a config entry."""
    coordinator: EmptyEpsilonCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    entry_id = config_entry.entry_id

    async_add_entities([
        EmptyEpsilonRedAlertButton(coordinator, entry_id),
        EmptyEpsilonResupplyButton(coordinator, entry_id),
        EmptyEpsilonRepairButton(coordinator, entry_id),
    ])


class EmptyEpsilonRedAlertButton(EmptyEpsilonEntity, ButtonEntity):
    """Button to set all player ships to red alert."""

    _attr_translation_key = "red_alert_all"
    _attr_icon = "mdi:alert"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "red_alert_all", "Red alert all", "mdi:alert")

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.api.red_alert_all()
        await self.coordinator.async_request_refresh()


class EmptyEpsilonResupplyButton(EmptyEpsilonEntity, ButtonEntity):
    """Button to resupply all player ships (ammo + energy)."""

    _attr_translation_key = "resupply_all"
    _attr_icon = "mdi:package-variant-closed"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "resupply_all", "Resupply all", "mdi:package-variant-closed")

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.api.resupply_all()
        await self.coordinator.async_request_refresh()


class EmptyEpsilonRepairButton(EmptyEpsilonEntity, ButtonEntity):
    """Button to repair all player ships (hull + shields)."""

    _attr_translation_key = "repair_all"
    _attr_icon = "mdi:wrench"

    def __init__(self, coordinator, entry_id: str) -> None:
        super().__init__(coordinator, entry_id, "repair_all", "Repair all", "mdi:wrench")

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.coordinator.api.repair_all()
        await self.coordinator.async_request_refresh()
