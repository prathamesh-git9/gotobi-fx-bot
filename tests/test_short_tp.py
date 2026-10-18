"""The two add-ons on the simulator: the +30-pip take-profit on the long, and the post-fix short (sell at the
09:55 JST fix, buy back 30 minutes later). Plus the SNTP clock, and the new settings and calendar times."""
import shutil
import socket
import struct
import threading
from dataclasses import replace
from datetime import date, timedelta

import pytest

from bot.clock import NTP_EPOCH, Clock, sntp_offset
from bot.config import Config, ConfigError, load_config
from bot.gotobi_calendar import GotobiCalendar
from conftest import FULL_CFG, Rig, ask_spike, dip, set_spread, spike, utc

GOTOBI = "2026-10-15"            # buy Wed 14 Oct 15:55 UTC, close Thu 00:54; sell Thu 00:55, buy back 01:25
SHORT = f"{GOTOBI}/short"


def sells(rig):
    return [r for r in rig.opens() if r["type"] == rig.fake.ORDER_TYPE_SELL]


def run_day(rig, start="2026-10-14 15:50", end="2026-10-15 02:00"):
    rig.run(start, end)


# ------------------------------------------------------------------------------------------ take-profit
def test_take_profit_is_sent_with_the_buy_and_closes_the_trade(week, tmp_path):
    spike(week, "2026-10-14 18:00", high=150.32)                         # bid reaches the 150.310 target
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    run_day(rig, end="2026-10-14 18:30")
    buy = rig.opens()[0]
    assert buy["tp"] == pytest.approx(150.010 + 0.30) and buy["sl"] == pytest.approx(150.010 - 0.55)
    rec = rig.journal.get(GOTOBI)
    assert rec["status"] == "closed" and rec["reason"] == "target" and rec["closed"] == "2026-10-14T18:00:00+00:00"
    assert rec["close_price"] == pytest.approx(150.310 * (1 - 0.2e-4))
    assert 0.5 < rec["r"] < 0.56                                         # ~29.4 of 55.6 pips
    assert rig.closes() == []                                            # the broker closed it, not the bot


def test_stop_and_target_in_the_same_minute_counts_as_the_stop(week, tmp_path):
    spike(week, "2026-10-14 18:00", high=150.32)
    dip(week, "2026-10-14 18:00", 149.40)
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    run_day(rig, end="2026-10-14 18:30")
    assert rig.journal.get(GOTOBI)["reason"] == "stop"


def test_no_take_profit_when_switched_off(week, tmp_path):
    rig = Rig(week, tmp_path, cfg=replace(FULL_CFG, take_profit_pips=0.0), start="2026-10-14 15:50")
    rig.run("2026-10-14 15:50", "2026-10-14 15:56")
    assert "tp" not in rig.opens()[0]


# ------------------------------------------------------------------------------------------ the post-fix short
def test_post_fix_short_lifecycle(week, tmp_path):
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    run_day(rig)
    s = sells(rig)
    assert len(rig.opens()) == 2 and len(s) == 1
    o = s[0]
    assert o["comment"] == f"gotobi-s {GOTOBI}" and o["sl"] == pytest.approx(150.000 + 0.55) and "tp" not in o
    assert o["volume"] == 0.31             # 10% of the EUR 997.4 left after the long: 99.74 / 312.25 per lot
    long, short = rig.journal.get(GOTOBI), rig.journal.get(SHORT)
    assert long["closed"] == "2026-10-15T00:54:00+00:00"
    assert short["side"] == "short" and short["status"] == "closed" and short["reason"] == "time"
    assert short["opened"] == "2026-10-15T00:55:00+00:00" and short["closed"] == "2026-10-15T01:25:00+00:00"
    assert short["filled_vs_fix_sec"] == 0.0
    assert short["entry_price"] == pytest.approx(150.000 * (1 - 0.2e-4))
    assert short["close_price"] == pytest.approx(150.010 * (1 + 0.2e-4))
    close = rig.closes()[-1]
    assert close["type"] == rig.fake.ORDER_TYPE_BUY and close["position"] == short["ticket"]
    assert long["pnl"] + short["pnl"] == pytest.approx(rig.fake.balance - 1000.0, abs=0.02)


def test_sell_goes_out_one_second_before_the_fix(week, tmp_path):
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    rig.run("2026-10-14 15:50", "2026-10-15 00:53")
    rig.run("2026-10-15 00:53:30", "2026-10-15 00:55:10", every_sec=1)
    short = rig.journal.get(SHORT)
    assert short["opened"] == "2026-10-15T00:54:59+00:00" and short["sent_vs_fix_sec"] == -1.0
    assert len(sells(rig)) == 1


def test_short_is_skipped_when_the_bot_is_too_late(week, tmp_path):
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-15 00:55:10")
    rig.run("2026-10-15 00:55:10", "2026-10-15 02:00")
    rec = rig.journal.get(SHORT)
    assert rec["status"] == "missed" and "5 s" in rec["note"] and rig.fake.requests == []


def test_short_waits_for_the_long_and_never_hedges(week, tmp_path):
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    rig.fake.fail_next("close", rig.fake.TRADE_RETCODE_PRICE_OFF, 2)    # long closes only at 00:56
    run_day(rig)
    assert rig.journal.get(GOTOBI)["exit_sent"] == "2026-10-15T00:56:00+00:00"
    assert rig.journal.get(SHORT)["status"] == "missed" and sells(rig) == []


def test_restart_during_the_short_does_not_sell_twice(week, tmp_path):
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    rig.run("2026-10-14 15:50", "2026-10-15 00:56")
    rig.start("2026-10-15 00:57")                                        # crash + restart from saved state
    rig.run("2026-10-15 00:57", "2026-10-15 02:00")
    assert len(sells(rig)) == 1 and rig.journal.get(SHORT)["closed"] == "2026-10-15T01:25:00+00:00"


def test_stopped_out_short_is_not_sold_again_after_the_journal_is_lost(week, tmp_path):
    ask_spike(week, "2026-10-15 00:58", 150.60)                         # above the 150.550 stop
    cfg = replace(FULL_CFG, short_max_late_sec=600.0)                   # keep the sell window open for the test
    rig = Rig(week, tmp_path / "state", cfg=cfg, start="2026-10-14 15:50")
    rig.run("2026-10-14 15:50", "2026-10-15 00:59")
    assert rig.journal.get(SHORT)["reason"] == "stop"
    shutil.rmtree(tmp_path / "state")
    rig.start("2026-10-15 01:00")
    rig.run("2026-10-15 01:00", "2026-10-15 02:00")
    rec = rig.journal.get(SHORT)
    assert len(sells(rig)) == 1 and rec["recovered"] and rec["reason"] == "stop"
    assert len([r for r in rig.opens() if r["type"] == rig.fake.ORDER_TYPE_BUY]) == 1


def test_adopts_an_unknown_short_and_buys_it_back_on_time(week, tmp_path):
    rig = Rig(week, tmp_path, cfg=FULL_CFG)
    rig.fake.set_time(utc("2026-10-15 00:56"))
    rig.fake.order_send({"action": 1, "symbol": "USDJPYm", "volume": 0.1, "type": 1, "price": 150.0, "sl": 150.55,
                         "deviation": 30, "magic": FULL_CFG.magic, "comment": f"gotobi-s {GOTOBI}",
                         "type_time": 0, "type_filling": 1})
    rig.start("2026-10-15 00:57")                                        # journal is empty (state lost)
    rig.run("2026-10-15 00:57", "2026-10-15 02:00")
    rec = rig.journal.get(SHORT)
    assert rec["adopted"] and rec["side"] == "short" and rec["closed"] == "2026-10-15T01:25:00+00:00"
    assert len(rig.opens()) == 1


def test_short_stop_is_recorded(week, tmp_path):
    ask_spike(week, "2026-10-15 01:00", 150.60)
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    run_day(rig)
    rec = rig.journal.get(SHORT)
    assert rec["reason"] == "stop" and rec["closed"] == "2026-10-15T01:00:00+00:00"
    assert rec["r"] == pytest.approx(-1.0, abs=0.03)


def test_short_also_trades_after_the_long_was_stopped_out(week, tmp_path):
    dip(week, "2026-10-14 18:00", 149.40)
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    run_day(rig)
    assert rig.journal.get(GOTOBI)["reason"] == "stop" and rig.journal.get(SHORT)["status"] == "closed"


def test_short_switched_off(week, tmp_path):
    rig = Rig(week, tmp_path, cfg=replace(FULL_CFG, post_fix_short=False), start="2026-10-14 15:50")
    run_day(rig)
    assert sells(rig) == [] and rig.journal.get(SHORT) is None


def test_kill_switch_blocks_the_short(week, tmp_path):
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    rig.run("2026-10-14 15:50", "2026-10-14 16:00")
    rig.journal.halt("test", utc("2026-10-14 16:00"))
    run_day(rig, start="2026-10-14 16:00")
    assert rig.journal.get(SHORT)["status"] == "skipped" and sells(rig) == []
    assert rig.journal.get(GOTOBI)["status"] == "closed"                 # the open long is still closed on time


def test_wide_spread_at_the_fix_means_no_short(week, tmp_path):
    set_spread(week, "2026-10-15 00:50", "2026-10-15 01:30", 0.08)
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    run_day(rig)
    assert rig.journal.get(SHORT)["status"] == "missed" and sells(rig) == []


def test_kill_switch_r_rule_counts_only_the_long_trades(week, tmp_path):
    rig = Rig(week, tmp_path, cfg=FULL_CFG)
    j = rig.start("2026-10-14 15:50").journal
    for i in range(59):
        j.slots[f"2020-01-{i:03d}"] = {"status": "closed", "r": 0.0, "pnl": 0.0}
    for i in range(100):                                                 # 100 losing shorts must not trip it
        j.slots[f"2020-02-{i:03d}/short"] = {"status": "closed", "r": -1.0, "pnl": -1.0, "side": "short"}
    run_day(rig)
    assert j.halted is None


def test_dry_run_checks_both_trades_and_sends_nothing(week, tmp_path):
    rig = Rig(week, tmp_path, cfg=FULL_CFG)
    rig.start("2026-10-14 15:50", dry_run=True)
    run_day(rig)
    assert rig.fake.requests == []
    assert rig.journal.get(GOTOBI)["status"] == "dryrun" and rig.journal.get(SHORT)["status"] == "dryrun"


def test_poll_interval_wakes_at_the_second_of_the_sell(week, tmp_path):
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    e = rig.engine
    assert e.poll_interval(utc("2026-10-15 00:54:57.500000")) == 1.0
    assert e.poll_interval(utc("2026-10-15 00:54:58.200000")) == pytest.approx(0.801)
    assert e.poll_interval(utc("2026-10-15 00:55:01")) == 0.25           # inside the few-second sell window
    assert e.poll_interval(utc("2026-10-15 01:24:57")) == pytest.approx(3.001)   # wake for the buy-back
    assert e.poll_interval(utc("2026-10-15 12:00")) == FULL_CFG.poll_sec
    assert not e.quiet(utc("2026-10-15 00:50")) and not e.quiet(utc("2026-10-15 01:21"))
    assert e.quiet(utc("2026-10-15 12:00"))


def test_preflight_reports_the_target_and_the_short(week, tmp_path):
    from bot.broker import MT5Broker
    from bot.engine import Engine
    from bot.journal import Journal
    rig = Rig(week, tmp_path, cfg=FULL_CFG)
    now = utc("2026-10-14 12:00")
    rig.fake.set_time(now)
    eng = Engine(FULL_CFG, MT5Broker(rig.fake), Journal(tmp_path, durable=False))
    eng.clock_note = "PC clock is 0.84 s behind true time (corrected; checked 0 min ago)"
    eng.startup(now, inspect_only=True)
    ready, lines = eng.preflight(now)
    text = "\n".join(lines)
    assert ready and "take-profit +30 pips" in text and "post-fix sell with its stop: accepted" in text
    assert "then the post-fix short: sell 2026-10-15T00:54:59" in text and "0.84 s behind" in text
    assert rig.fake.requests == []


# ------------------------------------------------------------------------------------------ calendar + settings
def test_calendar_short_times():
    s = GotobiCalendar.from_config(Config()).slot(date(2026, 10, 15))
    assert s.short_open.isoformat() == "2026-10-15T00:54:59+00:00"
    assert s.short_late.isoformat() == "2026-10-15T00:55:05+00:00"
    assert s.short_close.isoformat() == "2026-10-15T01:25:00+00:00"
    cal = GotobiCalendar.from_config(Config())
    assert cal.short_active(utc("2026-10-15 00:54:58")) is None
    assert cal.short_active(utc("2026-10-15 00:54:59")).gotobi == date(2026, 10, 15)
    assert cal.short_active(utc("2026-10-15 01:25")) is None
    assert cal.short_active(utc("2026-10-14 00:55")) is None             # not a gotobi day


def test_new_settings_are_validated(tmp_path):
    for bad in (dict(take_profit_pips=-1), dict(short_minutes=0), dict(short_stop_pips=5),
                dict(short_send_sec=-60), dict(short_send_sec=2.0, short_max_late_sec=1.0),
                dict(short_max_late_sec=90)):
        with pytest.raises(ConfigError):
            replace(Config(), **bad).validate()
    f = tmp_path / "c.toml"
    f.write_text("short_send_sec = -2\nshort_max_late_sec = 3\ntake_profit_pips = 35\npost_fix_short = false\n",
                 encoding="utf-8")
    cfg = load_config(f)
    assert cfg.short_send_sec == -2.0 and cfg.take_profit_pips == 35.0 and cfg.post_fix_short is False


# ------------------------------------------------------------------------------------------ the clock
def test_clock_uses_the_median_of_agreeing_time_servers():
    answers = {"a": (0.84, 0.03), "b": (0.83, 0.05), "c": (0.86, 0.02)}
    c = Clock(("a", "b", "c"), query=lambda h: answers[h], wall=lambda: 1000.0)
    assert c.refresh() and c.offset == pytest.approx(0.84)
    assert c.now().timestamp() == pytest.approx(1000.84)
    assert "0.84 s behind" in c.describe()


def test_clock_keeps_the_pc_time_when_servers_fail_or_disagree():
    def query(h):
        if h == "down":
            raise OSError("timed out")
        return {"a": (0.8, 0.03), "b": (5.0, 0.03), "slow": (0.8, 2.0)}[h]
    c = Clock(("a", "b", "down", "slow"), query=query, wall=lambda: 1000.0)
    assert not c.refresh() and c.offset == 0.0 and "not checked" in c.describe()


def test_clock_refreshes_once_per_period():
    calls, t = [], [0.0]
    c = Clock(("a", "b"), refresh_sec=3600, query=lambda h: calls.append(h) or (0.5, 0.01), wall=lambda: t[0],
              mono=lambda: t[0])
    c.maybe_refresh()
    t[0] = 3000.0
    c.maybe_refresh()
    t[0] = 3700.0
    c.maybe_refresh()
    assert len(calls) == 4                                               # two servers, two refreshes


def test_sntp_offset_against_a_local_time_server():
    srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    srv.bind(("127.0.0.1", 0))
    port = srv.getsockname()[1]

    def serve():
        data, addr = srv.recvfrom(48)
        import time
        now = time.time() + 2.5                                          # this server is 2.5 s ahead of the PC
        sec = int(now) + NTP_EPOCH
        frac = int((now % 1) * 2**32)
        reply = bytearray(48)
        reply[0], reply[1] = 0x24, 2                                     # version 4, server mode; stratum 2
        reply[32:40] = struct.pack("!II", sec, frac)
        reply[40:48] = struct.pack("!II", sec, frac)
        srv.sendto(bytes(reply), addr)

    th = threading.Thread(target=serve)
    th.start()
    try:
        off, rtt = sntp_offset("127.0.0.1", timeout=2.0, port=port)
    finally:
        th.join()
        srv.close()
    assert off == pytest.approx(2.5, abs=0.05) and 0 <= rtt < 0.5
