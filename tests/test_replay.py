"""End to end on real data: the production bot, stepped through 2016-2026 on the simulator, must reproduce the
research backtest trade for trade, survive restarts and outages, and keep its invariants."""
import importlib.util
import random
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from bot.config import Config
from bot.fake_mt5 import FakeMT5
from bot.gotobi_calendar import GotobiCalendar
from bot.replay import load_bars, load_eurusd, replay, step_times
from conftest import ROOT

pytestmark = pytest.mark.slow
UTC = timezone.utc
START = datetime(2016, 1, 4, tzinfo=UTC)
END = datetime(2026, 10, 16, 23, 59, tzinfo=UTC)
SLIP = 0.2e-4
QUIET_KILL = dict(kill_sum_r=-1e9, kill_max_drawdown=0.99)


@pytest.fixture(scope="module")
def market():
    return load_bars(), load_eurusd()


@pytest.fixture(scope="module")
def research():
    spec = importlib.util.spec_from_file_location("research_gotobi", ROOT / "src" / "gotobi.py")
    R = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(R)
    return R


def fake_for(market, **kw):
    bars, eu = market
    return FakeMT5(bars, eu, balance=1000.0, leverage=1000, vmax=1e6, **kw)


def bot_trades(journal, leg: str = "long") -> pd.DataFrame:
    """Journal records of one leg ('long' or 'short'), indexed by gotobi date."""
    rows = [{"gotobi": pd.Timestamp(k[:10]), **v} for k, v in journal.slots.items()
            if k.endswith("/short") == (leg == "short") and "#" not in k]
    return pd.DataFrame(rows).set_index("gotobi").sort_index()


@pytest.mark.parametrize("jp", [False, True], ids=["pasted-rule", "jp-holidays"])
def test_bot_reproduces_research_backtest(market, research, tmp_path, jp):
    cfg = replace(Config(), symbols=("USDJPYm",), risk_pct=1.0, exit_minutes_before_fix=0, max_spread_pips=1000.0,
                  max_entry_delay_min=600, min_hold_min=0, move_off_jp_holidays=jp, jp_bank_holidays=False,
                  take_profit_pips=0.0, post_fix_short=False, **QUIET_KILL)
    journal, _ = replay(cfg, fake_for(market), START, END, tmp_path)
    bot = bot_trades(journal)
    R = research
    df = R.load()
    days = R.gotobi_dates(pd.Timestamp(START.date()), pd.Timestamp(END.date()), jp)
    diff = R.rate_series(pd.Timestamp("2015-12-01"), pd.Timestamp("2026-11-30")).to_dict()
    res = R.trades(df, days, "A", diff).set_index("day")
    res = res[(res.index >= pd.Timestamp(START.date())) & (res.t_out <= pd.Timestamp(END.replace(tzinfo=None)))]

    closed = bot[bot.status == "closed"]
    only_research = sorted(set(res.index) - set(closed.index))
    only_bot = sorted(set(closed.index) - set(res.index))
    both = res.index.intersection(closed.index)
    r, b = res.loc[both], closed.loc[both]
    same_open = (pd.to_datetime(b.opened).dt.tz_localize(None) == r.t_in)
    same_close = (pd.to_datetime(b.closed).dt.tz_localize(None) == r.t_out)
    same_entry = (b.entry_price - r.ent * (1 + SLIP)).abs() < 1e-6
    exit_ref = r.ex * (1 - SLIP)
    same_exit = (b.close_price - exit_ref).abs() < 1e-6
    same_reason = (b.reason == r.reason)
    ok = same_open & same_close & same_entry & same_exit & same_reason
    bad = pd.DataFrame({"bot_open": b.opened, "res_open": r.t_in, "bot_close": b.closed, "res_close": r.t_out,
                        "bot_in": b.entry_price, "res_in": r.ent, "bot_out": b.close_price, "res_out": r.ex,
                        "bot_reason": b.reason, "res_reason": r.reason})[~ok]
    print(f"\n[{'jp' if jp else 'pasted'}] research {len(res)} trades, bot {len(closed)}; identical {int(ok.sum())}; "
          f"differ {len(bad)}; research-only {only_research}; bot-only {only_bot}")
    if len(bad):
        print(bad.to_string())
    bot_pips = ((closed.close_price - closed.entry_price) * 100).loc[both]
    print(f"avg pips: bot {bot_pips.mean():+.3f} vs research {r.net.mean():+.3f}")
    assert len(only_bot) == 0
    assert len(only_research) <= 3
    assert ok.mean() >= 0.995
    assert abs(bot_pips.mean() - r.net.mean()) < 0.05


def test_production_replay_invariants(market, tmp_path):
    cfg = replace(Config(), symbols=("USDJPYm",), risk_pct=1.0, **QUIET_KILL)
    fake = fake_for(market)
    journal, _ = replay(cfg, fake, START, END, tmp_path)
    t, sh = bot_trades(journal), bot_trades(journal, "short")
    cal = GotobiCalendar.from_config(cfg)
    expected = set(pd.Timestamp(d) for d in cal.trade_days(START.date(), END.date() - timedelta(days=1)))
    print("\nlong statuses:", t.status.value_counts().to_dict(), "| short statuses:", sh.status.value_counts().to_dict())
    print(t[t.status != "closed"][["status", "note"]].to_string() if (t.status != "closed").any() else "all closed")
    assert set(t.index) <= expected | {pd.Timestamp("2016-01-05")} and set(sh.index) <= expected
    assert not (t.status == "open").any() and not (sh.status == "open").any() and not fake.positions
    c, cs = t[t.status == "closed"], sh[sh.status == "closed"]
    assert c.reason.isin(["time", "stop", "target"]).all() and cs.reason.isin(["time", "stop"]).all()
    late = pd.concat([c[c.reason == "time"].exit_late_sec, cs[cs.reason == "time"].exit_late_sec])
    assert late.max() <= 60, late.sort_values().tail()
    for key, rec in c.iterrows():
        s = cal.slot(key.date())
        opened = datetime.fromisoformat(rec.opened)
        assert s.entry <= opened < s.exit - timedelta(minutes=cfg.min_hold_min - 1)
        assert rec.tp == pytest.approx(round(rec.entry_price / (1 + SLIP) + 0.30, 3))
    for key, rec in cs.iterrows():                    # each short: sold inside its window, after its long was closed
        s = cal.slot(key.date())
        assert s.short_open <= datetime.fromisoformat(rec.opened) <= s.short_late
        if key in c.index:
            assert datetime.fromisoformat(c.loc[key, "closed"]) <= datetime.fromisoformat(rec.opened)
    pips = (c.close_price - c.entry_price) * 100
    spips = (cs.entry_price - cs.close_price) * 100
    print(f"long: {len(c)} trades, win {(pips > 0).mean():.1%}, avg {pips.mean():+.2f} pips, stops "
          f"{(c.reason == 'stop').sum()}, take-profits {(c.reason == 'target').sum()} | short: {len(cs)} trades, "
          f"avg {spips.mean():+.2f} pips, stops {(cs.reason == 'stop').sum()} | balance 1000 -> {fake.balance:,.2f}")
    assert pips.mean() > 2.0 and spips.mean() > 1.0 and len(cs) >= 0.97 * len(c)


def test_restarts_change_nothing(market, tmp_path):
    cfg = replace(Config(), symbols=("USDJPYm",), risk_pct=1.0, **QUIET_KILL)
    start = datetime(2024, 1, 1, tzinfo=UTC)
    base, _ = replay(cfg, fake_for(market), start, END, tmp_path / "base")
    n = len(step_times(GotobiCalendar.from_config(cfg), start, END))
    rng = random.Random(3)
    restarts = set(rng.sample(range(1, n), n // 50))                     # kill and restart at 2% of polls
    again, _ = replay(cfg, fake_for(market), start, END, tmp_path / "again", restart_at=restarts)
    sa, sb = bot_trades(base, "short"), bot_trades(again, "short")
    assert list(sa.index) == list(sb.index) and (sa.status == sb.status).all()
    scols = ["opened", "closed", "entry_price", "close_price", "reason"]
    assert sa[scols].equals(sb[scols])                                   # shorts are never at a reopen: identical
    a, b = bot_trades(base), bot_trades(again)
    assert list(a.index) == list(b.index) and (a.status == b.status).all()
    weekday = [k for k in a.index if k.weekday() != 0]                   # Monday entries may wait 15 min after a restart
    cols = ["opened", "closed", "entry_price", "close_price", "reason"]
    assert a.loc[weekday, cols].equals(b.loc[weekday, cols])
    mon = [k for k in a.index if k.weekday() == 0 and a.loc[k, "status"] == "closed"]
    shift = [(datetime.fromisoformat(b.loc[k, "opened"]) - datetime.fromisoformat(a.loc[k, "opened"])) for k in mon]
    print(f"\n{len(restarts)} restarts; {len(weekday)} weekday trades identical; Monday entry shifts: "
          f"{sorted(set(s.total_seconds() / 60 for s in shift))} min")
    assert all(timedelta(0) <= s <= timedelta(minutes=cfg.reopen_wait_min) for s in shift)


def test_outages_never_duplicate_or_strand_a_trade(market, tmp_path):
    cfg = replace(Config(), symbols=("USDJPYm",), risk_pct=1.0, **QUIET_KILL)
    start = datetime(2024, 1, 1, tzinfo=UTC)
    rng = random.Random(5)
    down = []
    for _ in range(60):
        a = start + timedelta(minutes=rng.randrange(0, int((END - start).total_seconds() // 60)))
        down.append((a, a + timedelta(minutes=rng.randrange(30, 300))))
    cal = GotobiCalendar.from_config(cfg)
    slots = [cal.slot(d) for d in cal.trade_days(start.date(), END.date() - timedelta(days=1))]
    for s in rng.sample(slots, 12):                  # bot down across the exit: must close as soon as it is back
        down.append((s.exit - timedelta(minutes=20), s.exit + timedelta(minutes=rng.randrange(5, 240))))
    for s in rng.sample(slots, 12):                  # bot down across the entry: late entry, or missed if too late
        down.append((s.entry - timedelta(minutes=5), s.entry + timedelta(minutes=rng.randrange(10, 400))))
    for s in rng.sample(slots, 24):                  # more exits (the take-profit closes many trades first)
        down.append((s.exit - timedelta(minutes=10), s.exit + timedelta(minutes=rng.randrange(5, 240))))
    fake = fake_for(market)
    journal, _ = replay(cfg, fake, start, END, tmp_path, down=down)
    t, sh = bot_trades(journal), bot_trades(journal, "short")
    assert not fake.positions and not (t.status == "open").any() and not (sh.status == "open").any()
    for key, rec in sh[sh.status == "closed"].iterrows():      # a short is never sold late, outage or not
        s = cal.slot(key.date())
        assert s.short_open <= datetime.fromisoformat(rec.opened) <= s.short_late
    filled = [d.comment for d in fake.deal_log if d.entry == fake.DEAL_ENTRY_IN]
    assert len(filled) == len(set(filled))               # at most one FILLED buy and one sell per gotobi day
    assert sum(c.startswith("gotobi-s") for c in filled) > 0
    for d in fake.deal_log:                              # never long and short at the same time
        if d.entry == fake.DEAL_ENTRY_IN and d.comment.startswith("gotobi-s"):
            day = d.comment.split()[-1]
            lng = journal.get(day)
            if lng and lng.get("closed"):
                assert datetime.fromisoformat(lng["closed"]).timestamp() <= d.time
    retries = len([r for r in fake.requests if not r.get("position")]) - len(filled)
    print(f"\nbuy requests rejected and retried (e.g. 'market closed' at the reopen): {retries}")
    def back_at(when):                               # end of the (possibly overlapping) outages covering `when`
        while True:
            cover = [w for w in down if w[0] <= when < w[1]]
            if not cover:
                return when
            when = max(w[1] for w in cover)

    c = t[t.status == "closed"]
    hit = by_server = 0
    for key, rec in c.iterrows():
        due = datetime.fromisoformat(rec.exit_due)
        closed = datetime.fromisoformat(rec.closed)
        back = back_at(due)
        if rec.reason == "time" and back > due:      # still open at the exit while the bot was down
            hit += 1
            assert datetime.fromisoformat(rec.exit_sent) >= back - timedelta(minutes=1)
            assert closed <= back + timedelta(minutes=16)            # ... closed at the next poll (15-min steps here)
        elif rec.reason == "time":
            assert rec.exit_late_sec <= 60
        elif back > due and closed >= due:           # stop / target hit on the server while the bot was down
            by_server += 1
            assert closed <= back
    for key, rec in t.iterrows():                    # never enter later than the schedule allows
        if rec.status == "closed" and key.weekday() != 0:
            s = cal.slot(key.date())
            assert datetime.fromisoformat(rec.opened) <= s.entry + timedelta(minutes=cfg.max_entry_delay_min + 1)
    print(f"\nstatuses {t.status.value_counts().to_dict()}; exits that fell in an outage: closed late by the bot "
          f"{hit}, closed by the broker's stop/target during the outage {by_server}; short statuses "
          f"{sh.status.value_counts().to_dict()}")
    print(t[t.status != "closed"][["status", "note"]].to_string() if (t.status != "closed").any() else "")
    assert hit >= 8


def _cut_future(bars: pd.DataFrame, eu: pd.Series, cut: datetime):
    """Delete everything after `cut`; in the cut minute keep only its opening price (the rest of that minute is
    also the future)."""
    t = pd.Timestamp(cut.replace(tzinfo=None))
    b = bars[bars.index <= t].copy()
    if len(b) and b.index[-1] == t:
        for side in ("b", "a"):
            o = b.iloc[-1][f"{side}open"]
            for col in ("high", "low", "close"):
                b.iloc[-1, b.columns.get_loc(f"{side}{col}")] = o
    return b, eu[eu.index <= t]


def test_no_future_data_is_used(market, tmp_path):
    """Look-ahead test: with every price after the decision moment deleted, the bot must decide exactly the same."""
    bars, eu = market
    cfg = replace(Config(), symbols=("USDJPYm",), risk_pct=10.0, **QUIET_KILL)
    cal = GotobiCalendar.from_config(cfg)
    slots = [cal.slot(d) for d in cal.trade_days(datetime(2024, 3, 1).date(), datetime(2026, 10, 14).date())]
    rng = random.Random(11)
    cuts = []
    for s in rng.sample(slots, 10):
        mid = s.entry + timedelta(minutes=rng.randrange(1, int((s.exit - s.entry).total_seconds() // 60)))
        cuts += [s.entry, s.entry + timedelta(minutes=1), mid, s.exit - timedelta(minutes=1), s.exit,
                 s.fix, s.fix + timedelta(minutes=1), s.short_close - timedelta(minutes=1), s.short_close]
    mondays = [s for s in slots if s.gotobi.weekday() == 0]
    for s in rng.sample(mondays, 3):                                     # the Sunday-reopen decisions
        cuts += [datetime.combine(s.entry.date(), datetime.min.time(), UTC) + timedelta(hours=h, minutes=m)
                 for h, m in ((21, 5), (21, 20), (21, 35))]
    for i, cut in enumerate(cuts):
        start = cut - timedelta(days=20)
        full_fake = FakeMT5(bars, eu, balance=1000.0, leverage=1000, vmax=1e6)
        full, _ = replay(cfg, full_fake, start, cut, tmp_path / f"full{i}")
        cb, ce = _cut_future(bars, eu, cut)
        blind_fake = FakeMT5(cb, ce, balance=1000.0, leverage=1000, vmax=1e6)
        blind, _ = replay(cfg, blind_fake, start, cut, tmp_path / f"blind{i}")
        assert full.slots == blind.slots, f"decisions differ at {cut}"
        assert full_fake.balance == blind_fake.balance
        assert [(p.price_open, p.sl, p.volume) for p in full_fake.positions.values()] == \
               [(p.price_open, p.sl, p.volume) for p in blind_fake.positions.values()]
    print(f"\n{len(cuts)} cut points (entries, exits, mid-trade, Sunday reopens): every decision identical without "
          f"future data")


@pytest.fixture(scope="module")
def lab():
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    return importlib.import_module("gotobi_lab")


def test_bot_reproduces_the_lab_with_take_profit_and_short(market, lab, tmp_path):
    """The production rule (long + 30-pip take-profit + post-fix short) must match the research lab that chose it
    (src/gotobi_lab.py), trade for trade, on all 752 gotobi days 2016-2026."""
    cfg = replace(Config(), symbols=("USDJPYm",), risk_pct=1.0, **QUIET_KILL)
    journal, _ = replay(cfg, fake_for(market), START, END, tmp_path)
    t, sh_all = bot_trades(journal), bot_trades(journal, "short")
    t, sh = t[t.status == "closed"], sh_all[sh_all.status == "closed"]
    M, S = lab.Market(), lab.load_slots()
    bars = market[0]
    same_long = same_short = late_close = explained_miss = 0
    bad = []
    for k in range(len(S)):
        day = S.gotobi[k]
        lg = lab.run_leg(M, S.m_in[k], S.m_exit[k], 1, tp=30)
        st = lab.run_leg(M, S.m_fix[k], S.m_fix[k] + 30, -1)
        if day in t.index:
            b = t.loc[day]
            ok = abs(b.entry_price - lg.entry) < 1e-6 and abs(b.close_price - lg.exit) < 1e-6 and b.reason == lg.why
            same_long += ok
            if not ok:
                bad.append(("long", day.date(), b.entry_price, lg.entry, b.close_price, lg.exit, b.reason, lg.why))
        if day in sh.index:
            b = sh.loc[day]
            ok = abs(b.entry_price - st.entry) < 1e-6 and abs(b.close_price - st.exit) < 1e-6 and b.reason == st.why
            same_short += ok
            if not ok and b.exit_late_sec and abs(b.entry_price - st.entry) < 1e-6:
                late_close += 1          # no price in the 01:25 minute: the buy-back went out a minute later
            elif not ok:
                bad.append(("short", day.date(), b.entry_price, st.entry, b.close_price, st.exit, b.reason, st.why))
        else:
            # a short the lab took but the bot skipped: only allowed when the fix minute had no price at all or a
            # spread above the bot's limit (the bot refuses to sell into it)
            fix = pd.Timestamp(day) + pd.Timedelta(minutes=55)
            assert sh_all.loc[day, "status"] == "missed", day
            if fix in bars.index:
                spread = (bars.at[fix, "aopen"] - bars.at[fix, "bopen"]) * 100
                assert spread > cfg.max_spread_pips, (day, spread)
            explained_miss += 1
    print(f"\nlab slots {len(S)}; bot longs {len(t)} (identical {same_long}); bot shorts {len(sh)} (identical "
          f"{same_short}, buy-back a minute late {late_close}); shorts skipped for a wide spread / no price at the "
          f"fix {explained_miss}; unexplained differences: {bad[:5]}")
    assert len(t) == len(S) and same_long == len(S)
    assert not bad and late_close <= 3 and explained_miss <= 0.03 * len(S)
