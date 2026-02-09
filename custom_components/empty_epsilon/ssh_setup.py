"""SSH setup helpers (key generation, known_hosts). Run in executor to avoid blocking."""

from __future__ import annotations

import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Any

from .const import EE_CONFIG_DIR, EE_KEY_PATH, EE_KNOWN_HOSTS_PATH, EE_PUBKEY_PATH

_LOGGER = logging.getLogger(__name__)


def _ensure_config_dir() -> Path:
    """Create empty_epsilon config dir if needed."""
    path = Path(f"/config/{EE_CONFIG_DIR}")
    path.mkdir(parents=True, exist_ok=True)
    return path


def generate_ssh_key() -> tuple[str, str]:
    """
    Generate RSA key pair. Returns (private_key_path, public_key_path).
    Must run in executor (asyncssh import blocks).
    """
    import asyncssh

    _ensure_config_dir()
    key = asyncssh.generate_private_key("ssh-rsa", key_size=4096)
    private_key_data = key.export_private_key()
    public_key_data = key.export_public_key()
    # asyncssh returns bytes for PEM format
    if isinstance(private_key_data, bytes):
        private_key_data = private_key_data.decode("utf-8")
    if isinstance(public_key_data, bytes):
        public_key_data = public_key_data.decode("utf-8")

    Path(EE_KEY_PATH).write_text(private_key_data, encoding="utf-8")
    Path(EE_KEY_PATH).chmod(0o600)
    Path(EE_PUBKEY_PATH).write_text(public_key_data, encoding="utf-8")
    Path(EE_PUBKEY_PATH).chmod(0o644)

    # Also copy to www for web access: http://ha:8123/local/empty_epsilon/ee_ssh_public_key.pub
    www_dir = Path("/config/www/empty_epsilon")
    www_dir.mkdir(parents=True, exist_ok=True)
    (www_dir / "ee_ssh_public_key.pub").write_text(public_key_data, encoding="utf-8")

    _LOGGER.info("Generated SSH key pair at %s", EE_KEY_PATH)
    return EE_KEY_PATH, EE_PUBKEY_PATH


def fetch_and_save_host_key(host: str, port: int) -> str | None:
    """
    Run ssh-keyscan to fetch host key and append to known_hosts.
    Returns known_hosts path on success, None if ssh-keyscan unavailable.
    Must run in executor.
    """
    try:
        result = subprocess.run(
            ["ssh-keyscan", "-p", str(port), host],
            capture_output=True,
            timeout=10,
            check=False,
        )
        if result.returncode != 0 or not result.stdout:
            _LOGGER.debug("ssh-keyscan failed or empty: %s", result.stderr)
            return None
        _ensure_config_dir()
        with open(EE_KNOWN_HOSTS_PATH, "a", encoding="utf-8") as f:
            f.write(result.stdout.decode("utf-8"))
        return EE_KNOWN_HOSTS_PATH
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        _LOGGER.debug("ssh-keyscan not available or timed out: %s", e)
        return None


def validate_ssh_sync(
    host: str,
    port: int,
    username: str,
    password: str | None,
    key_filename: str | None,
    known_hosts: str | None,
    skip_host_key_check: bool,
    save_host_key_on_first_connect: bool = True,
) -> tuple[bool, str | None, str | None]:
    """
    Validate SSH connection. Runs in executor to avoid blocking.
    Returns (success, error_message, saved_known_hosts_path).
    If save_host_key_on_first_connect and we connect with skip, fetches host key.
    """
    import asyncssh

    from .ssh_manager import SSHManager

    async def _connect() -> tuple[bool, str | None, str | None]:
        ssh = SSHManager(
            host, port, username,
            password, key_filename,
            known_hosts=known_hosts,
            skip_host_key_check=skip_host_key_check,
        )
        saved_path: str | None = None
        try:
            ok = await ssh.connect()
            if ok and skip_host_key_check and save_host_key_on_first_connect:
                saved_path = await asyncio.to_thread(
                    fetch_and_save_host_key, host, port
                )
            if ok:
                await ssh.disconnect()
                return True, None, saved_path
            return False, "cannot_connect_ssh", None
        except Exception as e:
            _LOGGER.debug("SSH validation failed: %s", e)
            return False, str(e) or "cannot_connect_ssh", None

    try:
        return asyncio.run(_connect())
    except Exception as e:
        _LOGGER.debug("SSH validation error: %s", e)
        return False, str(e) or "cannot_connect_ssh", None
