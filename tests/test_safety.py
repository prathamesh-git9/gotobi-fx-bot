"""Regression tests for the independent review (codex_audit/bot_review/REPORT.md). Each scenario produced an unsafe
outcome before the fix; each test now checks the safe one."""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace

import pytest

from bot.broker import BrokerUnavailable, MT5Broker
from bot.clock import Clock
from bot.engine import Engine, StartupError
from bot.fake_mt5 import FakeMT5
from bot.journal import Journal
from conftest import FULL_CFG, Rig, dip, utc


def with_account(fake, **changes):
    """Make the terminal report a different account (login, server, demo/real) from now on."""
    real = fake.account_info

    def info():
        a = real()
        return None if a is None else SimpleNamespace(**{**vars(a), **changes})
    fake.account_info = info
    return real


def buys(fake):
    return [d for d in fake.deal_log if d.entry == fake.DEAL_ENTRY_IN and d.type == fake.DEAL_TYPE_BUY]


# ------------------------------------------------------------------ the account (review findings 1, 10, 17)
def test_switching_the_terminal_to_a_real_account_pauses_the_bot(tmp_path, week):
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    rig.fake.trade_mode = rig.fake.ACCOUNT_TRADE_MODE_REAL
    rig.run("2026-10-14 15:50", "2026-10-15 01:30")
    assert not rig.opens() and rig.journal.get("2026-10-15") is None


def test_another_account_in_the_terminal_pauses_everything_until_it_is_back(tmp_path, week):
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    rig.run("2026-10-14 15:55", "2026-10-14 16:00")
    assert rig.journal.get("2026-10-15")["status"] == "open"
    real = with_account(rig.fake, login=99999)
    rig.run("2026-10-14 16:01", "2026-10-15 00:56")          # the exit time passes while it is on another account
    assert rig.journal.get("2026-10-15")["status"] == "open"  # not closed, not written off as "unknown"
    assert not rig.closes()
    rig.fake.account_info = real
    rig.run("2026-10-15 00:57", "2026-10-15 00:58")
    rec = rig.journal.get("2026-10-15")
    assert rec["status"] == "closed" and rec["reason"] == "time"


def test_a_state_folder_with_another_accounts_open_trade_is_refused(tmp_path, week):
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    rig.run("2026-10-14 15:55", "2026-10-14 16:00")
    j = Journal(tmp_path, durable=False)
    j.account = [99999, "Other-Server"]
    j.save()
    with pytest.raises(StartupError, match="belongs to account 99999"):
        rig.start("2026-10-14 16:30")


def test_preflight_on_a_real_account_needs_both_keys(tmp_path, week):
    fake = FakeMT5(week, 1.17)
    fake.trade_mode = fake.ACCOUNT_TRADE_MODE_REAL
    now = utc("2026-10-14 15:00")
    fake.set_time(now)
    for flag in (False, True):
        e = Engine(replace(FULL_CFG, allow_live=True), MT5Broker(fake), Journal(tmp_path / str(flag), durable=False),
                   allow_live_flag=flag)
        e.startup(now, inspect_only=True)
        ready, report = e.preflight(now)
        assert ready is flag, report


# ------------------------------------------------------------------ positions the bot did not open (finding 6)
def test_a_position_the_bot_did_not_open_blocks_new_trades(tmp_path, week):
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    rig.fake.set_time(utc("2026-10-14 15:54"))
    manual = rig.fake.order_send({"action": rig.fake.TRADE_ACTION_DEAL, "symbol": rig.fake.name, "volume": 0.01,
                                  "type": rig.fake.ORDER_TYPE_SELL, "price": 150.0, "magic": 0,
                                  "type_time": rig.fake.ORDER_TIME_GTC, "type_filling": rig.fake.ORDER_FILLING_IOC})
    assert manual.retcode == rig.fake.TRADE_RETCODE_DONE
    rig.run("2026-10-14 15:55", "2026-10-15 01:30")
    assert {p.magic for p in rig.fake.positions.values()} == {0}       # the manual trade, untouched
    assert not buys(rig.fake)
    assert rig.journal.get("2026-10-15") is None and rig.journal.get("2026-10-15/short") is None


# ------------------------------------------------------------------ orders of unknown outcome (findings 2, 9)
def test_a_lost_order_reply_never_becomes_a_second_trade(tmp_path, week):
    dip(week, "2026-10-14 15:56", 149.0)                    # the buy is stopped out the next minute
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    send, lost = rig.fake.order_send, [True]

    def reply_lost(req):
        r = send(req)
        if lost[0] and not req.get("position"):
            lost[0] = False
            return None                     # the broker filled it; the confirmation never reached the bot
        return r
    rig.fake.order_send = reply_lost
    rig.run("2026-10-14 15:55", "2026-10-14 15:55")
    rig.run("2026-10-14 15:57", "2026-10-14 17:00")         # next poll: the position is already gone
    assert len(buys(rig.fake)) == 1
    rec = rig.journal.get("2026-10-15")
    assert rec["status"] == "closed" and rec["reason"] == "stop" and rec.get("recovered")
    assert rec["risk_amount"] and rec["r"] == pytest.approx(rec["pnl"] / rec["risk_amount"], abs=1e-3)  # R counts


def test_a_lost_reply_is_checked_against_the_open_position_second_by_second(tmp_path, week):
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    send, lost = rig.fake.order_send, [True]

    def reply_lost(req):
        r = send(req)
        if lost[0] and not req.get("position"):
            lost[0] = False
            return None
        return r
    rig.fake.order_send = reply_lost
    rig.run("2026-10-14 15:55", "2026-10-14 15:56", every_sec=1)
    assert len(buys(rig.fake)) == 1
    assert rig.journal.get("2026-10-15")["status"] == "open"


def test_an_order_with_no_answer_is_never_sent_twice(tmp_path, week):
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    send, attempts = rig.fake.order_send, []

    def drop_first(req):
        if not req.get("position") and req["type"] == rig.fake.ORDER_TYPE_BUY:
            attempts.append(req)
            if len(attempts) == 1:
                return None                 # no answer: it may or may not have reached the broker
        return send(req)
    rig.fake.order_send = drop_first
    rig.run("2026-10-14 15:55", "2026-10-15 01:30")
    assert len(attempts) == 1 and not buys(rig.fake)          # one attempt only, never resent
    assert rig.journal.get("2026-10-15")["status"] == "missed"
    assert rig.journal.get("2026-10-15/short")["status"] == "closed"   # the unresolved long did not block the short


def placed_once(rig, fill_later: list | None = None, attempts: list | None = None):
    """The first entry order comes back only as "placed" (queued). With fill_later, the queued order is kept
    so the test can let the broker fill it later; otherwise it never fills."""
    send = rig.fake.order_send
    attempts = [] if attempts is None else attempts

    def only_placed(req):
        if not req.get("position") and req["type"] == rig.fake.ORDER_TYPE_BUY:
            attempts.append(req)
            if len(attempts) == 1:
                if fill_later is not None:
                    fill_later.append(req)
                return SimpleNamespace(retcode=rig.fake.TRADE_RETCODE_PLACED, deal=0, order=4242, volume=0.0,
                                       price=0.0, comment="placed", request=SimpleNamespace(**req))
        return send(req)
    rig.fake.order_send = only_placed
    return send


def test_an_order_reported_only_as_placed_is_not_sent_again(tmp_path, week):
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    attempts = []
    placed_once(rig, attempts=attempts)
    rig.run("2026-10-14 15:55", "2026-10-15 01:30")
    assert len(attempts) == 1 and not buys(rig.fake)
    assert rig.journal.get("2026-10-15")["status"] == "missed"


def test_a_placed_order_that_fills_later_is_adopted_not_duplicated(tmp_path, week):
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    queued = []
    send = placed_once(rig, queued)
    rig.run("2026-10-14 15:55", "2026-10-14 15:58")
    rig.fake.set_time(utc("2026-10-14 15:59"))
    send(queued[0])                                           # the broker fills the queued order at 15:59
    rig.run("2026-10-14 16:00", "2026-10-15 01:30")
    assert len(buys(rig.fake)) == 1
    rec = rig.journal.get("2026-10-15")
    assert rec["status"] == "closed" and rec.get("adopted") and rec["risk_amount"] and rec["r"] is not None


def queue_first_buy(rig):
    """The broker answers the first entry with "placed" and really queues it as a live order."""
    send, attempts = rig.fake.order_send, []

    def queued(req):
        if not req.get("position") and req.get("action") == rig.fake.TRADE_ACTION_DEAL \
                and req["type"] == rig.fake.ORDER_TYPE_BUY:
            attempts.append(req)
            if len(attempts) == 1:
                t = rig.fake.queue_order(req)
                return SimpleNamespace(retcode=rig.fake.TRADE_RETCODE_PLACED, deal=0, order=t, volume=0.0,
                                       price=0.0, comment="placed", request=SimpleNamespace(**req))
        return send(req)
    rig.fake.order_send = queued
    return attempts


def test_a_queued_order_is_cancelled_and_can_never_overlap_the_short(tmp_path, week):
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    attempts = queue_first_buy(rig)
    worst = 0
    t = utc("2026-10-14 15:55")
    while t <= utc("2026-10-15 01:30"):
        rig.fake.set_time(t)
        rig.engine.step(t)
        worst = max(worst, len(rig.fake.positions))
        t += timedelta(seconds=60)
    assert not rig.fake.orders and len(attempts) == 1 and not buys(rig.fake)      # cancelled, never resent
    assert rig.journal.get("2026-10-15")["status"] == "missed"
    assert rig.journal.get("2026-10-15/short")["status"] == "closed" and worst <= 1


def refuse_cancels(rig):
    """The broker refuses to cancel live orders (they stay queued)."""
    send = rig.fake.order_send

    def no_cancel(req):
        if req.get("action") == rig.fake.TRADE_ACTION_REMOVE:
            return SimpleNamespace(retcode=rig.fake.TRADE_RETCODE_INVALID, deal=0, order=req["order"], volume=0.0,
                                   price=0.0, comment="cannot cancel", request=SimpleNamespace(**req))
        return send(req)
    rig.fake.order_send = no_cancel


def test_a_live_order_the_journal_does_not_know_blocks_new_trades(tmp_path, week):
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    t = rig.fake.queue_order({"action": rig.fake.TRADE_ACTION_DEAL, "symbol": rig.fake.name, "volume": 0.31,
                              "type": rig.fake.ORDER_TYPE_BUY, "price": 150.01, "magic": FULL_CFG.magic,
                              "comment": "gotobi 2026-10-15"})        # left by an earlier run whose state was lost
    refuse_cancels(rig)
    rig.run("2026-10-14 15:55", "2026-10-14 16:30")
    assert t in rig.fake.orders and not buys(rig.fake) and rig.journal.get("2026-10-15") is None


def test_a_still_live_order_keeps_its_trade_pending_and_a_late_fill_keeps_its_risk(tmp_path, week):
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    queue_first_buy(rig)
    refuse_cancels(rig)
    rig.run("2026-10-14 15:55", "2026-10-15 00:57")             # past the long's exit, the order still queued
    assert rig.journal.get("2026-10-15")["status"] == "unknown"  # not called missed while it can still fill
    assert rig.journal.get("2026-10-15/short") is None           # and nothing else opened
    rig.fake.fill_order(next(iter(rig.fake.orders)))             # it fills late
    rig.run("2026-10-15 00:58", "2026-10-15 01:00")
    rec = rig.journal.get("2026-10-15")
    assert rec["status"] == "closed" and rec["risk_amount"] and rec["r"] is not None and len(buys(rig.fake)) == 1


def test_a_queued_order_that_fills_before_the_cancel_is_adopted(tmp_path, week):
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    queue_first_buy(rig)
    rig.fake.set_time(utc("2026-10-14 15:55"))
    rig.engine.step(utc("2026-10-14 15:55"))
    rig.fake.fill_order(next(iter(rig.fake.orders)))          # the broker fills it before the bot's next poll
    rig.run("2026-10-14 15:56", "2026-10-15 01:30")
    assert len(buys(rig.fake)) == 1
    rec = rig.journal.get("2026-10-15")
    assert rec["status"] == "closed" and rec.get("adopted") and rec["r"] is not None


def test_mt5_answering_none_for_an_empty_list_is_not_an_error(tmp_path, week):
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    positions, orders = rig.fake.positions_get, rig.fake.orders_get

    def none_when_empty(real):
        def call(*a, **k):
            out = real(*a, **k)
            if out == ():
                rig.fake.error = (1, "Success")
                return None                  # some MT5 builds say "nothing" this way
            return out
        return call
    rig.fake.positions_get, rig.fake.orders_get = none_when_empty(positions), none_when_empty(orders)
    rig.run("2026-10-14 15:55", "2026-10-15 01:30")
    assert rig.journal.get("2026-10-15")["status"] == "closed" and len(buys(rig.fake)) == 1


def test_a_fill_followed_by_a_failed_position_read_is_not_sent_again(tmp_path, week):
    dip(week, "2026-10-14 15:56", 149.0)                     # and it is stopped out the next minute
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    send = rig.fake.order_send

    def filled_then_read_fails(req):
        r = send(req)
        if not req.get("position"):
            rig.fake.positions_fail = 2                      # the bot's next position reads fail
        return r
    rig.fake.order_send = filled_then_read_fails
    rig.fake.set_time(utc("2026-10-14 15:55"))
    with pytest.raises(BrokerUnavailable):
        rig.engine.step(utc("2026-10-14 15:55"))
    rig.fake.positions_fail = 0
    rig.run("2026-10-14 15:57", "2026-10-14 17:00")
    assert len(buys(rig.fake)) == 1
    rec = rig.journal.get("2026-10-15")
    assert rec["status"] == "closed" and rec["reason"] == "stop"


# ------------------------------------------------------------------ the short's deadline (finding 4)
def test_the_short_is_not_sent_once_a_slow_terminal_has_used_up_the_window(tmp_path, week):
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-15 00:54:50")
    clock = [utc("2026-10-15 00:54:59")]
    rig.engine.now_fn = lambda: clock[0]
    info = rig.fake.symbol_info

    def busy(symbol):                       # the terminal takes 7 s to answer at the fix
        clock[0] = utc("2026-10-15 00:55:06")
        return info(symbol)
    rig.fake.symbol_info = busy
    rig.fake.set_time(utc("2026-10-15 00:54:59"))
    rig.engine.step(utc("2026-10-15 00:54:59"))
    assert not [r for r in rig.opens() if r["type"] == rig.fake.ORDER_TYPE_SELL]
    assert rig.journal.get("2026-10-15/short")["status"] == "missed"


def test_the_short_records_when_it_was_really_sent(tmp_path, week):
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-15 00:54:50")
    rig.engine.now_fn = lambda: utc("2026-10-15 00:54:59.400")
    rig.fake.set_time(utc("2026-10-15 00:54:59"))
    rig.engine.step(utc("2026-10-15 00:54:59"))
    rec = rig.journal.get("2026-10-15/short")
    assert rec["status"] == "open" and rec["sent_vs_fix_sec"] == pytest.approx(-0.6)


def test_the_short_needs_a_clock_checked_by_time_servers(tmp_path, week):
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-15 00:54:50")
    rig.engine.clock_ok = lambda: False                       # UDP 123 blocked: the PC clock cannot be checked
    rig.fake.set_time(utc("2026-10-15 00:54:59"))
    rig.engine.step(utc("2026-10-15 00:54:59"))
    rec = rig.journal.get("2026-10-15/short")
    assert rec["status"] == "skipped" and "time servers" in rec["note"] and not rig.opens()


def test_an_unchecked_pc_clock_a_minute_off_the_broker_blocks_the_long(tmp_path, week):
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:40")
    rig.engine.clock_ok = lambda: False
    t = utc("2026-10-14 15:40")
    while t <= utc("2026-10-14 16:30"):                       # the PC clock runs 60 s ahead of the market
        rig.fake.set_time(t)
        rig.engine.step(t + timedelta(seconds=60))
        t += timedelta(seconds=60)
    assert not rig.opens()
    assert rig.engine.clock_suspect() == pytest.approx(60, abs=1)


def test_an_unchecked_clock_is_compared_with_live_prices_before_the_first_entry(tmp_path, week):
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:53:30")    # restarted a moment before 15:55
    rig.engine.clock_ok = lambda: False
    t = utc("2026-10-14 15:53:30")
    while t <= utc("2026-10-14 16:10"):                       # the PC clock runs 60 s ahead of the market
        rig.fake.set_time(t)
        rig.engine.step(t + timedelta(seconds=60))
        t += timedelta(seconds=20)
    assert not rig.opens()                                    # no buy at the physical 15:54


def test_the_stop_and_target_come_from_the_price_the_order_is_sent_at(tmp_path, week):
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    tick, calls = rig.fake.symbol_info_tick, [0]

    def moving(symbol):                                       # the market jumps 10 pips between sizing and sending
        calls[0] += 1
        t = tick(symbol)
        return t if calls[0] % 2 else SimpleNamespace(**{**vars(t), "bid": t.bid + 0.10, "ask": t.ask + 0.10})
    rig.fake.symbol_info_tick = moving
    rig.fake.set_time(utc("2026-10-14 15:55"))
    rig.engine.step(utc("2026-10-14 15:55"))
    req = rig.opens()[0]
    assert req["sl"] == pytest.approx(req["price"] - 0.55) and req["tp"] == pytest.approx(req["price"] + 0.30)


# ------------------------------------------------------------------ the kill switch while flat (finding 7)
def test_a_fall_in_equity_while_flat_trips_the_kill_switch_before_the_next_entry(tmp_path, week):
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    rig.fake.balance = 400.0                # money went elsewhere (manual trades, a withdrawal) while flat
    rig.run("2026-10-14 15:55", "2026-10-14 16:00")
    assert not rig.opens() and rig.journal.halted
    assert rig.journal.get("2026-10-15")["status"] == "skipped"


def test_exactly_half_the_peak_trips_the_kill_switch(tmp_path, week):
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    rig.fake.balance = 500.0                # peak 1,000
    rig.run("2026-10-14 15:55", "2026-10-14 15:56")
    assert rig.journal.halted and not rig.opens()


# ------------------------------------------------------------------ a damaged state file (finding 8)
def test_an_unreadable_state_file_falls_back_to_the_backup(tmp_path, week):
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    rig.run("2026-10-14 15:55", "2026-10-14 16:00")         # the long is open
    Journal(tmp_path)                                         # a restart: state.json reads cleanly, backup made
    (tmp_path / "state.json").write_text('{"slots":', encoding="utf-8")      # then the file is damaged
    rig.start("2026-10-14 18:00")
    assert rig.journal.recovered_from == "backup"
    assert rig.journal.get("2026-10-15")["status"] == "open"
    rig.run("2026-10-14 18:00", "2026-10-15 01:30")
    assert rig.journal.get("2026-10-15")["status"] == "closed"
    assert len(buys(rig.fake)) == 1
    assert list(tmp_path.glob("state.corrupt-*.json"))


def test_without_a_backup_open_trades_are_managed_and_nothing_new_opens(tmp_path, week):
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    rig.run("2026-10-14 15:55", "2026-10-14 16:00")
    (tmp_path / "state.json").write_text("not json at all", encoding="utf-8")
    (tmp_path / "state.json.bak").unlink(missing_ok=True)
    rig.start("2026-10-14 18:00")
    assert rig.journal.recovered_from == "nothing"
    rec = rig.journal.get("2026-10-15")
    assert rec["status"] == "open" and rec.get("adopted")    # taken back from the broker's open position
    rig.run("2026-10-14 18:00", "2026-10-15 01:30")
    assert rig.journal.get("2026-10-15")["status"] == "closed" and len(buys(rig.fake)) == 1
    assert rig.journal.halted and rig.journal.get("2026-10-15/short")["status"] == "skipped"   # nothing new


def test_the_backup_keeps_the_kill_switch(tmp_path, week):
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    rig.journal.halt("test halt", utc("2026-10-14 15:50"))
    (tmp_path / "state.json").write_text('{"slots": [', encoding="utf-8")       # damaged after the halt
    rig.start("2026-10-14 15:52")
    assert rig.journal.recovered_from == "backup" and rig.journal.halted["reason"] == "test halt"
    rig.run("2026-10-14 15:55", "2026-10-14 16:00")
    assert not rig.opens()


@pytest.mark.parametrize("bad", ['{"slots": []}',                                   # parses, but is not a journal
                                 '{"slots": {}, "halted": {"reason": "x"}}',         # a halt with no time
                                 '{"slots": {"2026-10-15": {"status": "open"}}}',    # an open trade with no ticket
                                 '{"slots": {"2026-10-15": {"status": "closed", "r": "lots"}}}'])
def test_valid_json_of_the_wrong_shape_counts_as_damaged(tmp_path, week, bad):
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    rig.run("2026-10-14 15:55", "2026-10-14 16:00")
    (tmp_path / "state.json").write_text(bad, encoding="utf-8")
    rig.start("2026-10-14 18:00")
    assert rig.journal.recovered_from == "backup" and rig.journal.get("2026-10-15")["status"] == "open"


def test_the_halted_file_keeps_the_kill_switch_when_the_backup_is_stale(tmp_path, week):
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    stale = (tmp_path / "state.json.bak").read_bytes() if (tmp_path / "state.json.bak").exists() else b'{"slots": {}}'
    rig.journal.halt("lost 6R", utc("2026-10-14 15:51"))
    (tmp_path / "state.json.bak").write_bytes(stale)                 # the backup update failed: no halt in it
    (tmp_path / "state.json").write_text("damaged", encoding="utf-8")
    rig.start("2026-10-14 15:52")
    assert rig.journal.recovered_from == "backup" and rig.journal.halted
    rig.run("2026-10-14 15:55", "2026-10-14 16:00")
    assert not rig.opens()


@pytest.mark.parametrize("cleared", [False, True])
def test_clear_halt_restarts_the_losing_streak_window(tmp_path, week, cleared):
    j = Journal(tmp_path, durable=False)
    for i in range(60):                                           # 60 losing longs: -12R in the window
        j.slots[f"2026-0{1 + i // 28}-{1 + i % 28:02d}"] = {"status": "closed", "r": -0.2, "pnl": -2.0,
                                                           "closed": "2026-06-01T00:54:00+00:00"}
    j.halt("the last 60 trades lost -12.0R", utc("2026-06-01 00:54"))
    if cleared:
        j.clear_halt()                                            # what --clear-halt does
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    rig.run("2026-10-14 15:55", "2026-10-14 16:00")
    if cleared:   # resumed, and the old losing run does not trip it again at once
        assert not rig.journal.halted and len(buys(rig.fake)) == 1
    else:
        assert rig.journal.halted and not rig.opens()


def test_clear_halt_switches_the_kill_switch_off_without_editing_json(tmp_path):
    import logging

    from bot.main import main
    j = Journal(tmp_path / "state", durable=False)
    j.set_peak(1000.0)
    j.halt("lost 6R", utc("2026-10-14 15:50"))
    cfg = tmp_path / "c.toml"
    cfg.write_text(f'state_dir = "{(tmp_path / "state").as_posix()}"\n', encoding="utf-8")
    saved = logging.getLogger().handlers[:]
    try:
        assert main(["--config", str(cfg), "--clear-halt"]) == 0
    finally:
        for h in logging.getLogger().handlers:
            h.close()
        logging.getLogger().handlers[:] = saved
    j = Journal(tmp_path / "state", durable=False)
    assert j.halted is None and j.peak_balance is None


# ------------------------------------------------------------------ an unreadable trade history (finding 13)
def test_a_history_error_is_not_taken_for_a_trade_without_deals(tmp_path, week):
    dip(week, "2026-10-14 16:05", 149.0)                    # stopped out at 16:05
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    rig.run("2026-10-14 15:55", "2026-10-14 16:00")
    history = rig.fake.history_deals_get

    def broken(*a, **k):
        rig.fake.error = (-10004, "No IPC connection")
        return None
    rig.fake.history_deals_get = broken
    rig.run("2026-10-14 16:05", "2026-10-15 00:56")          # hours of polls without a readable history
    assert rig.journal.get("2026-10-15")["status"] == "open"  # never written off as "unknown"
    assert rig.journal.get("2026-10-15/short") is None        # and nothing new opened meanwhile
    rig.fake.history_deals_get = history
    rig.run("2026-10-15 00:57", "2026-10-15 00:57")
    rec = rig.journal.get("2026-10-15")
    assert rec["status"] == "closed" and rec["reason"] == "stop" and rec["r"] is not None


def test_a_missing_closing_deal_is_never_written_off(tmp_path, week):
    dip(week, "2026-10-14 16:05", 149.0)                    # stopped out at 16:05
    rig = Rig(week, tmp_path, cfg=FULL_CFG, start="2026-10-14 15:50")
    rig.run("2026-10-14 15:55", "2026-10-14 16:00")
    history = rig.fake.history_deals_get

    def entries_only(*a, **k):                               # the history answers, but without the closing deal
        out = history(*a, **k)
        return None if out is None else tuple(d for d in out if d.entry == rig.fake.DEAL_ENTRY_IN)
    rig.fake.history_deals_get = entries_only
    rig.run("2026-10-14 16:05", "2026-10-15 00:56")
    assert rig.journal.get("2026-10-15")["status"] == "open"  # still unresolved, not "unknown"
    assert rig.journal.get("2026-10-15/short") is None        # and nothing new opened meanwhile
    rig.fake.history_deals_get = history
    rig.run("2026-10-15 00:57", "2026-10-15 00:57")
    rec = rig.journal.get("2026-10-15")
    assert rec["status"] == "closed" and rec["reason"] == "stop" and rec["r"] is not None


# ------------------------------------------------------------------ the clock (finding 5)
def test_the_clock_follows_a_windows_time_reset_without_a_jump():
    t = {"wall": 1000.0, "mono": 50.0}
    calls = []
    c = Clock(("a", "b"), query=lambda h: calls.append(h) or (20.0, 0.01), wall=lambda: t["wall"],
              mono=lambda: t["mono"])
    assert c.refresh() and len(calls) == 2                  # the PC was 20 s slow
    t["wall"] += 10
    t["mono"] += 10
    assert c.now().timestamp() == pytest.approx(1030.0)
    t["wall"] += 25                                          # Windows puts its clock right (+20 s) as 5 s pass
    t["mono"] += 5
    assert c.now().timestamp() == pytest.approx(1035.0)      # the bot's time stays continuous, not 20 s ahead
    c.maybe_refresh()
    assert len(calls) == 4                                   # and it asks the time servers again


def test_the_clock_counts_as_verified_only_while_servers_confirm_it():
    t, up = [0.0], [False]

    def query(h):
        if not up[0]:
            raise OSError("UDP 123 blocked")
        return 0.3, 0.01
    c = Clock(("a", "b"), query=query, wall=lambda: 1e9 + t[0], mono=lambda: t[0])
    assert not c.refresh() and not c.verified()
    up[0] = True
    assert c.refresh() and c.verified()
    up[0] = False
    t[0] += 13 * 3600
    c.maybe_refresh()
    assert not c.verified() and c.offset == pytest.approx(0.3)
