"""Base entity for EmptyEpsilon with shared DeviceInfo."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN


class EmptyEpsilonEntity(Entity):
    """Base class for EmptyEpsilon entities with device info."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator,
        config_entry_id: str,
        key: str,
        name: str,
        icon: str | None = None,
    ) -> None:
        self.coordinator = coordinator
        self._config_entry_id = config_entry_id
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"{config_entry_id}_{key}"
        if icon:
            self._attr_icon = icon

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._config_entry_id)},
            name="EmptyEpsilon Server",
            manufacturer="Empty Epsilon",
            configuration_url=f"http://{self.coordinator._config.get('ee_host', '')}:{self.coordinator._config.get('ee_port', 8080)}",
        )

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_coordinator_update))

    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
