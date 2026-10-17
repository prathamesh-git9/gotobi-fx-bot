"""Engine behaviour on the MT5 simulator: lifecycle, restarts, outages, stops, errors, guards, kill switch."""
from dataclasses import replace
from datetime import timedelta

import pytest

from bot.broker import BrokerUnavailable
from bot.engine import LiveAccountRefused, StartupError
from conftest import TEST_CFG, Rig, dip, make_bars, set_spread, utc

GOTOBI = "2026-10-15"            # Thursday: buy Wed 14 Oct 15:55 UTC, close Thu 15 Oct 00:54 UTC


def test_full_trade_lifecycle(week, tmp_path):
    rig = Rig(week, tmp_path, start="2026-10-14 12:00")
    rig.run("2026-10-14 12:00", "2026-10-15 02:00")
    opens, closes = rig.opens(), rig.closes()
    assert len(opens) == 1 and len(closes) == 1
    o = opens[0]
    assert o["type"] == rig.fake.ORDER_TYPE_BUY and o["magic"] == TEST_CFG.magic and o["comment"] == f"gotobi {GOTOBI}"
    assert o["sl"] == pytest.approx(150.010 - 0.55)                      # ask - 55 pips
    rec = rig.journal.get(GOTOBI)
    assert rec["status"] == "closed" and rec["reason"] == "time"
    assert rec["opened"] == "2026-10-14T15:55:00+00:00"
    assert rec["closed"] == "2026-10-15T00:54:00+00:00"
    assert rec["pnl"] == pytest.approx(rig.fake.balance - 1000.0, abs=0.01)
    assert len(rig.journal.slots) == 1                                   # no other day touched


def test_position_size_matches_risk(week, tmp_path):
    rig = Rig(week, tmp_path, start="2026-10-14 15:50")
    rig.run("2026-10-14 15:50", "2026-10-14 15:56")
    rec = rig.journal.get(GOTOBI)
    lots, risk = rec["volume"], rec["risk_amount"]
    # 10% of EUR 1,000 at a 55-pip stop: 1 lot loses 100,000 * 0.55 / 149.46 / 1.17 = EUR 314.5
    assert lots == 0.31 and risk <= 100.0 and risk > 100.0 - 314.5 * 0.01


def test_repeated_polls_and_restart_never_double_enter(week, tmp_path):
    rig = Rig(week, tmp_path, start="2026-10-14 15:54")
    rig.run("2026-10-14 15:54", "2026-10-14 15:56", every_sec=5)
    rig.start("2026-10-14 15:57")                                        # crash + restart from saved state
    rig.run("2026-10-14 15:57", "2026-10-15 01:00")
    assert len(rig.opens()) == 1 and len(rig.closes()) == 1


def test_missed_exit_is_closed_immediately_after_restart(week, tmp_path):
    rig = Rig(week, tmp_path, start="2026-10-14 15:50")
    rig.run("2026-10-14 15:50", "2026-10-15 00:30")                      # bot dies at 00:30
    rig.start("2026-10-15 03:00")                                        # back at 03:00
    rig.run("2026-10-15 03:00", "2026-10-15 03:05")
    rec = rig.journal.get(GOTOBI)
    assert rec["status"] == "closed" and rec["reason"] == "time"
    assert rec["exit_sent"] == "2026-10-15T03:00:00+00:00" and rec["exit_late_sec"] == 7560


def test_stop_loss_hit_is_recorded(week, tmp_path):
    dip(week, "2026-10-14 18:00", 149.40)                                # below the 149.46 stop
    rig = Rig(week, tmp_path, start="2026-10-14 15:50")
    rig.run("2026-10-14 15:50", "2026-10-15 01:00")
    rec = rig.journal.get(GOTOBI)
    assert rec["status"] == "closed" and rec["reason"] == "stop"
    assert rec["closed"] == "2026-10-14T18:00:00+00:00"
    assert rec["r"] == pytest.approx(-1.0, abs=0.03)
    assert rig.closes() == []                                            # the broker closed it, not the bot


def test_monday_gotobi_waits_for_reopen_plus_15_minutes(tmp_path):
    bars = make_bars("2026-10-01 00:00", "2026-10-05 12:00")             # shut Fri 21:00 -> Sun 21:05
    rig = Rig(bars, tmp_path, start="2026-10-04 15:00")
    rig.run("2026-10-04 15:00", "2026-10-05 01:00")
    rec = rig.journal.get("2026-10-05")
    assert rec["opened"] == "2026-10-04T21:20:00+00:00"                  # reopen 21:05 + 15 min
    assert rec["status"] == "closed" and rec["closed"] == "2026-10-05T00:54:00+00:00"


def test_wide_spread_delays_entry(week, tmp_path):
    set_spread(week, "2026-10-14 15:50", "2026-10-14 16:10", 0.08)      # 8 pips
    rig = Rig(week, tmp_path, start="2026-10-14 15:50")
    rig.run("2026-10-14 15:50", "2026-10-14 16:20")
    assert rig.journal.get(GOTOBI)["opened"] == "2026-10-14T16:10:00+00:00"


def test_spread_that_never_normalises_means_missed(week, tmp_path):
    set_spread(week, "2026-10-14 15:50", "2026-10-15 01:00", 0.08)
    rig = Rig(week, tmp_path, start="2026-10-14 15:50")
    rig.run("2026-10-14 15:50", "2026-10-14 18:00")
    rec = rig.journal.get(GOTOBI)
    assert rec["status"] == "missed" and rig.opens() == []
    assert rec["at"] == "2026-10-14T17:56:00+00:00"                      # first poll after 15:55 + 120 min


@pytest.mark.parametrize("start, entered", [("2026-10-14 17:00", True), ("2026-10-14 17:56", False)])
def test_late_start(week, tmp_path, start, entered):
    rig = Rig(week, tmp_path, start=start)
    rig.run(start, "2026-10-14 18:30")
    assert (rig.journal.get(GOTOBI)["status"] == "open") is entered


def test_transient_errors_are_retried(week, tmp_path):
    rig = Rig(week, tmp_path, start="2026-10-14 15:50")
    rig.fake.fail_next("open", rig.fake.TRADE_RETCODE_REQUOTE, 2)
    rig.fake.fail_next("open", None, 1)                                  # terminal does not answer once
    rig.run("2026-10-14 15:50", "2026-10-14 16:05")
    assert len(rig.opens()) == 4 and len(rig.fake.positions) == 1
    assert rig.journal.get(GOTOBI)["opened"] == "2026-10-14T15:58:00+00:00"


def test_fatal_error_skips_the_day(week, tmp_path):
    rig = Rig(week, tmp_path, start="2026-10-14 15:50")
    rig.fake.fail_next("open", rig.fake.TRADE_RETCODE_NO_MONEY, 1)
    rig.run("2026-10-14 15:50", "2026-10-15 01:00")
    rec = rig.journal.get(GOTOBI)
    assert rec["status"] == "skipped" and "10019" in rec["note"] and len(rig.opens()) == 1


def test_unsupported_filling_mode_falls_back(week, tmp_path):
    rig = Rig(week, tmp_path, start="2026-10-14 15:50", filling_mode=3)
    rig.fake.fail_next("open", rig.fake.TRADE_RETCODE_INVALID_FILL, 1)
    rig.run("2026-10-14 15:50", "2026-10-14 15:56")
    fills = [r["type_filling"] for r in rig.opens()]
    assert fills == [rig.fake.ORDER_FILLING_FOK, rig.fake.ORDER_FILLING_IOC] and len(rig.fake.positions) == 1


def test_close_failures_are_retried_until_closed(week, tmp_path):
    rig = Rig(week, tmp_path, start="2026-10-14 15:50")
    rig.fake.fail_next("close", rig.fake.TRADE_RETCODE_PRICE_OFF, 3)
    rig.run("2026-10-14 15:50", "2026-10-15 01:00")
    assert len(rig.closes()) == 4 and rig.journal.get(GOTOBI)["status"] == "closed"


def test_positions_error_aborts_the_poll_instead_of_double_entering(week, tmp_path):
    rig = Rig(week, tmp_path, start="2026-10-14 15:50")
    rig.run("2026-10-14 15:50", "2026-10-14 15:56")
    rig.fake.positions_fail = 1
    rig.fake.set_time(utc("2026-10-14 15:57"))
    with pytest.raises(BrokerUnavailable):
        rig.engine.step(utc("2026-10-14 15:57"))
    rig.run("2026-10-14 15:58", "2026-10-15 01:00")
    assert len(rig.opens()) == 1 and len(rig.closes()) == 1


def test_real_account_is_refused_without_both_keys(week, tmp_path):
    rig = Rig(week, tmp_path, trade_mode=2)
    with pytest.raises(LiveAccountRefused):
        rig.start("2026-10-14 15:50")
    with pytest.raises(LiveAccountRefused):
        rig.start("2026-10-14 15:50", allow_live_flag=True)              # flag without config
    rig.cfg = replace(TEST_CFG, allow_live=True)
    with pytest.raises(LiveAccountRefused):
        rig.start("2026-10-14 15:50")                                    # config without flag
    rig.start("2026-10-14 15:50", allow_live_flag=True)                  # both: allowed
    assert rig.fake.requests == []


def test_kill_switch_after_losing_run(week, tmp_path):
    dip(week, "2026-10-14 18:00", 149.40)
    rig = Rig(week, tmp_path)
    j = rig.start("2026-10-14 15:50").journal
    for i in range(59):                                                  # 59 earlier trades at -0.1R
        j.slots[f"2020-01-{i:03d}"] = {"status": "closed", "r": -0.1, "pnl": -1.0}
    rig.run("2026-10-14 15:50", "2026-10-15 01:00")                      # 60th trade is stopped out (-1R)
    assert j.halted and "last 60 trades" in j.halted["reason"]


def test_kill_switch_blocks_new_entries_but_not_exits(week, tmp_path):
    rig = Rig(week, tmp_path, start="2026-10-14 15:50")
    rig.run("2026-10-14 15:50", "2026-10-14 16:00")
    rig.journal.halt("test", utc("2026-10-14 16:00"))
    rig.run("2026-10-14 16:00", "2026-10-15 01:00")
    assert rig.journal.get(GOTOBI)["status"] == "closed"                 # still closed on time
    bars = make_bars("2026-10-11 21:05", "2026-10-21 20:59")
    rig2 = Rig(bars, tmp_path / "b", start="2026-10-19 12:00")
    rig2.journal.halt("test", utc("2026-10-19 12:00"))
    rig2.run("2026-10-19 12:00", "2026-10-20 01:00")
    assert rig2.journal.get("2026-10-20")["status"] == "skipped" and rig2.opens() == []


def test_drawdown_kill_switch(week, tmp_path):
    dip(week, "2026-10-14 18:00", 149.40)
    rig = Rig(week, tmp_path)
    j = rig.start("2026-10-14 15:50").journal
    j.peak_balance = 1700.0                                              # balance 1,000 is 41% below
    rig.run("2026-10-14 15:50", "2026-10-15 01:00")                      # after the -10% stop: 47% below
    assert j.halted is None
    j.peak_balance = 1850.0
    rig.engine._kill_switch(utc("2026-10-15 01:00"), rig.fake.balance)
    assert j.halted and "below its peak" in j.halted["reason"]


def test_adopts_an_unknown_position_and_closes_it_on_time(week, tmp_path):
    rig = Rig(week, tmp_path)
    rig.fake.set_time(utc("2026-10-14 16:00"))
    rig.fake.order_send({"action": 1, "symbol": "USDJPYm", "volume": 0.1, "type": 0, "price": 150.01, "sl": 149.4,
                         "deviation": 30, "magic": TEST_CFG.magic, "comment": f"gotobi {GOTOBI}",
                         "type_time": 0, "type_filling": 1})
    rig.start("2026-10-14 16:01")                                        # journal is empty (state lost)
    rig.run("2026-10-14 16:01", "2026-10-15 01:00")
    rec = rig.journal.get(GOTOBI)
    assert rec["adopted"] and rec["status"] == "closed" and rec["closed"] == "2026-10-15T00:54:00+00:00"
    assert len(rig.opens()) == 1                                         # adopted, not bought again


def test_manual_close_is_recorded_as_external(week, tmp_path):
    rig = Rig(week, tmp_path, start="2026-10-14 15:50")
    rig.run("2026-10-14 15:50", "2026-10-14 20:00")
    ticket = rig.journal.get(GOTOBI)["ticket"]
    rig.fake.order_send({"action": 1, "symbol": "USDJPYm", "volume": rig.fake.positions[ticket].volume, "type": 1,
                         "price": 150.0, "position": ticket, "deviation": 30, "magic": 0, "comment": "manual",
                         "type_time": 0, "type_filling": 1})
    rig.run("2026-10-14 20:01", "2026-10-15 01:00")
    assert rig.journal.get(GOTOBI)["reason"] == "external" and len(rig.opens()) == 1


def test_non_gotobi_days_are_never_traded(tmp_path):
    bars = make_bars("2026-10-11 21:05", "2026-10-16 20:59")
    rig = Rig(bars, tmp_path, start="2026-10-12 00:00")
    rig.run("2026-10-12 00:00", "2026-10-14 15:54")                      # Mon-Wed before the Thursday slot
    assert rig.fake.requests == [] and rig.journal.slots == {}


def test_dry_run_sends_nothing(week, tmp_path):
    rig = Rig(week, tmp_path)
    rig.start("2026-10-14 15:50", dry_run=True)
    rig.run("2026-10-14 15:50", "2026-10-15 01:00")
    rec = rig.journal.get(GOTOBI)
    assert rig.fake.requests == [] and rec["status"] == "dryrun" and "accepted" in rec["note"]


def test_server_time_offset(week, tmp_path):
    rig = Rig(week, tmp_path, cfg=replace(TEST_CFG, server_utc_offset_hours=2.0), server_offset_h=2.0)
    rig.start("2026-10-14 15:50")
    rig.run("2026-10-14 15:50", "2026-10-15 01:00")
    assert rig.journal.get(GOTOBI)["closed"] == "2026-10-15T00:54:00+00:00"
    wrong = Rig(week, tmp_path / "w", cfg=replace(TEST_CFG, auto_server_offset=False), server_offset_h=2.0)
    with pytest.raises(StartupError, match="future"):                    # server UTC+2, fixed config says 0
        wrong.start("2026-10-14 15:50")


def test_measures_an_unknown_broker_clock_offset(week, tmp_path):
    rig = Rig(week, tmp_path, server_offset_h=3.0, start="2026-10-14 15:50")   # config assumes UTC
    rig.run("2026-10-14 15:50", "2026-10-15 01:00")
    rec = rig.journal.get(GOTOBI)
    assert rig.engine.offset_h == 3.0
    assert rec["opened"] == "2026-10-14T15:55:00+00:00" and rec["closed"] == "2026-10-15T00:54:00+00:00"


def test_follows_a_broker_clock_shift_over_the_weekend(tmp_path):
    bars = make_bars("2026-10-01 00:00", "2026-10-05 12:00")
    rig = Rig(bars, tmp_path, server_offset_h=3.0, start="2026-10-02 12:00")
    rig.run("2026-10-02 12:00", "2026-10-02 13:00")
    assert rig.engine.offset_h == 3.0
    rig.fake.offset_s = 2 * 3600                                         # broker moves UTC+3 -> UTC+2 (DST end)
    rig.run("2026-10-04 15:00", "2026-10-05 01:00")
    rec = rig.journal.get("2026-10-05")
    assert rig.engine.offset_h == 2.0
    assert rec["opened"] == "2026-10-04T21:20:00+00:00" and rec["closed"] == "2026-10-05T00:54:00+00:00"


def test_poll_gap_across_the_close_does_not_fake_an_offset(tmp_path):
    bars = make_bars("2026-10-01 00:00", "2026-10-05 12:00")
    rig = Rig(bars, tmp_path, server_offset_h=3.0, start="2026-10-02 19:59")
    rig.run("2026-10-02 19:59", "2026-10-02 20:01")
    rig.run("2026-10-02 22:00", "2026-10-02 22:00")                      # next poll 2 h later, market shut at 21:00
    assert rig.engine.offset_h == 3.0


def test_algo_trading_off_waits_then_trades(week, tmp_path):
    rig = Rig(week, tmp_path, start="2026-10-14 15:50")
    rig.fake.algo_trading = False
    rig.run("2026-10-14 15:50", "2026-10-14 16:29")
    assert rig.fake.requests == [] and rig.journal.get(GOTOBI) is None
    rig.fake.algo_trading = True
    rig.run("2026-10-14 16:30", "2026-10-15 01:00")
    rec = rig.journal.get(GOTOBI)
    assert rec["opened"] == "2026-10-14T16:30:00+00:00" and rec["status"] == "closed"


def test_python_api_switched_off_until_too_late_means_missed(week, tmp_path):
    rig = Rig(week, tmp_path, start="2026-10-14 15:50")
    rig.fake.tradeapi_disabled = True
    rig.run("2026-10-14 15:50", "2026-10-14 18:30")
    assert rig.fake.requests == [] and rig.journal.get(GOTOBI)["status"] == "missed"


def test_exit_at_fix_when_configured(week, tmp_path):
    rig = Rig(week, tmp_path, cfg=replace(TEST_CFG, exit_minutes_before_fix=0), start="2026-10-14 15:50")
    rig.run("2026-10-14 15:50", "2026-10-15 01:00")
    assert rig.journal.get(GOTOBI)["closed"] == "2026-10-15T00:55:00+00:00"


def test_too_small_account_is_skipped(week, tmp_path):
    rig = Rig(week, tmp_path, cfg=replace(TEST_CFG, risk_pct=0.1), balance=10.0, start="2026-10-14 15:50")
    rig.run("2026-10-14 15:50", "2026-10-14 16:00")
    rec = rig.journal.get(GOTOBI)
    assert rec["status"] == "skipped" and "minimum lot" in rec["note"] and rig.opens() == []


def test_margin_limits_the_size(week, tmp_path):
    rig = Rig(week, tmp_path, leverage=5, start="2026-10-14 15:50")
    rig.run("2026-10-14 15:50", "2026-10-14 15:56")
    lots = rig.journal.get(GOTOBI)["volume"]
    margin = lots * 100_000 / 5 / 1.17
    assert lots < 0.31 and margin <= 0.9 * 1000 + 1e-6


def test_restart_during_monday_wait_keeps_the_reopen_time(tmp_path):
    bars = make_bars("2026-10-01 00:00", "2026-10-05 12:00")
    rig = Rig(bars, tmp_path, start="2026-10-04 15:00")
    rig.run("2026-10-04 15:00", "2026-10-04 21:10")
    rig.start("2026-10-04 21:11")                                        # restart after the reopen
    rig.run("2026-10-04 21:11", "2026-10-05 01:00")
    assert rig.journal.get("2026-10-05")["opened"] == "2026-10-04T21:20:00+00:00"


def test_brief_pause_after_reopen_does_not_restart_the_wait(tmp_path):
    bars = make_bars("2026-10-01 00:00", "2026-10-05 12:00", gaps=[("2026-10-04 21:10", "2026-10-04 21:14")])
    rig = Rig(bars, tmp_path, start="2026-10-04 15:00")
    rig.run("2026-10-04 15:00", "2026-10-05 01:00")
    assert rig.journal.get("2026-10-05")["opened"] == "2026-10-04T21:20:00+00:00"


def test_bot_started_after_the_reopen_waits_15_minutes_from_its_start(tmp_path):
    bars = make_bars("2026-10-01 00:00", "2026-10-05 12:00")
    rig = Rig(bars, tmp_path, start="2026-10-04 23:00")
    rig.run("2026-10-04 23:00", "2026-10-05 01:00")
    assert rig.journal.get("2026-10-05")["opened"] == "2026-10-04T23:15:00+00:00"


def test_weekday_feed_outage_waits_15_minutes_after_prices_return(week, tmp_path):
    week.drop(week.index[(week.index >= "2026-10-14 15:30") & (week.index < "2026-10-14 16:30")], inplace=True)
    rig = Rig(week, tmp_path, start="2026-10-14 15:00")
    rig.run("2026-10-14 15:00", "2026-10-14 17:00")
    assert rig.journal.get(GOTOBI)["opened"] == "2026-10-14T16:45:00+00:00"


def test_short_weekday_gap_is_not_a_closure(week, tmp_path):
    week.drop(week.index[(week.index >= "2026-10-14 15:50") & (week.index < "2026-10-14 16:10")], inplace=True)
    rig = Rig(week, tmp_path, start="2026-10-14 15:00")
    rig.run("2026-10-14 15:00", "2026-10-14 17:00")
    assert rig.journal.get(GOTOBI)["opened"] == "2026-10-14T16:10:00+00:00"


def test_stopped_out_day_is_not_bought_again_after_the_journal_is_lost(week, tmp_path):
    import shutil
    dip(week, "2026-10-14 18:00", 149.40)
    rig = Rig(week, tmp_path / "state", start="2026-10-14 15:50")
    rig.run("2026-10-14 15:50", "2026-10-14 18:10")                      # bought, then stopped out at 18:00
    shutil.rmtree(tmp_path / "state")                                     # state file lost / deleted
    rig.start("2026-10-14 18:30")
    rig.run("2026-10-14 18:30", "2026-10-15 01:00")
    assert len(rig.opens()) == 1                                         # the broker history blocked a 2nd buy
    rec = rig.journal.get(GOTOBI)
    assert rec["recovered"] and rec["status"] == "closed" and rec["reason"] == "stop"


def test_journal_survives_a_reload(week, tmp_path):
    from bot.journal import Journal
    rig = Rig(week, tmp_path, start="2026-10-14 15:50")
    rig.run("2026-10-14 15:50", "2026-10-15 01:00")
    again = Journal(tmp_path)
    assert again.get(GOTOBI) == rig.journal.get(GOTOBI) and again.get(GOTOBI)["status"] == "closed"
    assert again.peak_balance == rig.journal.peak_balance


def test_never_opens_with_less_than_the_minimum_hold_left(week, tmp_path):
    rig = Rig(week, tmp_path, cfg=replace(TEST_CFG, max_entry_delay_min=600), start="2026-10-15 00:30")
    rig.run("2026-10-15 00:30", "2026-10-15 01:00")
    rec = rig.journal.get(GOTOBI)
    assert rec["status"] == "missed" and rec["note"] == "too close to the exit" and rig.opens() == []


def test_long_weekday_outage_past_the_delay_limit_is_missed(week, tmp_path):
    week.drop(week.index[(week.index >= "2026-10-14 15:30") & (week.index < "2026-10-14 18:30")], inplace=True)
    rig = Rig(week, tmp_path, start="2026-10-14 15:00")
    rig.run("2026-10-14 15:00", "2026-10-14 20:00")
    assert rig.journal.get(GOTOBI)["status"] == "missed" and rig.opens() == []


def test_monday_reopen_too_close_to_the_exit_is_missed(tmp_path):
    bars = make_bars("2026-10-01 00:00", "2026-10-05 12:00", gaps=[("2026-10-04 21:00", "2026-10-05 00:35")])
    rig = Rig(bars, tmp_path, start="2026-10-04 15:00")
    rig.run("2026-10-04 15:00", "2026-10-05 01:00")
    assert rig.journal.get("2026-10-05")["status"] == "missed" and rig.opens() == []


def _preflight(rig, when, inspect_only=True):
    from bot.broker import MT5Broker
    from bot.engine import Engine
    from bot.journal import Journal
    now = utc(when)
    rig.fake.set_time(now)
    eng = Engine(rig.cfg, MT5Broker(rig.fake), Journal(rig.state_dir, durable=False))
    eng.startup(now, inspect_only=inspect_only)
    return eng.preflight(now)


def test_preflight_ready_on_a_healthy_demo(week, tmp_path):
    rig = Rig(week, tmp_path)
    ready, lines = _preflight(rig, "2026-10-14 12:00")
    text = "\n".join(lines)
    assert ready and lines[-1].startswith("READY") and "DEMO" in text and "accepted" in text
    assert "0.31 lots" in text and "UTC+0 h" in text and rig.fake.requests == []      # nothing was sent


def test_preflight_names_each_problem(week, tmp_path):
    rig = Rig(week, tmp_path, trade_mode=2)
    rig.fake.algo_trading = False
    rig.fake.tradeapi_disabled = True
    ready, lines = _preflight(rig, "2026-10-14 12:00")
    text = "\n".join(lines)
    assert not ready and lines[-1].startswith("NOT READY")
    assert "REAL MONEY" in text and "Algo Trading button is OFF" in text and "Python API trading is DISABLED" in text
    assert rig.fake.requests == []


def test_preflight_on_a_weekend_and_with_a_utc_plus_3_broker(tmp_path):
    bars = make_bars("2026-10-01 00:00", "2026-10-05 12:00")
    ready, lines = _preflight(Rig(bars, tmp_path / "w"), "2026-10-03 12:00")             # Saturday
    assert ready and any("market is shut" in x for x in lines)
    ready, lines = _preflight(Rig(bars, tmp_path / "o", server_offset_h=3.0), "2026-10-02 12:00")
    assert ready and any("UTC+3 h" in x for x in lines)
