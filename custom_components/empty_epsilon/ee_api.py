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
        url = self._url(EE_EXEC_PATH)
        _LOGGER.debug("exec_lua POST %s (Lua: %s)", url, lua_code[:80] + "..." if len(lua_code) > 80 else lua_code)
        async with aiohttp.ClientSession(timeout=self._timeout) as session:
            try:
                async with session.post(
                    url,
                    data=lua_code,
                    headers={"Content-Type": "text/plain; charset=utf-8"},
                ) as resp:
                    text = await resp.text()
                    _LOGGER.debug("exec_lua response status=%s len=%d body=%s", resp.status, len(text), repr(text[:200]))
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
                _LOGGER.warning("HTTP request failed to %s: %s", url, e)
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
            raw = (r or "").strip().strip('"\'')
            result = raw.lower() == "true"
            return result
        except EEAPIError as e:
            _LOGGER.debug("get_has_game failed: %s (raw=%s)", e, getattr(e, "raw", None))
            return False

    async def get_player_ship_count(self) -> int:
        """Count active player ships. Use 0,1,2... (getPlayerShip(-1) can duplicate 0)."""
        try:
            r = await self.exec_lua(
                "local n=0; for i=0,99 do if getPlayerShip(i) then n=n+1 end end; "
                "if n==0 and getPlayerShip(-1) then n=1 end; return tostring(n)"
            )
            return int(float(r.strip())) if r and r.strip() else 0
        except (EEAPIError, ValueError):
            return 0

    async def get_victory_faction(self) -> str | None:
        """Return winning faction name or None if game not over."""
        try:
            r = await self.exec_lua(
                "local g=gameGlobalInfo; if g then return tostring(g:getVictoryFaction() or '') end; return ''"
            )
            raw = (r or "").strip().strip('"\'')
            # Treat nil, null, none, empty as "game not over"
            if not raw or raw.lower() in ("nil", "null", "none"):
                return None
            return raw
        except EEAPIError:
            return None

    async def is_paused(self) -> bool:
        """Return True if game is paused (speed 0)."""
        try:
            # Try global getGameSpeed() first; fallback to gameGlobalInfo:getGameSpeed()
            r = await self.exec_lua(
                "if getGameSpeed then return tostring(getGameSpeed()==0) end; "
                "local g=gameGlobalInfo; if g and g.getGameSpeed then return tostring(g:getGameSpeed()==0) end; "
                "return 'false'"
            )
            s = (r or "").strip().lower().strip('"\'')
            return s == "true"
        except EEAPIError:
            return False

    async def pause_game(self) -> None:
        """Pause the game."""
        await self.exec_lua("pauseGame()")

    async def unpause_game(self) -> None:
        """Unpause the game."""
        await self.exec_lua("unpauseGame()")

    async def shutdown_game(self) -> None:
        """Request graceful shutdown via EE shutdownGame(). Exits the process cleanly."""
        await self.exec_lua("shutdownGame()")

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

    # --- Phase 5: Advanced GM controls ---

    def _escape(self, s: str) -> str:
        return (s or "").replace("\\", "\\\\").replace('"', '\\"')

    async def spawn_cpu_ship(
        self,
        template: str = "Adder MK3",
        faction: str = "Kraylor",
        x: float = 0,
        y: float = 0,
        order: str = "idle",
    ) -> None:
        """Spawn an AI CpuShip. Order: idle, roam, attack (needs target)."""
        t, f = self._escape(template or "Adder MK3"), self._escape(faction or "Kraylor")
        base = f'CpuShip():setFaction("{f}"):setTemplate("{t}"):setPosition({x},{y})'
        if order == "roam":
            await self.exec_lua(base + ":orderRoaming()")
        else:
            await self.exec_lua(base + ":orderIdle()")

    async def spawn_station(
        self,
        template: str = "Small Station",
        faction: str = "Human Navy",
        x: float = 0,
        y: float = 0,
    ) -> None:
        """Spawn a SpaceStation."""
        t, f = self._escape(template or "Small Station"), self._escape(faction or "Human Navy")
        await self.exec_lua(
            f'SpaceStation():setFaction("{f}"):setTemplate("{t}"):setPosition({x},{y})'
        )

    async def spawn_nebula(self, x: float = 0, y: float = 0) -> None:
        """Spawn a nebula at position."""
        await self.exec_lua(f"Nebula():setPosition({x},{y})")

    async def spawn_asteroid(self, x: float = 0, y: float = 0) -> None:
        """Spawn an asteroid at position."""
        await self.exec_lua(f"Asteroid():setPosition({x},{y})")

    async def send_comms_message(self, callsign: str, message: str) -> None:
        """Send an incoming comms message to a player ship by callsign."""
        c, m = self._escape(callsign), self._escape(message)
        await self.exec_lua(
            f'for i=-1,99 do local s=getPlayerShip(i); if s and s:getCallSign()=="{c}" then '
            f's:addCustomMessage("gm","{m}"); break end end'
        )

    async def modify_hull(self, callsign: str, value: float) -> None:
        """Set hull percentage (0-100) for a player ship."""
        c = self._escape(callsign)
        v = max(0, min(100, float(value)))
        await self.exec_lua(
            f'for i=-1,99 do local s=getPlayerShip(i); if s and s:getCallSign()=="{c}" then '
            f's:setHull({v}); break end end'
        )

    async def modify_shields(self, callsign: str, front: float, rear: float) -> None:
        """Set shield percentages (0-100) for a player ship."""
        c = self._escape(callsign)
        f, r = max(0, min(100, float(front))), max(0, min(100, float(rear)))
        await self.exec_lua(
            f'for i=-1,99 do local s=getPlayerShip(i); if s and s:getCallSign()=="{c}" then '
            f's:setShields({f},{r}); break end end'
        )

    async def give_weapons(
        self,
        callsign: str,
        homing: int = 0,
        nuke: int = 0,
        emp: int = 0,
        mine: int = 0,
        hvli: int = 0,
    ) -> None:
        """Add ammo to a player ship. Pass counts to add."""
        c = self._escape(callsign)
        updates = []
        for name, count in [("Homing", homing), ("Nuke", nuke), ("EMP", emp), ("Mine", mine), ("HVLI", hvli)]:
            if count:
                updates.append(f's:setWeaponStorage("{name}", (s:getWeaponStorage("{name}") or 0)+{count})')
        if not updates:
            return
        lua = f'for i=-1,99 do local s=getPlayerShip(i); if s and s:getCallSign()=="{c}" then {" ".join(updates)}; break end end'
        await self.exec_lua(lua)

    async def red_alert_all(self) -> None:
        """Set all player ships to red alert."""
        await self.exec_lua(
            'for i=-1,99 do local s=getPlayerShip(i); if s then s:setAlertLevel("RED ALERT"); end end'
        )

    async def resupply_all(self) -> None:
        """Refill energy and ammo for all player ships."""
        await self.exec_lua(
            "for i=-1,99 do local s=getPlayerShip(i); if s then "
            "s:setEnergyLevel(s:getEnergyLevelMax()); "
            "for _,w in ipairs({'Homing','Nuke','EMP','Mine','HVLI'}) do "
            "local m=s:getWeaponStorageMax(w); if m and m>0 then s:setWeaponStorage(w,m) end end "
            "end end"
        )

    async def repair_all(self) -> None:
        """Restore hull and shields for all player ships."""
        await self.exec_lua(
            "for i=-1,99 do local s=getPlayerShip(i); if s then "
            "s:setHull(s:getHullMax() or 100); "
            "local fm=s:getShieldMax(0); local rm=s:getShieldMax(1); "
            "s:setShields(fm and fm or 100, rm and rm or 100); "
            "end end"
        )

    # --- Phase 2: Server-level and primary ship sensors ---

    async def get_total_objects(self) -> int:
        """Return count of all game objects."""
        try:
            r = await self.exec_lua(
                "local t=getAllObjects() or {}; return tostring(#t)"
            )
            return int(float(r.strip())) if r and r.strip() else 0
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
            return int(float(r.strip())) if r and r.strip() else 0
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
            return int(float(r.strip())) if r and r.strip() else 0
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
                "local rep=0; if s.getReputationPoints then rep=s:getReputationPoints() or 0 end; "
                "return c..'|'..t..'|'..sec..'|'..tostring(h)..'|'..tostring(n)..'|'..tostring(e)..'|'..tostring(m)..'|'..tostring(v)..'|'..tostring(rep)"
            )
            if not r or "|" not in r:
                return result
            raw = r.strip().strip('"\'')
            parts = raw.split("|", 8)
            result["callsign"] = (parts[0].strip().strip('"\'') or None) if parts[0] else None
            result["ship_type"] = (parts[1].strip() or None) if len(parts) > 1 else None
            result["sector"] = (parts[2].strip() or None) if len(parts) > 2 else None
            for i, k in enumerate(["homing", "nuke", "emp", "mine", "hvli"], 3):
                try:
                    result[k] = int(float(parts[i])) if i < len(parts) and parts[i] else 0
                except (ValueError, IndexError):
                    result[k] = 0
            if len(parts) > 8:
                rep_raw = (parts[8] or "").strip().strip('"\'')
                if rep_raw and rep_raw.lower() not in ("nil", "null", "none"):
                    try:
                        result["reputation"] = int(float(rep_raw))
                    except (ValueError, TypeError):
                        result["reputation"] = 0
                else:
                    result["reputation"] = 0
            return result
        except EEAPIError:
            return result
