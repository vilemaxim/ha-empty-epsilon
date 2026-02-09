"""EmptyEpsilon service handlers."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import config_validation as cv

from .const import CONF_ENABLE_EXEC_LUA, DOMAIN

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
