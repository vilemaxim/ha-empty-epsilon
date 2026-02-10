"""SSH/SCP manager for EmptyEpsilon server management and hardware.ini deploy."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any

from .const import (
    DEFAULT_INIT_SCENARIO,
    DEFAULT_SACN_CHANNELS,
    DEFAULT_SACN_UNIVERSE,
    DEFAULT_RESEND_DELAY_MS,
    SACN_CHANNEL_NAMES,
    SACN_CHANNEL_SPEC,
)

_LOGGER = logging.getLogger(__name__)

# General integration log on the EE server: all actions and results
EE_INTEGRATION_LOG = "/tmp/emptyepsilon_integration.log"


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
        self._known_hosts = (known_hosts.strip() or None) if known_hosts else None
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
        if self._skip_host_key_check:
            kwargs["known_hosts"] = None
        elif known_hosts_obj is not None:
            kwargs["known_hosts"] = known_hosts_obj
        return kwargs

    async def connect(self) -> bool:
        """Establish SSH connection. Returns True on success."""
        import sys
        if "asyncssh" not in sys.modules:
            await asyncio.to_thread(__import__, "asyncssh")
        import asyncssh

        known_hosts_obj = None
        if not self._skip_host_key_check and self._known_hosts:
            path = Path(self._known_hosts)
            if path.exists():
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

    async def _clear_integration_log(self) -> None:
        """Clear the integration log on the EE server (fresh log for each run)."""
        await self.run_command(f"> {EE_INTEGRATION_LOG}", timeout=5.0)

    async def _log_remote(self, action: str, message: str, status: str | None = None) -> None:
        """Append an action/result line to the integration log on the EE server."""
        line = f"{action}: {message}"
        if status is not None:
            line += f" [status={status}]"
        # Use printf to avoid shell interpretation of message content
        escaped = line.replace("'", "'\"'\"'")
        await self.run_command(
            f"printf '%s [HA] %s\\n' \"$(date -Iseconds 2>/dev/null || date)\" '{escaped}' >> {EE_INTEGRATION_LOG}",
            timeout=5.0,
        )

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

    async def start_server(
        self,
        ee_install_path: str,
        ee_port: int,
        scenario: str = DEFAULT_INIT_SCENARIO,
        headless_name: str = "EmptyEpsilon",
        headless_internet: bool = False,
    ) -> bool:
        """
        Start EmptyEpsilon headless with httpserver on the EE host via SSH.
        Skips if already running. Uses login shell.
        All actions and EE output go to /tmp/emptyepsilon_integration.log on the EE server.
        Returns True if the server is running (existing or newly started).
        """
        await self._log_remote("start_server", "checking if EmptyEpsilon already running")
        _cmd = "pgrep EmptyEpsilon || true"
        await self._log_remote("start_server", f"about to run: {_cmd}")
        check_status, check_out, check_err = await self.run_command(
            _cmd,
            timeout=5.0,
        )
        await self._log_remote("start_server", f"pgrep result: status={check_status} pids={check_out.strip() or '(none)'}")
        _LOGGER.debug("pgrep check: status=%s out=%r err=%r", check_status, check_out, check_err)
        if check_out.strip():
            _LOGGER.info("EmptyEpsilon already running, skipping start")
            await self._log_remote("start_server", "skipped - already running")
            return True

        base = ee_install_path.rstrip("/")
        ee_bin = base if base.endswith("EmptyEpsilon") else f"{base}/EmptyEpsilon"
        # Deploy options.ini so EE reads headless config (name, internet, etc.)
        await self.deploy_options_ini(
            scenario=scenario,
            ee_port=ee_port,
            headless_name=headless_name,
            headless_internet=headless_internet,
        )
        # EE reads options.ini; no need for command-line args
        cmd = (
            f"( echo '=== EmptyEpsilon process output ===' >> {EE_INTEGRATION_LOG}; "
            f"nohup {ee_bin} >> {EE_INTEGRATION_LOG} 2>&1 & )"
        )
        full_cmd = f'bash -l -c "{cmd}"'
        await self._log_remote("start_server", f"about to run: {full_cmd}")
        _LOGGER.info("Running start command on %s:%s", self._host, self._port)
        status, out, err = await self.run_command(
            full_cmd,
            timeout=15.0,
        )
        await self._log_remote("start_server", f"nohup launched: status={status} stdout={out[:100] if out else ''} stderr={err[:100] if err else ''}")
        if status != 0:
            _LOGGER.warning(
                "Start server command failed (status=%s): %s %s",
                status, out.strip(), err.strip(),
            )
            return False
        await asyncio.sleep(2)
        await self._log_remote("start_server", "verifying process started")
        _verify_cmd = "pgrep EmptyEpsilon || true"
        await self._log_remote("start_server", f"about to run: {_verify_cmd}")
        check_status, check_out, _ = await self.run_command(
            _verify_cmd,
            timeout=5.0,
        )
        await self._log_remote("start_server", f"verify pgrep: status={check_status} pids={check_out.strip() or '(none)'}")
        if not check_out.strip():
            _LOGGER.warning(
                "EmptyEpsilon start command ran but no process found. Check %s on the EE server.",
                EE_INTEGRATION_LOG,
            )
            await self._log_remote("start_server", "FAILED - no process found after start")
            return False
        _LOGGER.info(
            "EmptyEpsilon start sent: %s (httpserver=%s)",
            scenario, ee_port,
        )
        await self._log_remote("start_server", f"SUCCESS - process running (httpserver={ee_port})")
        return True

    async def stop_server(self) -> bool:
        """Stop EmptyEpsilon by killing the process on the EE host via SSH."""
        await self._clear_integration_log()
        cmd = "pkill EmptyEpsilon || true"
        await self._log_remote("stop_server", f"about to run: {cmd}")
        status, out, err = await self.run_command(cmd, timeout=15.0)
        await self._log_remote("stop_server", f"result: status={status} out={out.strip() or ''} err={err.strip() or ''}")
        if status != 0:
            _LOGGER.warning(
                "Stop server command failed (status=%s): %s %s",
                status, out.strip(), err.strip(),
            )
            return False
        _LOGGER.info("EmptyEpsilon stop sent")
        return True

    async def deploy_hardware_ini(
        self,
        universe: int = DEFAULT_SACN_UNIVERSE,
        channels: int = DEFAULT_SACN_CHANNELS,
    ) -> bool:
        """Generate hardware.ini and upload to EE config dir (~/.emptyepsilon/)."""
        await self._clear_integration_log()
        await self._log_remote("deploy_hardware_ini", "starting", "universe=" + str(universe))
        _cmd = "echo $HOME"
        await self._log_remote("deploy_hardware_ini", f"about to run: {_cmd}")
        status, out, err = await self.run_command(_cmd)
        await self._log_remote("deploy_hardware_ini", f"echo HOME -> status={status} home={out.strip() or err}")
        if status != 0:
            _LOGGER.warning("Could not resolve remote HOME: %s %s", out, err)
            return False
        home = out.strip()
        remote_dir = f"{home}/.emptyepsilon"
        remote_path = f"{remote_dir}/hardware.ini"
        _mkdir_cmd = f"mkdir -p {remote_dir}"
        await self._log_remote("deploy_hardware_ini", f"about to run: {_mkdir_cmd}")
        mkdir_status, _, _ = await self.run_command(_mkdir_cmd)
        await self._log_remote("deploy_hardware_ini", f"mkdir -p {remote_dir} -> status={mkdir_status}")
        if mkdir_status != 0:
            _LOGGER.warning("Could not create %s on remote", remote_dir)
            return False
        content = generate_hardware_ini(universe=universe, channels=channels)
        await self._log_remote("deploy_hardware_ini", f"about to upload (SFTP): {remote_path}")
        upload_ok = await self.upload_string(content, remote_path)
        await self._log_remote("deploy_hardware_ini", f"upload to {remote_path} -> ok={upload_ok}")
        return upload_ok

    async def deploy_options_ini(
        self,
        scenario: str,
        ee_port: int,
        headless_name: str = "EmptyEpsilon",
        headless_internet: bool = False,
    ) -> bool:
        """
        Deploy or update ~/.emptyepsilon/options.ini for headless server.
        Merges with existing file to preserve user preferences.
        See https://github.com/daid/EmptyEpsilon/wiki/Headless-Dedicated-Server
        """
        await self._log_remote("deploy_options_ini", "starting")
        _cmd = "echo $HOME"
        await self._log_remote("deploy_options_ini", f"about to run: {_cmd}")
        status, out, err = await self.run_command(_cmd)
        if status != 0:
            _LOGGER.warning("Could not resolve remote HOME: %s %s", out, err)
            return False
        home = out.strip()
        remote_dir = f"{home}/.emptyepsilon"
        options_path = f"{remote_dir}/options.ini"
        for d in (remote_dir, f"{home}/logs"):
            _mkdir_cmd = f"mkdir -p {d}"
            await self._log_remote("deploy_options_ini", f"about to run: {_mkdir_cmd}")
            mkdir_status, _, _ = await self.run_command(_mkdir_cmd)
            if mkdir_status != 0:
                return False

        our_keys = {
            "headless": scenario,
            "httpserver": str(ee_port),
            "headless_name": headless_name,
            "headless_internet": "1" if headless_internet else "0",
        }
        await self._log_remote("deploy_options_ini", f"options: {our_keys}")

        status, existing, _ = await self.run_command(
            f"test -f {options_path} && cat {options_path} || echo ''",
            timeout=5.0,
        )
        lines = []
        if existing.strip():
            for line in existing.strip().split("\n"):
                if "=" in line:
                    key = line.split("=")[0].strip()
                    if key not in our_keys:
                        lines.append(line.rstrip())
        for k, v in our_keys.items():
            lines.append(f"{k}={v}")
        content = "\n".join(lines) + "\n"
        await self._log_remote("deploy_options_ini", f"about to upload: {options_path}")
        ok = await self.upload_string(content, options_path)
        await self._log_remote("deploy_options_ini", f"upload result: ok={ok}")
        return ok
