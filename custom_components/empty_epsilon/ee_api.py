"""EmptyEpsilon HTTP API client (exec.lua only)."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .const import EE_EXEC_PATH

_LOGGER = logging.getLogger(__name__)


class EEAPIError(Exception):
    """Error from EE HTTP API."""

    def __init__(self, message: str, raw: str | None = None) -> None:
        super().__init__(message)
        self.raw = raw


class EEAPIClient:
    """Client for EmptyEpsilon HTTP API via POST /exec.lua."""

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    def _url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    async def exec_lua(self, lua_code: str) -> str:
        """
        Execute Lua code on the EE server. Returns the result as string.
        Raises EEAPIError on API error or no game.
        """
        async with aiohttp.ClientSession(timeout=self._timeout) as session:
            try:
                async with session.post(
                    self._url(EE_EXEC_PATH),
                    data=lua_code,
                    headers={"Content-Type": "text/plain; charset=utf-8"},
                ) as resp:
                    text = await resp.text()
                    if resp.status != 200:
                        raise EEAPIError(f"HTTP {resp.status}: {text}", raw=text)
                    # EE returns JSON on error: {"ERROR": "..."}
                    if text.strip().startswith("{"):
                        import json
                        try:
                            data = __import__("json").loads(text)
                            if "ERROR" in data:
                                raise EEAPIError(data["ERROR"], raw=text)
                        except ValueError:
                            pass
                    return text
            except aiohttp.ClientError as e:
                _LOGGER.debug("HTTP request failed: %s", e)
                raise EEAPIError(str(e)) from e

    async def get_scenario_time(self) -> float | None:
        """Return scenario time in seconds or None if no game."""
        try:
            r = await self.exec_lua("return tostring(getScenarioTime() or '')")
            return float(r) if r and r.strip() else None
        except (EEAPIError, ValueError):
            return None

    async def get_has_game(self) -> bool:
        """Return True if a game is running (scenario time and player ship exist)."""
        try:
            r = await self.exec_lua(
                "return tostring(getScenarioTime() ~= nil and getPlayerShip(-1) ~= nil)"
            )
            return r.strip().lower() == "true"
        except EEAPIError:
            return False

    async def get_player_ship_count(self) -> int:
        """Count active player ships (1-indexed until nil)."""
        try:
            r = await self.exec_lua(
                "local n=0; while getPlayerShip(n) do n=n+1 end; return tostring(n)"
            )
            return int(r.strip()) if r and r.strip().isdigit() else 0
        except (EEAPIError, ValueError):
            return 0

    async def get_victory_faction(self) -> str | None:
        """Return winning faction name or None if game not over."""
        try:
            r = await self.exec_lua(
                "local g=gameGlobalInfo; if g then return tostring(g:getVictoryFaction() or '') end; return ''"
            )
            return r.strip() or None
        except EEAPIError:
            return None

    async def is_paused(self) -> bool:
        """Return True if game is paused (speed 0)."""
        try:
            r = await self.exec_lua(
                "local g=gameGlobalInfo; if g then return tostring(g:getGameSpeed()==0) end; return 'false'"
            )
            return r.strip().lower() == "true"
        except EEAPIError:
            return False

    async def pause_game(self) -> None:
        """Pause the game."""
        await self.exec_lua("pauseGame()")

    async def unpause_game(self) -> None:
        """Unpause the game."""
        await self.exec_lua("unpauseGame()")
