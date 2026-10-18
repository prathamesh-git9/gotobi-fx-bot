"""Accurate UTC for the one second-sensitive move: the sell at the 09:55 JST Tokyo fix.

PC clocks drift (the development PC was 0.84 s slow). The bot asks public time servers (SNTP, UDP port 123) for
the PC clock's error about once an hour and adds the correction to every timestamp it uses. When no server
answers, the PC clock is used as it is: the post-fix sell still works if it lands within about 10 s before to
1 s after the fix (measured on 2016-2026 ticks, src/fix_seconds.py), so a normal Windows clock is good enough.

Two traps are handled:
- Windows resets its own clock now and then. A correction measured before that would then be wrong, so the clock
  watches the PC time against the monotonic counter (which nothing resets). When the PC time jumps, the
  correction is adjusted by the same amount, so the bot's time stays continuous, and the servers are asked again.
- verified() says whether the time was checked against the servers recently. The engine only trusts tick
  timestamps to reveal the broker's clock offset when it is. Otherwise a PC clock that is an hour out could pass
  for a broker in another time zone.
"""
from __future__ import annotations

import logging
import socket
import statistics
import struct
import time
from datetime import datetime, timezone

log = logging.getLogger("gotobi.clock")
NTP_EPOCH = 2208988800          # seconds from 1900-01-01 (NTP) to 1970-01-01 (Unix)
JUMP_SEC = 1.0                  # PC time moving this much against the monotonic counter = the clock was reset


def sntp_offset(host: str, timeout: float = 1.5, port: int = 123) -> tuple[float, float]:
    """(offset, round trip) in seconds from one SNTP query. offset = true time - PC time."""
    packet = b"\x23" + 47 * b"\0"                         # version 4, client mode
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        t0 = time.time()
        s.sendto(packet, (host, port))
        data, _ = s.recvfrom(48)
        t3 = time.time()
    if len(data) < 48:
        raise OSError(f"short SNTP reply from {host}")

    def stamp(offset: int) -> float:
        sec, frac = struct.unpack("!II", data[offset:offset + 8])
        return sec - NTP_EPOCH + frac / 2**32

    t1, t2 = stamp(32), stamp(40)                          # server receive / transmit
    if t2 <= 0 or data[1] == 0:                            # stratum 0 = "kiss of death" / unsynchronised
        raise OSError(f"unusable SNTP reply from {host}")
    return ((t1 - t0) + (t2 - t3)) / 2, (t3 - t0) - (t2 - t1)


class Clock:
    """PC time corrected by the median offset of the time servers that answered."""

    def __init__(self, servers: tuple[str, ...], refresh_sec: float = 3600.0, query=sntp_offset, wall=time.time,
                 mono=time.monotonic, max_age_sec: float = 12 * 3600):
        self.servers, self.refresh_sec, self.max_age_sec = servers, refresh_sec, max_age_sec
        self.query, self.wall, self.mono = query, wall, mono
        self.offset = 0.0                   # seconds to add to the PC clock
        self.measured_at: float | None = None
        self._verified_mono: float | None = None
        self._tried_at: float | None = None
        self._anchor: tuple[float, float] | None = None    # (PC time, monotonic) when the offset was last right

    def refresh(self) -> bool:
        self._tried_at = self.mono()
        offsets = []
        for host in self.servers:
            try:
                off, rtt = self.query(host)
            except OSError as e:
                log.debug("time server %s: %s", host, e)
                continue
            if 0 <= rtt < 1.0:
                offsets.append(off)
        if len(offsets) >= 2 and max(offsets) - min(offsets) < 0.25:
            new = statistics.median(offsets)
            if abs(new - self.offset) > 0.2 or self.measured_at is None:
                log.info("PC clock is %.2f s %s true time (%d time servers); correcting", abs(new),
                         "behind" if new > 0 else "ahead of", len(offsets))
            self.offset, self.measured_at = new, self.wall()
            self._verified_mono = self.mono()
            self._anchor = (self.wall(), self.mono())
            return True
        log.warning("could not check the PC clock against time servers (%d usable answers); %s", len(offsets),
                    "keeping the last correction" if self.measured_at is not None else "using it as it is")
        return False

    def maybe_refresh(self) -> None:
        if self._tried_at is None or self.mono() - self._tried_at >= self.refresh_sec:
            self.refresh()

    def _follow_jumps(self, wall: float) -> None:
        if self._anchor is None:
            return
        w0, m0 = self._anchor
        jump = (wall - w0) - (self.mono() - m0)
        if abs(jump) > JUMP_SEC:
            log.warning("the PC clock jumped %+.1f s (Windows time sync?); keeping the bot's time continuous and "
                        "checking the time servers again", jump)
            self.offset -= jump
            self._anchor = (wall, self.mono())
            self._tried_at = None           # re-check at the next quiet moment

    def now(self) -> datetime:
        wall = self.wall()
        self._follow_jumps(wall)
        return datetime.fromtimestamp(wall + self.offset, timezone.utc)

    def verified(self) -> bool:
        """True if the time servers confirmed the clock within max_age_sec."""
        return self._verified_mono is not None and self.mono() - self._verified_mono < self.max_age_sec

    def describe(self) -> str:
        if self.measured_at is None:
            return "PC clock not checked against time servers (using it as it is)"
        age = (self.mono() - self._verified_mono) / 60
        side = "behind" if self.offset > 0 else "ahead of"
        return f"PC clock is {abs(self.offset):.2f} s {side} true time (corrected; checked {age:.0f} min ago)"
