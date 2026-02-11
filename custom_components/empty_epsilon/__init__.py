"""EmptyEpsilon Home Assistant integration."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_EE_HOST,
    CONF_EE_INSTALL_PATH,
    CONF_EE_PORT,
    CONF_HEADLESS_INTERNET,
    CONF_HEADLESS_NAME,
    CONF_SCENARIO,
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
from .diagnostics import async_get_config_entry_diagnostics
from .services import async_setup_services
from .ssh_manager import SSHManager

__all__ = ["async_get_config_entry_diagnostics", "async_setup", "async_setup_entry", "async_unload_entry"]

_LOGGER = logging.getLogger(__name__)

EE_STARTUP_DELAY = 8
# Option key: True after we've auto-started once (so we skip on HA restart)
OPTION_HAS_AUTO_STARTED = "has_auto_started_once"


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the EmptyEpsilon integration (no YAML)."""
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up EmptyEpsilon from a config entry."""
    data = dict(config_entry.data)
    options = config_entry.options or {}
    # EE API always uses the same host as SSH
    data[CONF_EE_HOST] = data.get(CONF_SSH_HOST, data.get(CONF_EE_HOST, "localhost"))
    data[CONF_POLL_INTERVAL] = options.get(CONF_POLL_INTERVAL, 10)
    data[CONF_SACN_UNIVERSE] = options.get(CONF_SACN_UNIVERSE, 2)
    if CONF_EE_INSTALL_PATH in options:
        data[CONF_EE_INSTALL_PATH] = options[CONF_EE_INSTALL_PATH]
    data[CONF_HEADLESS_NAME] = options.get(CONF_HEADLESS_NAME, "EmptyEpsilon")
    data[CONF_HEADLESS_INTERNET] = options.get(CONF_HEADLESS_INTERNET, False)
    data[CONF_SCENARIO] = options.get(CONF_SCENARIO, DEFAULT_INIT_SCENARIO)

    # Auto-start EE only on first setup (not on HA restart)
    if not options.get(OPTION_HAS_AUTO_STARTED, False):
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
        sacn_universe = data.get(CONF_SACN_UNIVERSE, 2)
        await ssh.deploy_hardware_ini(universe=sacn_universe)
        headless_name = data.get(CONF_HEADLESS_NAME, "EmptyEpsilon")
        headless_internet = data.get(CONF_HEADLESS_INTERNET, False)
        scenario = data.get(CONF_SCENARIO, DEFAULT_INIT_SCENARIO)
        if await ssh.start_server(
            install_path, ee_port, scenario,
            headless_name=headless_name,
            headless_internet=headless_internet,
        ):
            _LOGGER.info("Waiting %ds for EmptyEpsilon to boot", EE_STARTUP_DELAY)
            await asyncio.sleep(EE_STARTUP_DELAY)
        await ssh.disconnect()
        hass.config_entries.async_update_entry(
            config_entry,
            options={**options, OPTION_HAS_AUTO_STARTED: True},
        )

    # Remove orphaned Active scenario entity (no EE API to get scenario name)
    entity_reg = er.async_get(hass)
    active_scenario_id = entity_reg.async_get_entity_id(
        "sensor", DOMAIN, f"{config_entry.entry_id}_active_scenario"
    )
    if active_scenario_id:
        entity_reg.async_remove(active_scenario_id)
        _LOGGER.debug("Removed orphaned entity %s", active_scenario_id)

    coordinator = EmptyEpsilonCoordinator(hass, data)
    _LOGGER.info(
        "EmptyEpsilon setup: EE API at http://%s:%s",
        data.get(CONF_EE_HOST, "?"),
        data.get(CONF_EE_PORT, 8080),
    )
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
