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

# Step 1: SSH (required for server management)
SSH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SSH_HOST): str,
        vol.Required(CONF_SSH_PORT, default=DEFAULT_SSH_PORT): vol.All(
            vol.Coerce(int), vol.Range(1, 65535)
        ),
        vol.Required(CONF_SSH_USERNAME): str,
        vol.Optional(CONF_SSH_PASSWORD, default=""): str,
        vol.Optional(CONF_SSH_KEY, default=""): str,
    }
)

# Step 2: EE server configuration
EE_SERVER_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_EE_HOST, default=""): str,
        vol.Optional(CONF_EE_PORT, default=DEFAULT_HTTP_PORT): vol.All(
            vol.Coerce(int), vol.Range(1, 65535)
        ),
        vol.Optional(CONF_EE_INSTALL_PATH, default="/opt/EmptyEpsilon"): str,
        vol.Optional(CONF_SCENARIO_PATH, default="/config/empty_epsilon/scenarios"): str,
    }
)


async def _validate_ssh(
    hass: HomeAssistant, host: str, port: int, username: str, password: str, key: str
) -> str | None:
    """Validate SSH connection. Returns error string or None."""
    try:
        from .ssh_manager import SSHManager

        ssh = SSHManager(host, port, username, password or None, key or None)
        if await ssh.connect():
            await ssh.disconnect()
            return None
        return "cannot_connect_ssh"
    except Exception as e:
        _LOGGER.debug("SSH validation failed: %s", e)
        return "cannot_connect_ssh"


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
        _LOGGER.debug("HTTP validation failed (server may not be running): %s", e)
        return "server_not_running"


class EmptyEpsilonConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EmptyEpsilon."""

    VERSION = 1

    def __init__(self) -> None:
        self._ssh_data: dict[str, Any] = {}
        self._ee_data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step (SSH credentials)."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=SSH_SCHEMA,
                description_placeholders={
                    "info": "SSH access is required to start/stop the EmptyEpsilon server and deploy configuration."
                },
            )

        # Validate SSH
        error = await _validate_ssh(
            self.hass,
            user_input[CONF_SSH_HOST],
            user_input[CONF_SSH_PORT],
            user_input[CONF_SSH_USERNAME],
            user_input.get(CONF_SSH_PASSWORD, ""),
            user_input.get(CONF_SSH_KEY, ""),
        )
        if error:
            return self.async_show_form(
                step_id="user",
                data_schema=SSH_SCHEMA,
                errors={"base": error},
            )

        self._ssh_data = dict(user_input)
        return await self.async_step_server()

    async def async_step_server(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure EE server details."""
        if user_input is None:
            return self.async_show_form(
                step_id="server",
                data_schema=EE_SERVER_SCHEMA,
                description_placeholders={
                    "info": "Configure EmptyEpsilon server location and HTTP port. "
                    "Leave EE Host empty to use the SSH host. "
                    "The server does not need to be running now."
                },
            )

        self._ee_data = dict(user_input)
        
        # If EE host is empty, use SSH host
        if not self._ee_data.get(CONF_EE_HOST):
            self._ee_data[CONF_EE_HOST] = self._ssh_data[CONF_SSH_HOST]

        # Optional: try to validate HTTP if server is running
        # (don't fail if it's not)
        http_error = await _validate_http(
            self.hass,
            self._ee_data[CONF_EE_HOST],
            self._ee_data[CONF_EE_PORT],
        )
        if http_error:
            _LOGGER.info(
                "EmptyEpsilon HTTP API not reachable during setup (server may not be running). "
                "This is OK - you can start it later via services."
            )

        return self._create_entry()

    def _create_entry(self) -> FlowResult:
        data = {**self._ssh_data, **self._ee_data}
        return self.async_create_entry(
            title=f"EmptyEpsilon @ {data.get(CONF_SSH_HOST, '')}",
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
