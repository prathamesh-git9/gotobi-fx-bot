"""Which days are gotobi trading days, and the UTC window of each trade.

Gotobi days are the 5th, 10th, 15th, 20th, 25th and 30th. One that falls on a weekend (or, optionally, a Japanese
public or bank holiday) moves to the business day before. The trade for gotobi day D opens on D-1 at entry_utc
and closes on D at fix_utc minus exit_minutes_before_fix. Days whose fix falls in an FX-market closure are skipped.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache

import holidays

UTC = timezone.utc
GOTOBI_DAYS = (5, 10, 15, 20, 25, 30)


def parse_hm(s: str) -> time:
    h, m = map(int, s.split(":"))
    return time(h, m)


def month_after(d: date) -> date:
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


@dataclass(frozen=True)
class Slot:
    gotobi: date        # the Japanese fix date
    entry: datetime     # UTC, on the calendar day before
    fix: datetime       # 09:55 JST expressed in UTC
    exit: datetime      # UTC, when the bot closes


class GotobiCalendar:
    def __init__(self, move_off_jp_holidays: bool = True, jp_bank_holidays: bool = True,
                 fx_closed_mmdd: tuple[str, ...] = ("12-25", "01-01"), entry_utc: str = "15:55",
                 fix_utc: str = "00:55", exit_minutes_before_fix: int = 1):
        self.move_holidays = move_off_jp_holidays
        self.bank_holidays = jp_bank_holidays
        self.fx_closed = frozenset(fx_closed_mmdd)
        self.entry_time = parse_hm(entry_utc)
        self.fix_time = parse_hm(fix_utc)
        self.exit_before = timedelta(minutes=exit_minutes_before_fix)
        self._jp = holidays.Japan()

    @classmethod
    def from_config(cls, cfg) -> "GotobiCalendar":
        return cls(cfg.move_off_jp_holidays, cfg.jp_bank_holidays, cfg.fx_closed_mmdd, cfg.entry_utc,
                   cfg.fix_utc, cfg.exit_minutes_before_fix)

    def business_day(self, d: date) -> bool:
        if d.weekday() >= 5:
            return False
        if self.move_holidays and d in self._jp:
            return False
        if self.bank_holidays and ((d.month == 12 and d.day == 31) or (d.month == 1 and d.day <= 3)):
            return False
        return True

    @lru_cache(maxsize=512)
    def _month(self, year: int, month: int) -> frozenset:
        last_day = (month_after(date(year, month, 1)) - timedelta(days=1)).day
        out = set()
        for g in GOTOBI_DAYS:
            if g > last_day:
                continue
            d = date(year, month, g)
            while not self.business_day(d):
                d -= timedelta(days=1)
            out.add(d)
        return frozenset(out)

    def is_trade_day(self, d: date) -> bool:
        """True if a trade's fix falls on d (after weekend/holiday moves, excluding FX closures)."""
        nxt = month_after(d)
        if d not in self._month(d.year, d.month) and d not in self._month(nxt.year, nxt.month):
            return False
        return f"{d:%m-%d}" not in self.fx_closed

    def trade_days(self, start: date, end: date) -> list[date]:
        out, m = set(), date(start.year, start.month, 1)
        while m <= month_after(end):
            out |= self._month(m.year, m.month)
            m = month_after(m)
        return sorted(d for d in out if start <= d <= end and self.is_trade_day(d))

    def slot(self, d: date) -> Slot:
        fix = datetime.combine(d, self.fix_time, UTC)
        entry = datetime.combine(d - timedelta(days=1), self.entry_time, UTC)
        return Slot(d, entry, fix, fix - self.exit_before)

    def active(self, now: datetime) -> Slot | None:
        """The slot whose entry window [entry, exit) contains `now` (an aware UTC datetime)."""
        for d in (now.date(), now.date() + timedelta(days=1)):
            if self.is_trade_day(d):
                s = self.slot(d)
                if s.entry <= now < s.exit:
                    return s
        return None

    def next_slot(self, now: datetime) -> Slot:
        d = now.date()
        for _ in range(60):
            if self.is_trade_day(d) and self.slot(d).exit > now:
                return self.slot(d)
            d += timedelta(days=1)
        raise RuntimeError("no gotobi day in the next 60 days")
