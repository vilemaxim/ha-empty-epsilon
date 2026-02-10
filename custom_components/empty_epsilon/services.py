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
        try:
            ssh, cfg = _get_ssh_and_config(hass, call)
            install_path = cfg.get(CONF_EE_INSTALL_PATH, "/usr/local/bin")
            ee_port = call.data.get("httpserver") or cfg.get(CONF_EE_PORT, 8080)
            scenario = call.data.get("scenario") or DEFAULT_INIT_SCENARIO
            sacn_universe = cfg.get(CONF_SACN_UNIVERSE, 2)
            _LOGGER.info(
                "start_server: host=%s install_path=%s port=%s scenario=%s",
                cfg.get(CONF_SSH_HOST), install_path, ee_port, scenario,
            )
            try:
                deploy_ok = await ssh.deploy_hardware_ini(universe=sacn_universe)
                _LOGGER.info("start_server: deploy_hardware_ini=%s", deploy_ok)
                ok = await ssh.start_server(install_path, ee_port, scenario)
                _LOGGER.info("start_server: start_server result=%s", ok)
                if ok:
                    coord = _get_coordinator(hass, call)
                    await coord.async_request_refresh()
            finally:
                await ssh.disconnect()
        except Exception as e:
            _LOGGER.exception("start_server failed: %s", e)
            raise

    async def stop_server(call: ServiceCall) -> None:
        ssh, _ = _get_ssh_and_config(hass, call)
        try:
            await ssh.stop_server()
            coord = _get_coordinator(hass, call)
            await coord.async_request_refresh()
        finally:
            await ssh.disconnect()

    async def spawn_cpu_ship(call: ServiceCall) -> None:
        coord = _get_coordinator(hass, call)
        await coord.api.spawn_cpu_ship(
            template=call.data.get("template", "Adder MK3"),
            faction=call.data.get("faction", "Kraylor"),
            x=float(call.data.get("x", 0)),
            y=float(call.data.get("y", 0)),
            order=call.data.get("order", "idle"),
        )
        await coord.async_request_refresh()

    async def spawn_station(call: ServiceCall) -> None:
        coord = _get_coordinator(hass, call)
        await coord.api.spawn_station(
            template=call.data.get("template", "Small Station"),
            faction=call.data.get("faction", "Human Navy"),
            x=float(call.data.get("x", 0)),
            y=float(call.data.get("y", 0)),
        )
        await coord.async_request_refresh()

    async def spawn_nebula(call: ServiceCall) -> None:
        coord = _get_coordinator(hass, call)
        await coord.api.spawn_nebula(
            x=float(call.data.get("x", 0)),
            y=float(call.data.get("y", 0)),
        )
        await coord.async_request_refresh()

    async def spawn_asteroid(call: ServiceCall) -> None:
        coord = _get_coordinator(hass, call)
        await coord.api.spawn_asteroid(
            x=float(call.data.get("x", 0)),
            y=float(call.data.get("y", 0)),
        )
        await coord.async_request_refresh()

    async def send_comms_message(call: ServiceCall) -> None:
        coord = _get_coordinator(hass, call)
        await coord.api.send_comms_message(
            callsign=call.data["callsign"],
            message=call.data["message"],
        )
        await coord.async_request_refresh()

    async def modify_hull(call: ServiceCall) -> None:
        coord = _get_coordinator(hass, call)
        await coord.api.modify_hull(
            callsign=call.data["callsign"],
            value=float(call.data.get("value", 100)),
        )
        await coord.async_request_refresh()

    async def modify_shields(call: ServiceCall) -> None:
        coord = _get_coordinator(hass, call)
        await coord.api.modify_shields(
            callsign=call.data["callsign"],
            front=float(call.data.get("front", 100)),
            rear=float(call.data.get("rear", 100)),
        )
        await coord.async_request_refresh()

    async def give_weapons(call: ServiceCall) -> None:
        coord = _get_coordinator(hass, call)
        await coord.api.give_weapons(
            callsign=call.data["callsign"],
            homing=int(call.data.get("homing", 0)),
            nuke=int(call.data.get("nuke", 0)),
            emp=int(call.data.get("emp", 0)),
            mine=int(call.data.get("mine", 0)),
            hvli=int(call.data.get("hvli", 0)),
        )
        await coord.async_request_refresh()

    async def red_alert_all(call: ServiceCall) -> None:
        coord = _get_coordinator(hass, call)
        await coord.api.red_alert_all()
        await coord.async_request_refresh()

    async def resupply_all(call: ServiceCall) -> None:
        coord = _get_coordinator(hass, call)
        await coord.api.resupply_all()
        await coord.async_request_refresh()

    async def repair_all(call: ServiceCall) -> None:
        coord = _get_coordinator(hass, call)
        await coord.api.repair_all()
        await coord.async_request_refresh()

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
    hass.services.async_register(
        DOMAIN,
        "spawn_cpu_ship",
        spawn_cpu_ship,
        schema=vol.Schema({
            vol.Optional("entity_id"): cv.entity_id,
            vol.Optional("device_id"): str,
            vol.Optional("template", default="Adder MK3"): str,
            vol.Optional("faction", default="Kraylor"): str,
            vol.Optional("x", default=0): vol.Coerce(float),
            vol.Optional("y", default=0): vol.Coerce(float),
            vol.Optional("order", default="idle"): vol.In(["idle", "roam"]),
        }),
    )
    hass.services.async_register(
        DOMAIN,
        "spawn_station",
        spawn_station,
        schema=vol.Schema({
            vol.Optional("entity_id"): cv.entity_id,
            vol.Optional("device_id"): str,
            vol.Optional("template", default="Small Station"): str,
            vol.Optional("faction", default="Human Navy"): str,
            vol.Optional("x", default=0): vol.Coerce(float),
            vol.Optional("y", default=0): vol.Coerce(float),
        }),
    )
    hass.services.async_register(
        DOMAIN,
        "spawn_nebula",
        spawn_nebula,
        schema=vol.Schema({
            vol.Optional("entity_id"): cv.entity_id,
            vol.Optional("device_id"): str,
            vol.Optional("x", default=0): vol.Coerce(float),
            vol.Optional("y", default=0): vol.Coerce(float),
        }),
    )
    hass.services.async_register(
        DOMAIN,
        "spawn_asteroid",
        spawn_asteroid,
        schema=vol.Schema({
            vol.Optional("entity_id"): cv.entity_id,
            vol.Optional("device_id"): str,
            vol.Optional("x", default=0): vol.Coerce(float),
            vol.Optional("y", default=0): vol.Coerce(float),
        }),
    )
    hass.services.async_register(
        DOMAIN,
        "send_comms_message",
        send_comms_message,
        schema=vol.Schema({
            vol.Optional("entity_id"): cv.entity_id,
            vol.Optional("device_id"): str,
            vol.Required("callsign"): str,
            vol.Required("message"): str,
        }),
    )
    hass.services.async_register(
        DOMAIN,
        "modify_hull",
        modify_hull,
        schema=vol.Schema({
            vol.Optional("entity_id"): cv.entity_id,
            vol.Optional("device_id"): str,
            vol.Required("callsign"): str,
            vol.Optional("value", default=100): vol.Coerce(float),
        }),
    )
    hass.services.async_register(
        DOMAIN,
        "modify_shields",
        modify_shields,
        schema=vol.Schema({
            vol.Optional("entity_id"): cv.entity_id,
            vol.Optional("device_id"): str,
            vol.Required("callsign"): str,
            vol.Optional("front", default=100): vol.Coerce(float),
            vol.Optional("rear", default=100): vol.Coerce(float),
        }),
    )
    hass.services.async_register(
        DOMAIN,
        "give_weapons",
        give_weapons,
        schema=vol.Schema({
            vol.Optional("entity_id"): cv.entity_id,
            vol.Optional("device_id"): str,
            vol.Required("callsign"): str,
            vol.Optional("homing", default=0): vol.Coerce(int),
            vol.Optional("nuke", default=0): vol.Coerce(int),
            vol.Optional("emp", default=0): vol.Coerce(int),
            vol.Optional("mine", default=0): vol.Coerce(int),
            vol.Optional("hvli", default=0): vol.Coerce(int),
        }),
    )
    hass.services.async_register(
        DOMAIN,
        "red_alert_all",
        red_alert_all,
        schema=vol.Schema({
            vol.Optional("entity_id"): cv.entity_id,
            vol.Optional("device_id"): str,
        }),
    )
    hass.services.async_register(
        DOMAIN,
        "resupply_all",
        resupply_all,
        schema=vol.Schema({
            vol.Optional("entity_id"): cv.entity_id,
            vol.Optional("device_id"): str,
        }),
    )
    hass.services.async_register(
        DOMAIN,
        "repair_all",
        repair_all,
        schema=vol.Schema({
            vol.Optional("entity_id"): cv.entity_id,
            vol.Optional("device_id"): str,
        }),
    )
