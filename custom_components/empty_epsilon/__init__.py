"""EmptyEpsilon Home Assistant integration."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ENABLE_EXEC_LUA,
    CONF_EE_INSTALL_PATH,
    CONF_EE_PORT,
    CONF_POLL_INTERVAL,
    CONF_SACN_UNIVERSE,
    CONF_SSH_HOST,
    CONF_SSH_KEY,
    CONF_SSH_KNOWN_HOSTS,
    CONF_SSH_PASSWORD,
    CONF_SSH_PORT,
    CONF_SSH_SKIP_HOST_KEY_CHECK,
    CONF_SSH_USERNAME,
    DEFAULT_INIT_SCENARIO,
    DOMAIN,
)
from .coordinator import EmptyEpsilonCoordinator
from .services import async_setup_services
from .ssh_manager import SSHManager

_LOGGER = logging.getLogger(__name__)

# Seconds to wait for EE to boot before first coordinator refresh
EE_STARTUP_DELAY = 8


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the EmptyEpsilon integration (no YAML)."""
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up EmptyEpsilon from a config entry."""
    data = dict(config_entry.data)
    options = config_entry.options or {}
    data[CONF_POLL_INTERVAL] = options.get(CONF_POLL_INTERVAL, 10)
    data[CONF_SACN_UNIVERSE] = options.get(CONF_SACN_UNIVERSE, 2)
    data[CONF_ENABLE_EXEC_LUA] = options.get(CONF_ENABLE_EXEC_LUA, False)

    # Start EE server via SSH before coordinator setup (proves we have full control)
    ssh = SSHManager(
        host=data[CONF_SSH_HOST],
        port=data.get(CONF_SSH_PORT, 22),
        username=data[CONF_SSH_USERNAME],
        password=data.get(CONF_SSH_PASSWORD) or None,
        key_filename=(data.get(CONF_SSH_KEY) or "").strip() or None,
        known_hosts=data.get(CONF_SSH_KNOWN_HOSTS),
        skip_host_key_check=data.get(CONF_SSH_SKIP_HOST_KEY_CHECK, True),
    )
    install_path = data.get(CONF_EE_INSTALL_PATH, "/usr/local/bin")
    ee_port = data.get(CONF_EE_PORT, 8080)
    if await ssh.start_server(install_path, ee_port, DEFAULT_INIT_SCENARIO):
        _LOGGER.info("Waiting %ds for EmptyEpsilon to boot", EE_STARTUP_DELAY)
        await asyncio.sleep(EE_STARTUP_DELAY)
    await ssh.disconnect()

    coordinator = EmptyEpsilonCoordinator(hass, data)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[config_entry.entry_id] = coordinator

    await coordinator.start_sacn()

    await hass.config_entries.async_forward_entry_setups(
        config_entry, ["sensor", "binary_sensor", "switch", "button"]
    )

    if not hass.data.get(DOMAIN + "_services"):
        await async_setup_services(hass)
        hass.data[DOMAIN + "_services"] = True

    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: EmptyEpsilonCoordinator = hass.data[DOMAIN].get(config_entry.entry_id)
    if coordinator:
        coordinator.stop_sacn()
    unload_ok = await hass.config_entries.async_unload_platforms(
        config_entry, ["sensor", "binary_sensor", "switch", "button"]
    )
    if unload_ok and DOMAIN in hass.data:
        hass.data[DOMAIN].pop(config_entry.entry_id, None)
    return unload_ok
