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

    # --- Phase 3: Game controls ---

    async def global_message(self, message: str) -> None:
        """Display a message to all players."""
        # Escape quotes in message for Lua string
        escaped = (message or "").replace("\\", "\\\\").replace('"', '\\"')
        await self.exec_lua(f'globalMessage("{escaped}")')

    async def victory(self, faction: str) -> None:
        """End the game with the specified faction as winner."""
        escaped = (faction or "Human Navy").replace("\\", "\\\\").replace('"', '\\"')
        await self.exec_lua(f'victory("{escaped}")')

    async def spawn_player_ship(
        self,
        template: str = "Atlantis",
        callsign: str = "Epsilon",
        faction: str = "Human Navy",
        x: float = 0,
        y: float = 0,
    ) -> None:
        """Spawn a player ship. Template examples: Atlantis, Phobos M3P, Player Cruiser."""
        t = (template or "Atlantis").replace("\\", "\\\\").replace('"', '\\"')
        c = (callsign or "Epsilon").replace("\\", "\\\\").replace('"', '\\"')
        f = (faction or "Human Navy").replace("\\", "\\\\").replace('"', '\\"')
        await self.exec_lua(
            f'PlayerSpaceship():setFaction("{f}"):setTemplate("{t}"):setCallSign("{c}"):setPosition({x},{y})'
        )

    # --- Phase 2: Server-level and primary ship sensors ---

    async def get_active_scenario(self) -> str | None:
        """Return active scenario name or None."""
        try:
            r = await self.exec_lua(
                "if getScenarioName then return tostring(getScenarioName() or '') end; return ''"
            )
            return (r or "").strip() or None
        except EEAPIError:
            return None

    async def get_total_objects(self) -> int:
        """Return count of all game objects."""
        try:
            r = await self.exec_lua(
                "local t=getAllObjects() or {}; return tostring(#t)"
            )
            return int(r.strip()) if r and r.strip().isdigit() else 0
        except (EEAPIError, ValueError):
            return 0

    async def get_enemy_ship_count(self) -> int:
        """Return count of hostile CpuShips (from first player's perspective)."""
        try:
            r = await self.exec_lua(
                "local p=getPlayerShip(-1); if not p then return '0' end; "
                "local n=0; for _,o in ipairs(getAllObjects() or {}) do "
                "if o.typeName=='CpuShip' and p:isEnemy(o) then n=n+1 end end; return tostring(n)"
            )
            return int(r.strip()) if r and r.strip().lstrip("-").isdigit() else 0
        except (EEAPIError, ValueError):
            return 0

    async def get_friendly_station_count(self) -> int:
        """Return count of stations friendly to first player."""
        try:
            r = await self.exec_lua(
                "local p=getPlayerShip(-1); if not p then return '0' end; "
                "local n=0; for _,o in ipairs(getAllObjects() or {}) do "
                "if o.typeName=='SpaceStation' and p:isFriendly(o) then n=n+1 end end; return tostring(n)"
            )
            return int(r.strip()) if r and r.strip().lstrip("-").isdigit() else 0
        except (EEAPIError, ValueError):
            return 0

    async def get_primary_ship_info(self) -> dict[str, str | int | None]:
        """Return callsign, type, sector, ammo for first player ship. Keys may be None if no ship."""
        result: dict[str, str | int | None] = {
            "callsign": None,
            "ship_type": None,
            "sector": None,
            "homing": None,
            "nuke": None,
            "emp": None,
            "mine": None,
            "hvli": None,
            "reputation": None,
        }
        try:
            # Single exec for primary ship: callsign, type, sector, ammo, reputation
            r = await self.exec_lua(
                "local s=getPlayerShip(-1); if not s then return '' end; "
                "local c=s:getCallSign() or ''; local t=s:getTypeName() or ''; "
                "local sec=''; if s.getSectorName then sec=s:getSectorName() or '' end; "
                "local h=s:getWeaponStorage('Homing') or 0; local n=s:getWeaponStorage('Nuke') or 0; "
                "local e=s:getWeaponStorage('EMP') or 0; local m=s:getWeaponStorage('Mine') or 0; "
                "local v=s:getWeaponStorage('HVLI') or 0; "
                "local rep=0; if getReputationPoints then rep=getReputationPoints(s:getFaction()) or 0 end; "
                "return c..'|'..t..'|'..sec..'|'..tostring(h)..'|'..tostring(n)..'|'..tostring(e)..'|'..tostring(m)..'|'..tostring(v)..'|'..tostring(rep)"
            )
            if not r or "|" not in r:
                return result
            parts = r.strip().split("|", 8)
            result["callsign"] = parts[0].strip() or None
            result["ship_type"] = parts[1].strip() or None
            result["sector"] = parts[2].strip() or None
            for i, k in enumerate(["homing", "nuke", "emp", "mine", "hvli"], 3):
                try:
                    result[k] = int(parts[i]) if i < len(parts) and parts[i] else 0
                except (ValueError, IndexError):
                    result[k] = 0
            if len(parts) > 8:
                try:
                    result["reputation"] = int(parts[8])
                except (ValueError, TypeError):
                    result["reputation"] = None
            return result
        except EEAPIError:
            return result
