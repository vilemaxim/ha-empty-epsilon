"""Config flow for EmptyEpsilon integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
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
    CONF_SSH_KNOWN_HOSTS,
    CONF_SSH_PASSWORD,
    CONF_SSH_PORT,
    CONF_SSH_SKIP_HOST_KEY_CHECK,
    CONF_SSH_USERNAME,
    DEFAULT_HTTP_PORT,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_SACN_UNIVERSE,
    DEFAULT_SSH_PORT,
    DOMAIN,
    EE_KEY_PATH,
    EE_KNOWN_HOSTS_PATH,
)

_LOGGER = logging.getLogger(__name__)

# Step 0: Key setup
KEY_SCHEMA = vol.Schema(
    {
        vol.Required("key_choice", default="generate"): vol.In(
            ["generate", "use_existing"]
        ),
    }
)

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
        vol.Optional(CONF_SSH_SKIP_HOST_KEY_CHECK, default=True): bool,
    }
)

# Step 2: EE server configuration
EE_SERVER_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_EE_HOST, default=""): str,
        vol.Optional(CONF_EE_PORT, default=DEFAULT_HTTP_PORT): vol.All(
            vol.Coerce(int), vol.Range(1, 65535)
        ),
        vol.Optional(CONF_EE_INSTALL_PATH, default="/usr/local/bin"): str,
        vol.Optional(CONF_SCENARIO_PATH, default="/config/empty_epsilon/scenarios"): str,
    }
)


async def _validate_ssh(
    hass: HomeAssistant,
    host: str,
    port: int,
    username: str,
    password: str,
    key: str,
    skip_host_key_check: bool,
) -> tuple[str | None, str | None]:
    """
    Validate SSH connection in executor (avoids blocking asyncssh import).
    Returns (error_message, known_hosts_path).
    On first connect with skip=True, fetches and saves host key; known_hosts_path is set.
    """
    from .ssh_setup import validate_ssh_sync

    result = await hass.async_add_executor_job(
        validate_ssh_sync,
        host,
        port,
        username,
        password or None,
        key or None,
        None,  # known_hosts - we'll use saved path after first connect
        skip_host_key_check,
        True,  # save_host_key_on_first_connect
    )
    success, err, saved_path = result
    if success:
        return None, saved_path
    return err or "cannot_connect_ssh", None


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
        self._generated_key_path: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step (key setup)."""
        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=KEY_SCHEMA,
                description_placeholders={
                    "info": "Generate a new SSH key for this integration, or use an existing key."
                },
            )

        if user_input.get("key_choice") == "generate":
            return await self.async_step_generate_key()
        return await self.async_step_ssh()

    async def async_step_generate_key(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Generate SSH key and continue to SSH credentials."""
        from .ssh_setup import generate_ssh_key

        try:
            await self.hass.async_add_executor_job(generate_ssh_key)
            self._generated_key_path = EE_KEY_PATH
        except Exception as e:
            _LOGGER.exception("Key generation failed: %s", e)
            return self.async_show_form(
                step_id="user",
                data_schema=KEY_SCHEMA,
                errors={"base": "key_generation_failed"},
            )
        return await self.async_step_ssh()

    async def async_step_ssh(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle SSH credentials step."""
        if user_input is None:
            schema = SSH_SCHEMA.extend({
                vol.Optional(
                    CONF_SSH_KEY,
                    default=self._generated_key_path or "",
                ): str,
            })
            return self.async_show_form(
                step_id="ssh",
                data_schema=schema,
                description_placeholders={
                    "info": "SSH access to the EE server. "
                    "During setup, the server's host key will be trusted automatically."
                },
            )

        key_path = (user_input.get(CONF_SSH_KEY) or "").strip()
        if not key_path and self._generated_key_path:
            key_path = self._generated_key_path
        if not key_path and not user_input.get(CONF_SSH_PASSWORD):
            return self.async_show_form(
                step_id="ssh",
                data_schema=SSH_SCHEMA.extend({
                    vol.Optional(CONF_SSH_KEY, default=key_path): str,
                }),
                errors={"base": "key_or_password_required"},
            )

        # Validate SSH in executor
        error, known_hosts_path = await _validate_ssh(
            self.hass,
            user_input[CONF_SSH_HOST],
            user_input[CONF_SSH_PORT],
            user_input[CONF_SSH_USERNAME],
            user_input.get(CONF_SSH_PASSWORD, ""),
            key_path,
            user_input.get(CONF_SSH_SKIP_HOST_KEY_CHECK, True),
        )
        if error:
            return self.async_show_form(
                step_id="ssh",
                data_schema=SSH_SCHEMA.extend({
                    vol.Optional(CONF_SSH_KEY, default=key_path): str,
                }),
                errors={"base": error},
            )

        self._ssh_data = dict(user_input)
        self._ssh_data[CONF_SSH_KEY] = key_path
        if known_hosts_path:
            self._ssh_data[CONF_SSH_KNOWN_HOSTS] = known_hosts_path
            self._ssh_data[CONF_SSH_SKIP_HOST_KEY_CHECK] = False
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
                    "info": "Configure EmptyEpsilon server. "
                    "Leave EE Host empty to use the SSH host. "
                    "The server does not need to be running now."
                },
            )

        self._ee_data = dict(user_input)
        if not self._ee_data.get(CONF_EE_HOST):
            self._ee_data[CONF_EE_HOST] = self._ssh_data[CONF_SSH_HOST]

        http_error = await _validate_http(
            self.hass,
            self._ee_data[CONF_EE_HOST],
            self._ee_data[CONF_EE_PORT],
        )
        if http_error:
            _LOGGER.info(
                "EmptyEpsilon HTTP API not reachable during setup. "
                "You can start it later via services."
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
        """Initialize options flow. config_entry required for HA 2024.1-2024.9 compatibility."""
        super().__init__()
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self._config_entry.options or {}
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
