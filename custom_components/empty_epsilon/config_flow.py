"""Config flow for EmptyEpsilon integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_EE_HOST,
    CONF_EE_INSTALL_PATH,
    CONF_EE_PORT,
    CONF_ENABLE_EXEC_LUA,
    CONF_POLL_INTERVAL,
    CONF_SACN_UNIVERSE,
    CONF_SCENARIO_PATH,
    CONF_SSH_HOST,
    CONF_SSH_KEY,
    CONF_SSH_PASSWORD,
    CONF_SSH_PORT,
    CONF_SSH_USERNAME,
    DEFAULT_HTTP_PORT,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_SACN_UNIVERSE,
    DEFAULT_SSH_PORT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_HTTP = "http"
STEP_SSH = "ssh"
STEP_OPTIONS = "options"

HTTP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EE_HOST): str,
        vol.Required(CONF_EE_PORT, default=DEFAULT_HTTP_PORT): vol.All(
            vol.Coerce(int), vol.Range(1, 65535)
        ),
    }
)

SSH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SSH_HOST): str,
        vol.Required(CONF_SSH_PORT, default=DEFAULT_SSH_PORT): vol.All(
            vol.Coerce(int), vol.Range(1, 65535)
        ),
        vol.Required(CONF_SSH_USERNAME): str,
        vol.Required(CONF_SSH_PASSWORD, default=""): str,
        vol.Optional(CONF_SSH_KEY, default=""): str,
        vol.Optional(CONF_EE_INSTALL_PATH, default="/opt/EmptyEpsilon"): str,
        vol.Optional(CONF_SCENARIO_PATH, default="/config/empty_epsilon/scenarios"): str,
    }
)


async def _validate_http(hass: HomeAssistant, host: str, port: int) -> str | None:
    """Validate HTTP connection to EE server. Returns error string or None."""
    try:
        from .ee_api import EEAPIClient

        client = EEAPIClient(f"http://{host}:{port}")
        result = await client.exec_lua("return 'ok'")
        if result == "ok":
            return None
        return "unexpected_response"
    except Exception as e:
        _LOGGER.debug("HTTP validation failed: %s", e)
        return "cannot_connect"


class EmptyEpsilonConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EmptyEpsilon."""

    VERSION = 1

    def __init__(self) -> None:
        self._http_data: dict[str, Any] = {}
        self._ssh_data: dict[str, Any] | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step (HTTP connection)."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=HTTP_SCHEMA,
                description_placeholders={
                    "warning": "The EE HTTP API has no built-in authentication. "
                    "Restrict access with a firewall (e.g. only allow your Home Assistant IP)."
                },
            )

        error = await _validate_http(
            self.hass,
            user_input[CONF_EE_HOST],
            user_input[CONF_EE_PORT],
        )
        if error:
            return self.async_show_form(
                step_id="user",
                data_schema=HTTP_SCHEMA,
                errors={"base": error},
            )

        self._http_data = dict(user_input)
        return await self.async_step_ssh()

    async def async_step_ssh(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Optional SSH step for server management."""
        if user_input is None:
            return self.async_show_form(
                step_id="ssh",
                data_schema=SSH_SCHEMA,
                description_placeholders={
                    "optional": "Optional. Skip or leave SSH host empty to configure later."
                },
            )

        ssh_host = (user_input.get(CONF_SSH_HOST) or "").strip()
        if not ssh_host:
            self._ssh_data = {}
        else:
            self._ssh_data = dict(user_input)

        return self._create_entry()

    def _create_entry(self) -> FlowResult:
        data = {**self._http_data}
        if self._ssh_data:
            data[CONF_SSH_HOST] = self._ssh_data.get(CONF_SSH_HOST, "")
            data[CONF_SSH_PORT] = self._ssh_data.get(CONF_SSH_PORT, DEFAULT_SSH_PORT)
            data[CONF_SSH_USERNAME] = self._ssh_data.get(CONF_SSH_USERNAME, "")
            data[CONF_SSH_PASSWORD] = self._ssh_data.get(CONF_SSH_PASSWORD, "")
            data[CONF_SSH_KEY] = self._ssh_data.get(CONF_SSH_KEY, "")
            data[CONF_EE_INSTALL_PATH] = self._ssh_data.get(
                CONF_EE_INSTALL_PATH, "/opt/EmptyEpsilon"
            )
            data[CONF_SCENARIO_PATH] = self._ssh_data.get(
                CONF_SCENARIO_PATH, "/config/empty_epsilon/scenarios"
            )
        else:
            data[CONF_SSH_HOST] = ""
            data[CONF_SSH_PORT] = DEFAULT_SSH_PORT
            data[CONF_SSH_USERNAME] = ""
            data[CONF_SSH_PASSWORD] = ""
            data[CONF_SSH_KEY] = ""
            data[CONF_EE_INSTALL_PATH] = "/opt/EmptyEpsilon"
            data[CONF_SCENARIO_PATH] = "/config/empty_epsilon/scenarios"

        return self.async_create_entry(
            title=f"EmptyEpsilon @ {self._http_data.get(CONF_EE_HOST, '')}",
            data=data,
            options={
                CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
                CONF_SACN_UNIVERSE: DEFAULT_SACN_UNIVERSE,
                CONF_ENABLE_EXEC_LUA: False,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> EmptyEpsilonOptionsFlow:
        return EmptyEpsilonOptionsFlow(config_entry)


class EmptyEpsilonOptionsFlow(config_entries.OptionsFlow):
    """Handle EmptyEpsilon options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options or {}
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_POLL_INTERVAL,
                    default=options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(5, 120)),
                vol.Optional(
                    CONF_SACN_UNIVERSE,
                    default=options.get(CONF_SACN_UNIVERSE, DEFAULT_SACN_UNIVERSE),
                ): vol.All(vol.Coerce(int), vol.Range(1, 63999)),
                vol.Optional(
                    CONF_ENABLE_EXEC_LUA,
                    default=options.get(CONF_ENABLE_EXEC_LUA, False),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
