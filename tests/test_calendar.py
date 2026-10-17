"""Gotobi calendar: matches the research backtest's calendar, handles weekends/holidays, and the trade windows."""
import importlib.util
import random
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from bot.gotobi_calendar import GotobiCalendar

UTC = timezone.utc
ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent


def research_module():
    spec = importlib.util.spec_from_file_location("research_gotobi", ROOT / "src" / "gotobi.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("jp", [False, True])
def test_matches_research_calendar(jp):
    R = research_module()
    start, end = date(2016, 1, 1), date(2027, 12, 31)
    research = {d.date() for d in R.gotobi_dates(pd.Timestamp(start), pd.Timestamp(end), jp)}
    cal = GotobiCalendar(move_off_jp_holidays=jp, jp_bank_holidays=False, fx_closed_mmdd=())
    assert set(cal.trade_days(start, end)) == research


def test_bank_holidays_only_remove_the_two_jan3_dates():
    with_bank = GotobiCalendar(True, True, ())
    without = GotobiCalendar(True, False, ())
    a = set(with_bank.trade_days(date(2016, 1, 1), date(2026, 12, 31)))
    b = set(without.trade_days(date(2016, 1, 1), date(2026, 12, 31)))
    assert b - a == {date(2020, 1, 3), date(2025, 1, 3)}
    assert a - b == set()      # both moved onto 30 Dec, already a gotobi day


@pytest.mark.parametrize("nominal, expected", [
    (date(2026, 10, 10), date(2026, 10, 9)),    # Saturday -> Friday
    (date(2026, 3, 20), date(2026, 3, 19)),     # Vernal Equinox Day -> Thursday
    (date(2026, 5, 5), date(2026, 5, 1)),       # Golden Week (3-6 May) -> Friday 1 May
    (date(2026, 7, 20), date(2026, 7, 17)),     # Marine Day (Monday) -> Friday
    (date(2025, 11, 30), date(2025, 11, 28)),   # Sunday -> Friday
])
def test_moves(nominal, expected):
    cal = GotobiCalendar()
    assert not cal.is_trade_day(nominal)
    assert cal.is_trade_day(expected)


def test_plain_days_and_non_days():
    cal = GotobiCalendar()
    assert cal.is_trade_day(date(2026, 10, 15))
    assert cal.is_trade_day(date(2026, 10, 5))           # Monday gotobi
    for d in (date(2026, 10, 13), date(2026, 10, 14), date(2026, 10, 16)):
        assert not cal.is_trade_day(d)
    assert not cal.is_trade_day(date(2025, 12, 25))      # FX market shut at the exit time
    assert GotobiCalendar(fx_closed_mmdd=()).is_trade_day(date(2025, 12, 25))


def test_february_has_no_30th_but_month_end_moves_are_kept():
    cal = GotobiCalendar()
    feb = [d for d in cal.trade_days(date(2026, 2, 1), date(2026, 2, 28))]
    assert feb == [date(2026, 2, 5), date(2026, 2, 10), date(2026, 2, 13), date(2026, 2, 20), date(2026, 2, 25)]


def test_slot_times_are_utc_and_dst_free():
    cal = GotobiCalendar()
    for d in (date(2026, 3, 30), date(2026, 10, 26), date(2026, 7, 15)):   # around EU/US clock changes
        s = cal.slot(d)
        assert s.entry == datetime(d.year, d.month, d.day, 15, 55, tzinfo=UTC) - timedelta(days=1)
        assert s.fix == datetime(d.year, d.month, d.day, 0, 55, tzinfo=UTC)
        assert s.exit == datetime(d.year, d.month, d.day, 0, 54, tzinfo=UTC)
    assert GotobiCalendar(exit_minutes_before_fix=0).slot(date(2026, 10, 15)).exit.minute == 55


def test_active_window_boundaries():
    cal = GotobiCalendar()
    s = cal.slot(date(2026, 10, 15))
    assert cal.active(s.entry - timedelta(seconds=1)) is None
    assert cal.active(s.entry) == s
    assert cal.active(s.exit - timedelta(seconds=1)) == s
    assert cal.active(s.exit) is None
    assert cal.next_slot(datetime(2026, 10, 13, 12, tzinfo=UTC)) == s


def test_active_agrees_with_brute_force():
    cal = GotobiCalendar()
    days = cal.trade_days(date(2015, 12, 1), date(2027, 2, 1))
    slots = [cal.slot(d) for d in days]
    rng = random.Random(7)
    base = datetime(2016, 1, 1, tzinfo=UTC)
    for _ in range(20000):
        now = base + timedelta(seconds=rng.randrange(0, 11 * 365 * 86400))
        expected = [s for s in slots if s.entry <= now < s.exit]
        assert cal.active(now) == (expected[0] if expected else None)
