"""EmptyEpsilon service handlers."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_EE_INSTALL_PATH,
    CONF_EE_PORT,
    CONF_ENABLE_EXEC_LUA,
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
from .ssh_manager import SSHManager

_LOGGER = logging.getLogger(__name__)


def _get_coordinator(hass: HomeAssistant, call: ServiceCall):
    """Resolve target entity or single instance to coordinator. Raises if not found."""
    target = call.data.get("entity_id") or call.data.get("device_id")
    if not target:
        entries = list(hass.data.get(DOMAIN, {}).keys())
        if not entries:
            raise ValueError("No EmptyEpsilon integration configured")
        if len(entries) != 1:
            raise ValueError(
                "Must specify entity_id when multiple EmptyEpsilon instances exist"
            )
        return hass.data[DOMAIN][entries[0]]

    entity_reg = er.async_get(hass)
    entity_id = target if isinstance(target, str) else target[0]
    if entity_id.startswith("device_"):
        dev_reg = hass.helpers.device_registry.async_get(hass)
        device = dev_reg.async_get(entity_id)
        if not device:
            raise ValueError(f"Device {entity_id} not found")
        for ident in device.identifiers:
            if ident[0] == DOMAIN and ident[1] in hass.data.get(DOMAIN, {}):
                return hass.data[DOMAIN][ident[1]]
        raise ValueError(f"Device {entity_id} is not an EmptyEpsilon device")
    entity = entity_reg.async_get(entity_id)
    if not entity or entity.platform.domain != DOMAIN:
        raise ValueError(f"Entity {entity_id} is not an EmptyEpsilon entity")
    return hass.data[DOMAIN][entity.config_entry_id]


def _get_ssh_and_config(hass: HomeAssistant, call: ServiceCall):
    """Get SSHManager and config dict for server management. Uses _get_coordinator logic."""
    coord = _get_coordinator(hass, call)
    cfg = coord._config
    ssh = SSHManager(
        host=cfg[CONF_SSH_HOST],
        port=cfg.get(CONF_SSH_PORT, 22),
        username=cfg[CONF_SSH_USERNAME],
        password=cfg.get(CONF_SSH_PASSWORD) or None,
        key_filename=(cfg.get(CONF_SSH_KEY) or "").strip() or None,
        known_hosts=cfg.get(CONF_SSH_KNOWN_HOSTS),
        skip_host_key_check=cfg.get(CONF_SSH_SKIP_HOST_KEY_CHECK, True),
    )
    return ssh, cfg


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register EmptyEpsilon services."""

    async def global_message(call: ServiceCall) -> None:
        coord = _get_coordinator(hass, call)
        await coord.api.global_message(call.data["message"])
        await coord.async_request_refresh()

    async def victory(call: ServiceCall) -> None:
        coord = _get_coordinator(hass, call)
        await coord.api.victory(call.data.get("faction", "Human Navy"))
        await coord.async_request_refresh()

    async def spawn_player_ship(call: ServiceCall) -> None:
        coord = _get_coordinator(hass, call)
        await coord.api.spawn_player_ship(
            template=call.data.get("template", "Atlantis"),
            callsign=call.data.get("callsign", "Epsilon"),
            faction=call.data.get("faction", "Human Navy"),
            x=float(call.data.get("x", 0)),
            y=float(call.data.get("y", 0)),
        )
        await coord.async_request_refresh()

    async def exec_lua(call: ServiceCall) -> None:
        coord = _get_coordinator(hass, call)
        if not coord._config.get(CONF_ENABLE_EXEC_LUA, False):
            raise ValueError("Execute Lua is disabled. Enable it in integration options.")
        result = await coord.api.exec_lua(call.data["code"])
        _LOGGER.info("exec_lua result: %s", result[:200] if result else "")

    async def start_server(call: ServiceCall) -> None:
        ssh, cfg = _get_ssh_and_config(hass, call)
        install_path = cfg.get(CONF_EE_INSTALL_PATH, "/opt/EmptyEpsilon")
        ee_port = call.data.get("httpserver") or cfg.get(CONF_EE_PORT, 8080)
        scenario = call.data.get("scenario") or DEFAULT_INIT_SCENARIO
        try:
            ok = await ssh.start_server(install_path, ee_port, scenario)
            if ok:
                coord = _get_coordinator(hass, call)
                await coord.async_request_refresh()
        finally:
            await ssh.disconnect()

    async def stop_server(call: ServiceCall) -> None:
        ssh, _ = _get_ssh_and_config(hass, call)
        try:
            await ssh.stop_server()
            coord = _get_coordinator(hass, call)
            await coord.async_request_refresh()
        finally:
            await ssh.disconnect()

    hass.services.async_register(
        DOMAIN,
        "global_message",
        global_message,
        schema=vol.Schema({
            vol.Optional("entity_id"): cv.entity_id,
            vol.Optional("device_id"): str,
            vol.Required("message"): str,
        }),
    )
    hass.services.async_register(
        DOMAIN,
        "victory",
        victory,
        schema=vol.Schema({
            vol.Optional("entity_id"): cv.entity_id,
            vol.Optional("device_id"): str,
            vol.Optional("faction", default="Human Navy"): str,
        }),
    )
    hass.services.async_register(
        DOMAIN,
        "spawn_player_ship",
        spawn_player_ship,
        schema=vol.Schema({
            vol.Optional("entity_id"): cv.entity_id,
            vol.Optional("device_id"): str,
            vol.Optional("template", default="Atlantis"): str,
            vol.Optional("callsign", default="Epsilon"): str,
            vol.Optional("faction", default="Human Navy"): str,
            vol.Optional("x", default=0): vol.Coerce(float),
            vol.Optional("y", default=0): vol.Coerce(float),
        }),
    )
    hass.services.async_register(
        DOMAIN,
        "exec_lua",
        exec_lua,
        schema=vol.Schema({
            vol.Optional("entity_id"): cv.entity_id,
            vol.Optional("device_id"): str,
            vol.Required("code"): str,
        }),
    )
    hass.services.async_register(
        DOMAIN,
        "start_server",
        start_server,
        schema=vol.Schema({
            vol.Optional("entity_id"): cv.entity_id,
            vol.Optional("device_id"): str,
            vol.Optional("scenario", default=DEFAULT_INIT_SCENARIO): str,
            vol.Optional("httpserver"): vol.Coerce(int),
        }),
    )
    hass.services.async_register(
        DOMAIN,
        "stop_server",
        stop_server,
        schema=vol.Schema({
            vol.Optional("entity_id"): cv.entity_id,
            vol.Optional("device_id"): str,
        }),
    )
