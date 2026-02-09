"""sACN/E1.31 listener for EmptyEpsilon real-time game state."""

from __future__ import annotations

import asyncio
import logging
from typing import Callable

from .const import (
    DEFAULT_SACN_CHANNELS,
    DEFAULT_SACN_UNIVERSE,
    SACN_CHANNEL_NAMES,
    SACN_CHANNEL_SPEC,
)

_LOGGER = logging.getLogger(__name__)


def _decode_dmx_value(raw: int, min_out: float, max_out: float) -> float:
    """DMX channel is 0-255; map to min_out..max_out."""
    return min_out + (raw / 255.0) * (max_out - min_out)


class SACNListener:
    """
    Listens for sACN packets on a universe and exposes decoded game state.
    Call start() then read latest via get_data(). Call stop() on shutdown.
    """

    def __init__(
        self,
        universe: int = DEFAULT_SACN_UNIVERSE,
        channels: int = DEFAULT_SACN_CHANNELS,
    ) -> None:
        self._universe = universe
        self._channels = channels
        self._data: dict[str, float] = {name: 0.0 for name in SACN_CHANNEL_NAMES}
        self._lock = asyncio.Lock()
        self._receiver = None
        self._task: asyncio.Task | None = None
        self._callback: Callable[[dict[str, float]], None] | None = None

    def set_callback(self, callback: Callable[[dict[str, float]], None] | None) -> None:
        """Set optional callback for each received packet (dict of channel name -> value)."""
        self._callback = callback

    def get_data(self) -> dict[str, float]:
        """Return latest decoded data (copy)."""
        return dict(self._data)

    async def _packet_received(self, universe: int, dmx: list[int]) -> None:
        """Process one sACN packet (universe and dmx_data copied from receiver thread)."""
        if universe != self._universe:
            return
        new_data = {}
        for (ch_0based, _ee_var, _min_in, _max_in, min_out, max_out), name in zip(
            SACN_CHANNEL_SPEC, SACN_CHANNEL_NAMES
        ):
            if ch_0based <= len(dmx):
                raw = dmx[ch_0based - 1]
                # EE variable effect outputs 0.0-1.0 mapped to 0-255
                val = _decode_dmx_value(raw, min_out, max_out)
                new_data[name] = val
        if not new_data:
            return
        async with self._lock:
            self._data.update(new_data)
        if self._callback:
            try:
                self._callback(self.get_data())
            except Exception:
                _LOGGER.exception("sACN callback error")

    def _sync_packet_received(self, packet) -> None:
        """Synchronous callback from sacn library; schedule async handler."""
        try:
            universe = packet.universe
            dmx_data = list(getattr(packet, "dmxData", None) or getattr(packet, "dmx_data", ()) or [])
            loop = asyncio.get_running_loop()
            loop.call_soon_thread_safe(
                lambda: asyncio.ensure_future(self._packet_received(universe, dmx_data))
            )
        except RuntimeError:
            pass

    async def start(self) -> None:
        """Start listening for sACN on the configured universe."""
        try:
            import sacn
        except ImportError as e:
            _LOGGER.error("sacn library not installed: %s", e)
            return

        self._receiver = sacn.sACNreceiver()
        self._receiver.register_listener(
            "universe",
            lambda p: self._sync_packet_received(p),
            universe=self._universe,
        )
        self._receiver.start()
        try:
            self._receiver.join_multicast(self._universe)
        except Exception as e:
            _LOGGER.debug("join_multicast failed (broadcast may still work): %s", e)
        _LOGGER.info("sACN listener started on universe %s", self._universe)

    def stop(self) -> None:
        """Stop the listener."""
        if self._receiver:
            try:
                self._receiver.stop()
            except Exception:
                pass
            self._receiver = None
        _LOGGER.info("sACN listener stopped")
