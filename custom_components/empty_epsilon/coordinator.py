"""DataUpdateCoordinator combining sACN push and HTTP API poll for EmptyEpsilon."""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_EE_HOST,
    CONF_EE_PORT,
    CONF_POLL_INTERVAL,
    CONF_SACN_UNIVERSE,
    DOMAIN,
    GAME_STATUS_GAME_OVER_DEFEAT,
    GAME_STATUS_GAME_OVER_VICTORY,
    GAME_STATUS_PAUSED,
    GAME_STATUS_PLAYING,
    GAME_STATUS_SETUP,
)
from .ee_api import EEAPIClient, EEAPIError
from .sacn_listener import SACNListener

_LOGGER = logging.getLogger(__name__)


class EmptyEpsilonCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Combines sACN real-time data with HTTP API polled data."""

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        self._config = config
        host = config[CONF_EE_HOST]
        port = config[CONF_EE_PORT]
        self._base_url = f"http://{host}:{port}"
        self._api = EEAPIClient(self._base_url)
        poll_interval = config.get(CONF_POLL_INTERVAL, 10)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=poll_interval),
        )
        self._sacn: SACNListener | None = None
        universe = config.get(CONF_SACN_UNIVERSE, 2)
        self._sacn = SACNListener(universe=universe)
        self._last_scenario_time: float | None = None
        self._last_scenario_time_at: float = 0.0

    def _infer_paused(self, scenario_time: float | None) -> bool:
        """Infer paused when scenario time does not advance (EE getGameSpeed returns nil in headless)."""
        now = time.monotonic()
        if scenario_time is None:
            self._last_scenario_time = None
            return False
        # Need at least 3s of real time to compare
        if self._last_scenario_time is not None and (now - self._last_scenario_time_at) >= 3.0:
            elapsed_real = now - self._last_scenario_time_at
            delta_scenario = scenario_time - self._last_scenario_time
            # If scenario advanced by less than 1s over 3s+ real time, consider paused
            paused = delta_scenario < 1.0
        else:
            paused = False
        self._last_scenario_time = scenario_time
        self._last_scenario_time_at = now
        return paused

    @property
    def api(self) -> EEAPIClient:
        return self._api

    @property
    def sacn_listener(self) -> SACNListener | None:
        return self._sacn

    async def _async_update_data(self) -> dict[str, Any]:
        """Merge sACN data with HTTP API data."""
        data: dict[str, Any] = {"sacn": {}, "http": {}, "game_status": None}

        # Latest sACN (real-time)
        if self._sacn:
            data["sacn"] = self._sacn.get_data()

        # HTTP API (game status, player count, scenario time, paused)
        try:
            has_game = await self._api.get_has_game()
            data["http"]["has_game"] = has_game
            data["http"]["server_reachable"] = True
            _LOGGER.info(
                "EmptyEpsilon HTTP poll: has_game=%s url=%s",
                has_game,
                self._base_url,
            )

            if has_game:
                scenario_time = await self._api.get_scenario_time()
                data["http"]["scenario_time"] = scenario_time
                data["http"]["player_ship_count"] = await self._api.get_player_ship_count()
                # EE getGameSpeed() returns nil in headless; infer pause from scenario time not advancing
                data["http"]["paused"] = self._infer_paused(scenario_time)
                victory = await self._api.get_victory_faction()
                data["http"]["victory_faction"] = victory

                # Phase 2: server-level and primary ship sensors
                data["http"]["active_scenario"] = await self._api.get_active_scenario()
                data["http"]["total_objects"] = await self._api.get_total_objects()
                data["http"]["enemy_ship_count"] = await self._api.get_enemy_ship_count()
                data["http"]["friendly_station_count"] = await self._api.get_friendly_station_count()
                data["http"]["primary_ship"] = await self._api.get_primary_ship_info()

                # Derive game_status
                if victory:
                    # Human Navy typical victory faction; treat others as defeat for player
                    data["game_status"] = (
                        GAME_STATUS_GAME_OVER_VICTORY
                        if victory and "human" in victory.lower()
                        else GAME_STATUS_GAME_OVER_DEFEAT
                    )
                elif data["http"]["paused"]:
                    data["game_status"] = GAME_STATUS_PAUSED
                else:
                    data["game_status"] = GAME_STATUS_PLAYING
            else:
                data["game_status"] = GAME_STATUS_SETUP
                data["http"]["scenario_time"] = None
                data["http"]["player_ship_count"] = 0
                data["http"]["paused"] = False
                self._last_scenario_time = None
                data["http"]["victory_faction"] = None
                data["http"]["active_scenario"] = None
                data["http"]["total_objects"] = 0
                data["http"]["enemy_ship_count"] = 0
                data["http"]["friendly_station_count"] = 0
                data["http"]["primary_ship"] = {}

        except EEAPIError as e:
            _LOGGER.warning("HTTP API update failed: %s (raw=%s)", e, getattr(e, "raw", None))
            data["http"]["server_reachable"] = False
            data["http"]["has_game"] = False
            data["game_status"] = GAME_STATUS_SETUP
            # Don't raise so sACN data can still be used
        except Exception as e:
            _LOGGER.exception("Update failed: %s", e)
            data["http"]["server_reachable"] = False
            raise UpdateFailed from e

        return data

    async def start_sacn(self) -> None:
        """Start sACN listener and wire callback to request refresh."""
        if not self._sacn:
            return
        # Callback runs on event loop (from sacn_listener._packet_received); schedule refresh
        def on_sacn_data(_data: dict) -> None:
            self.hass.async_create_task(self.async_request_refresh())

        self._sacn.set_callback(on_sacn_data)
        await self._sacn.start()

    def stop_sacn(self) -> None:
        """Stop sACN listener."""
        if self._sacn:
            self._sacn.stop()
