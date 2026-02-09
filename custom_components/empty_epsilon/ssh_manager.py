"""SSH/SCP manager for EmptyEpsilon server management and hardware.ini deploy."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any

# Import deferred to connect() - asyncssh does blocking I/O on import

from .const import (
    DEFAULT_SACN_CHANNELS,
    DEFAULT_SACN_UNIVERSE,
    DEFAULT_RESEND_DELAY_MS,
    SACN_CHANNEL_NAMES,
    SACN_CHANNEL_SPEC,
)

_LOGGER = logging.getLogger(__name__)


def generate_hardware_ini(
    universe: int = DEFAULT_SACN_UNIVERSE,
    channels: int = DEFAULT_SACN_CHANNELS,
    resend_delay_ms: int = DEFAULT_RESEND_DELAY_MS,
) -> str:
    """Generate hardware.ini content for EE sACN output."""
    lines = [
        "[hardware]",
        "device = sACNDevice",
        f"universe = {universe}",
        f"channels = {channels}",
        f"resend_delay = {resend_delay_ms}",
        "",
    ]
    for (ch, _ee_var, min_in, max_in, min_out, max_out), name in zip(
        SACN_CHANNEL_SPEC, SACN_CHANNEL_NAMES
    ):
        lines.append("[channel]")
        lines.append(f"name = {name}")
        lines.append(f"channel = {ch}")
        lines.append("")
    for (ch, ee_var, min_in, max_in, min_out, max_out), name in zip(
        SACN_CHANNEL_SPEC, SACN_CHANNEL_NAMES
    ):
        lines.append("[state]")
        lines.append("condition = Always")
        lines.append(f"target = {name}")
        lines.append("effect = variable")
        lines.append(f"input = {ee_var}")
        lines.append(f"min_input = {min_in}")
        lines.append(f"max_input = {max_in}")
        lines.append(f"min_output = {min_out}")
        lines.append(f"max_output = {max_out}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


class SSHManager:
    """Async SSH/SCP operations for EE server."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str | None = None,
        key_filename: str | None = None,
        known_hosts: str | None = None,
        skip_host_key_check: bool = False,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password or ""
        self._key_filename = key_filename.strip() if key_filename else None
        self._known_hosts = known_hosts.strip() or None
        self._skip_host_key_check = skip_host_key_check
        self._conn: Any = None

    def _connect_kwargs(self, known_hosts_obj: Any = None) -> dict[str, Any]:
        kwargs = {
            "host": self._host,
            "port": self._port,
            "username": self._username,
        }
        if self._key_filename:
            kwargs["client_keys"] = [self._key_filename]
        if self._password:
            kwargs["password"] = self._password
        # Host key verification: known_hosts object, or skip if requested
        if self._skip_host_key_check:
            kwargs["known_hosts"] = None
        elif known_hosts_obj is not None:
            kwargs["known_hosts"] = known_hosts_obj
        return kwargs

    async def connect(self) -> bool:
        """Establish SSH connection. Returns True on success."""
        import asyncssh  # Lazy import - asyncssh blocks on load

        known_hosts_obj = None
        if not self._skip_host_key_check and self._known_hosts:
            path = Path(self._known_hosts)
            if path.exists():
                # Load file in executor to avoid blocking the event loop
                content = await asyncio.to_thread(path.read_text, encoding="utf-8")
                known_hosts_obj = asyncssh.import_known_hosts(content)

        try:
            self._conn = await asyncio.wait_for(
                asyncssh.connect(**self._connect_kwargs(known_hosts_obj)),
                timeout=15.0,
            )
            return True
        except Exception as e:
            _LOGGER.warning("SSH connect failed: %s", e)
            return False

    async def disconnect(self) -> None:
        """Close SSH connection."""
        if self._conn:
            try:
                self._conn.close()
                await self._conn.wait_closed()
            except Exception:
                pass
            self._conn = None

    async def run_command(self, command: str, timeout: float = 30.0) -> tuple[int, str, str]:
        """Run a command. Returns (exit_status, stdout, stderr)."""
        if not self._conn:
            if not await self.connect():
                return -1, "", "SSH not connected"
        try:
            result = await asyncio.wait_for(
                self._conn.run(command),
                timeout=timeout,
            )
            return (
                result.exit_status,
                result.stdout or "",
                result.stderr or "",
            )
        except Exception as e:
            _LOGGER.warning("SSH command failed: %s", e)
            self._conn = None
            return -1, "", str(e)

    async def upload_string(
        self,
        content: str,
        remote_path: str,
        timeout: float = 30.0,
    ) -> bool:
        """Upload string content to a remote file (e.g. hardware.ini)."""
        if not self._conn:
            if not await self.connect():
                return False
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".ini", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            local_path = f.name
        try:
            sftp = await asyncio.wait_for(
                self._conn.start_sftp_client(),
                timeout=timeout,
            )
            await asyncio.wait_for(
                sftp.put(local_path, remote_path),
                timeout=timeout,
            )
            return True
        except Exception as e:
            _LOGGER.warning("SFTP upload failed: %s", e)
            return False
        finally:
            Path(local_path).unlink(missing_ok=True)

    async def deploy_hardware_ini(
        self,
        ee_install_path: str,
        universe: int = DEFAULT_SACN_UNIVERSE,
        channels: int = DEFAULT_SACN_CHANNELS,
    ) -> bool:
        """Generate hardware.ini and upload to EE server scripts directory."""
        content = generate_hardware_ini(universe=universe, channels=channels)
        remote_path = f"{ee_install_path.rstrip('/')}/scripts/hardware.ini"
        return await self.upload_string(content, remote_path)
