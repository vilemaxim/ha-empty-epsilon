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

SACN_PORT = 5568


def _decode_dmx_value(raw: int, min_out: float, max_out: float) -> float:
    """DMX channel is 0-255; map to min_out..max_out."""
    return min_out + (raw / 255.0) * (max_out - min_out)


class _SACNUDPProtocol(asyncio.DatagramProtocol):
    """UDP protocol that receives sACN packets (broadcast or multicast) and forwards to listener."""

    def __init__(self, listener: SACNListener) -> None:
        self._listener = listener
        self._transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self._transport = transport

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self._listener._on_datagram(data)

    def connection_lost(self, exc: Exception | None) -> None:
        pass


class SACNListener:
    """
    Listens for sACN packets on a universe and exposes decoded game state.
    Receives both broadcast (255.255.255.255) and multicast (239.255.0.N) - EE uses broadcast.
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
        self._transport: asyncio.DatagramTransport | None = None
        self._callback: Callable[[dict[str, float]], None] | None = None

    def set_callback(self, callback: Callable[[dict[str, float]], None] | None) -> None:
        """Set optional callback for each received packet (dict of channel name -> value)."""
        self._callback = callback

    def get_data(self) -> dict[str, float]:
        """Return latest decoded data (copy)."""
        return dict(self._data)

    def _on_datagram(self, data: bytes) -> None:
        """Parse sACN packet and process if universe matches. Called from protocol."""
        try:
            from sacn.messages.data_packet import DataPacket

            packet = DataPacket.make_data_packet(tuple(data))
        except (ImportError, TypeError, IndexError) as e:
            _LOGGER.debug("sACN parse failed: %s", e)
            return
        dmx_data = list(packet.dmxData)
        asyncio.create_task(self._packet_received(packet.universe, dmx_data))

    async def _packet_received(self, universe: int, dmx: list[int]) -> None:
        """Process one sACN packet."""
        if universe != self._universe:
            return
        new_data = {}
        for (ch_0based, _ee_var, _min_in, _max_in, min_out, max_out), name in zip(
            SACN_CHANNEL_SPEC, SACN_CHANNEL_NAMES
        ):
            if ch_0based <= len(dmx):
                raw = dmx[ch_0based - 1]
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

    async def start(self) -> None:
        """Start listening for sACN on the configured universe (broadcast + multicast)."""
        try:
            from sacn.messages.data_packet import DataPacket  # noqa: F401
        except ImportError as e:
            _LOGGER.error("sacn library not installed: %s", e)
            return

        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            lambda: _SACNUDPProtocol(self),
            local_addr=("0.0.0.0", SACN_PORT),
        )
        self._transport = transport
        _LOGGER.info(
            "sACN listener started on port %s (universe %s, broadcast + multicast)",
            SACN_PORT,
            self._universe,
        )

    def stop(self) -> None:
        """Stop the listener."""
        if self._transport:
            self._transport.close()
            self._transport = None
        _LOGGER.info("sACN listener stopped")
