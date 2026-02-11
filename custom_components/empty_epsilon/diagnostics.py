"""Diagnostics for EmptyEpsilon integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_EE_HOST, CONF_EE_PORT, CONF_SSH_HOST, CONF_SSH_PASSWORD, CONF_SSH_KEY, DOMAIN
from .ee_api import EEAPIClient, EEAPIError

TO_REDACT = {CONF_SSH_PASSWORD, CONF_SSH_KEY, "ssh_password", "ssh_key"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data: dict[str, Any] = {
        "config_entry": async_redact_data(dict(entry.data), TO_REDACT),
        "options": dict(entry.options or {}),
    }

    # Check if HTTP server is active (exec.lua responding)
    host = entry.data.get(CONF_SSH_HOST, entry.data.get(CONF_EE_HOST, "localhost"))
    port = (entry.options or {}).get(CONF_EE_PORT, entry.data.get(CONF_EE_PORT, 8080))
    base_url = f"http://{host}:{port}"
    api = EEAPIClient(base_url, timeout=5.0)

    try:
        # Simple ping: return "ok" from exec.lua
        await api.exec_lua('return "ok"')
        data["httpserver_active"] = True
    except EEAPIError as e:
        data["httpserver_active"] = False
        data["httpserver_error"] = str(e)
    except Exception as e:
        data["httpserver_active"] = False
        data["httpserver_error"] = str(e)

    # Include coordinator data if available
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator:
        data["last_update_success"] = coordinator.last_update_success
        data["coordinator_data"] = coordinator.data

    return data
