"""Media Source platform for EmptyEpsilon scenario files."""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any, Protocol

from aiohttp import web
from aiohttp.web_request import FileField

from homeassistant.components import http
from homeassistant.components.http import require_admin
from homeassistant.components.media_player import BrowseError, MediaClass
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import raise_if_invalid_filename, raise_if_invalid_path

from .const import DOMAIN, EE_CONFIG_DIR, EE_SCENARIOS_DIR

_LOGGER = logging.getLogger(__name__)

# Max 5 MB per scenario file
MAX_UPLOAD_SIZE = 5 * 1024 * 1024
LUA_EXT = ".lua"


class PathNotSupportedError(HomeAssistantError):
    """Path is not supported."""


class InvalidFileNameError(HomeAssistantError):
    """Invalid filename."""


class UploadedFile(Protocol):
    """Protocol for uploaded file."""

    filename: str
    file: io.IOBase
    content_type: str


def _scenarios_path(hass: HomeAssistant) -> Path:
    """Return the scenarios directory path."""
    return Path(hass.config.config_dir, EE_CONFIG_DIR, EE_SCENARIOS_DIR)


def _ensure_scenarios_dir(hass: HomeAssistant) -> Path:
    """Ensure scenarios directory exists. Returns the path."""
    path = _scenarios_path(hass)
    path.mkdir(parents=True, exist_ok=True)
    return path


async def async_get_media_source(hass: HomeAssistant) -> "ScenarioMediaSource":
    """Set up the EmptyEpsilon scenario media source."""
    return ScenarioMediaSource(hass)


class ScenarioMediaSource:
    """Media source for EmptyEpsilon .lua scenario files."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the source."""
        from homeassistant.components.media_source.models import MediaSource

        MediaSource.__init__(self, DOMAIN)
        self.hass = hass
        self.name = "Empty Epsilon scenarios"

    def _full_path(self, identifier: str) -> Path:
        """Return full filesystem path for an identifier (relative path)."""
        base = _scenarios_path(self.hass)
        if identifier:
            path = Path(base, identifier)
        else:
            path = base
        try:
            path.resolve().relative_to(base.resolve())
        except ValueError:
            raise ValueError("Invalid path")
        return path

    async def async_browse_media(self, item: Any) -> Any:
        """Browse scenario files and directories."""
        from homeassistant.components.media_source.models import BrowseMediaSource

        identifier = (item.identifier or "").strip()
        if identifier and ".." in identifier:
            raise BrowseError("Invalid path")

        base = _ensure_scenarios_dir(self.hass)
        full_path = base / identifier if identifier else base

        def _browse() -> Any:
            if not full_path.exists():
                if not identifier:
                    raise BrowseError("Scenarios directory does not exist.")
                raise BrowseError("Path does not exist.")

            if not full_path.is_dir():
                raise BrowseError("Path is not a directory.")

            result = BrowseMediaSource(
                domain=self.domain,
                identifier=identifier,
                media_class=MediaClass.DIRECTORY,
                media_content_type="",
                title="Empty Epsilon scenarios" if not identifier else full_path.name,
                can_play=False,
                can_expand=True,
            )
            result.children = []

            for child in sorted(full_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                if child.name.startswith("."):
                    continue
                rel = str(child.relative_to(base))
                if child.is_dir():
                    result.children.append(
                        BrowseMediaSource(
                            domain=self.domain,
                            identifier=rel,
                            media_class=MediaClass.DIRECTORY,
                            media_content_type="",
                            title=child.name,
                            can_play=False,
                            can_expand=True,
                        )
                    )
                elif child.suffix.lower() == LUA_EXT:
                    result.children.append(
                        BrowseMediaSource(
                            domain=self.domain,
                            identifier=rel,
                            media_class=MediaClass.MUSIC,
                            media_content_type="text/plain",
                            title=child.name,
                            can_play=True,
                            can_expand=False,
                        )
                    )
            return result

        return await self.hass.async_add_executor_job(_browse)

    async def async_resolve_media(self, item: Any) -> Any:
        """Resolve a scenario file to a playable URL."""
        from homeassistant.components.media_source.models import PlayMedia

        identifier = (item.identifier or "").strip()
        if ".." in identifier or not identifier.endswith(LUA_EXT):
            raise ValueError("Invalid scenario")

        full_path = self._full_path(identifier)
        if not full_path.exists() or not full_path.is_file():
            raise ValueError("File not found")

        url = f"/api/{DOMAIN}/scenarios/{identifier}"
        return PlayMedia(url=url, mime_type="text/x-lua")


class ScenarioFileView(http.HomeAssistantView):
    """Serve scenario files."""

    url = f"/api/{DOMAIN}/scenarios/{{path:.+}}"
    name = f"api:{DOMAIN}:scenarios"

    async def get(self, request: web.Request, path: str) -> web.Response:
        """Serve a scenario file."""
        hass = request.app[http.KEY_HASS]
        if ".." in path or path.startswith("/"):
            raise web.HTTPBadRequest
        base = _scenarios_path(hass)
        full_path = base / path
        try:
            full_path.resolve().relative_to(base.resolve())
        except ValueError:
            raise web.HTTPBadRequest
        if not full_path.exists() or not full_path.is_file():
            raise web.HTTPNotFound
        if full_path.suffix.lower() != LUA_EXT:
            raise web.HTTPNotFound
        return web.FileResponse(full_path, headers={"Content-Type": "text/x-lua"})


class UploadScenarioView(http.HomeAssistantView):
    """Upload scenario files."""

    url = f"/api/{DOMAIN}/scenarios/upload"
    name = f"api:{DOMAIN}:scenarios:upload"

    @require_admin
    async def post(self, request: web.Request) -> web.Response:
        """Handle scenario upload."""
        hass = request.app[http.KEY_HASS]
        request._client_max_size = MAX_UPLOAD_SIZE  # noqa: SLF001

        try:
            data = await request.post()
        except Exception as err:
            _LOGGER.error("Upload failed: %s", err)
            raise web.HTTPBadRequest from err

        file_field = data.get("file")
        if not file_field or not isinstance(file_field, FileField):
            raise web.HTTPBadRequest(reason="No file provided")

        filename = file_field.filename or ""
        if not filename.lower().endswith(LUA_EXT):
            raise web.HTTPBadRequest(reason="Only .lua files are allowed")

        try:
            raise_if_invalid_filename(filename)
        except ValueError as err:
            raise web.HTTPBadRequest(reason="Invalid filename") from err

        target_dir = _ensure_scenarios_dir(hass)
        target_path = target_dir / filename

        try:
            raise_if_invalid_path(str(target_path.relative_to(target_dir)))
        except ValueError as err:
            raise web.HTTPBadRequest from err

        def _write() -> None:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with target_path.open("wb") as f:
                f.write(file_field.file.read())

        try:
            await hass.async_add_executor_job(_write)
        except OSError as err:
            _LOGGER.error("Failed to save scenario: %s", err)
            raise web.HTTPInternalServerError from err

        media_id = f"media-source://{DOMAIN}/{filename}"
        return web.json_response({"media_content_id": media_id})
