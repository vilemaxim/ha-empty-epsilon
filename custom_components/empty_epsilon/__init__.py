"""EmptyEpsilon Home Assistant integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_EE_HOST,
    CONF_EE_PORT,
    CONF_POLL_INTERVAL,
    CONF_SACN_UNIVERSE,
    DOMAIN,
)
from .coordinator import EmptyEpsilonCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the EmptyEpsilon integration (no YAML)."""
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up EmptyEpsilon from a config entry."""
    data = dict(config_entry.data)
    options = config_entry.options or {}
    data[CONF_POLL_INTERVAL] = options.get(CONF_POLL_INTERVAL, 10)
    data[CONF_SACN_UNIVERSE] = options.get(CONF_SACN_UNIVERSE, 2)

    coordinator = EmptyEpsilonCoordinator(hass, data)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[config_entry.entry_id] = coordinator

    await coordinator.start_sacn()

    hass.config_entries.async_setup_platforms(config_entry, ["sensor", "binary_sensor"])

    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: EmptyEpsilonCoordinator = hass.data[DOMAIN].get(config_entry.entry_id)
    if coordinator:
        coordinator.stop_sacn()
    unload_ok = await hass.config_entries.async_unload_platforms(
        config_entry, ["sensor", "binary_sensor"]
    )
    if unload_ok and DOMAIN in hass.data:
        hass.data[DOMAIN].pop(config_entry.entry_id, None)
    return unload_ok
