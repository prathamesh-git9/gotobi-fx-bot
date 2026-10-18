"""Independent second-review checks against the current implementation."""
from __future__ import annotations

from types import SimpleNamespace
from datetime import timedelta
from pathlib import Path

import pytest

from bot.broker import BrokerUnavailable, MT5Broker
from bot.clock import Clock
from bot.engine import Engine
from bot.fake_mt5 import FakeMT5
from bot.journal import Journal
from bot.sizing import size_position
from test_adversarial import at, bars, cfg


def rig(tmp_path, start="2026-10-14 15:50", end="2026-10-15 01:30"):
    fake = FakeMT5(bars(start, end), 1.17, slip_bp=0)
    fake.set_time(at(start))
    journal = Journal(tmp_path)
    engine = Engine(cfg(tmp_path), MT5Broker(fake), journal)
    engine.startup(at(start))
    return fake, engine, journal


def entries(fake):
    return [d for d in fake.deal_log if d.entry == fake.DEAL_ENTRY_IN and d.magic == 950955]


def test_real_account_switch_blocks_order(tmp_path):
    fake, engine, journal = rig(tmp_path)
    fake.trade_mode = fake.ACCOUNT_TRADE_MODE_REAL
    fake.set_time(at("2026-10-14 15:55"))
    engine.step(at("2026-10-14 15:55"))
    assert not entries(fake) and journal.get("2026-10-15") is None


def test_other_account_pauses_and_resumes_overdue_exit(tmp_path):
    fake, engine, journal = rig(tmp_path)
    fake.set_time(at("2026-10-14 15:55"))
    engine.step(at("2026-10-14 15:55"))
    original = fake.account_info
    fake.account_info = lambda: SimpleNamespace(**{**vars(original()), "login": 999})
    fake.set_time(at("2026-10-15 00:55"))
    engine.step(at("2026-10-15 00:55"))
    assert fake.positions and journal.get("2026-10-15")["status"] == "open"
    fake.account_info = original
    fake.set_time(at("2026-10-15 00:56"))
    engine.step(at("2026-10-15 00:56"))
    assert not fake.positions


def test_foreign_position_blocks_entry(tmp_path):
    fake, engine, _ = rig(tmp_path)
    fake.set_time(at("2026-10-14 15:54"))
    r = fake.order_send({"action": fake.TRADE_ACTION_DEAL, "symbol": fake.name, "volume": 0.01,
                         "type": fake.ORDER_TYPE_SELL, "price": 150, "magic": 0,
                         "type_time": fake.ORDER_TIME_GTC, "type_filling": fake.ORDER_FILLING_IOC})
    assert r.retcode == fake.TRADE_RETCODE_DONE
    fake.set_time(at("2026-10-14 15:55"))
    engine.step(at("2026-10-14 15:55"))
    assert not entries(fake) and len(fake.positions) == 1


def test_lost_fill_then_stop_does_not_duplicate(tmp_path):
    fake, engine, journal = rig(tmp_path)
    i = list(fake.t).index(int(at("2026-10-14 15:56").timestamp() // 60))
    fake.bl = fake.bl.copy()
    fake.bl[i] = 149.0
    send, first = fake.order_send, [True]

    def lost(req):
        result = send(req)
        if first[0] and not req.get("position"):
            first[0] = False
            return None
        return result

    fake.order_send = lost
    fake.set_time(at("2026-10-14 15:55"))
    engine.step(at("2026-10-14 15:55"))
    fake.set_time(at("2026-10-14 15:57"))
    engine.step(at("2026-10-14 15:57"))
    assert len(entries(fake)) == 1 and journal.get("2026-10-15")["status"] == "closed"


def test_placed_order_can_be_resent_while_still_pending(tmp_path):
    fake, engine, _ = rig(tmp_path)
    fake.leverage = 500
    send, pending, sends = fake.order_send, [], []

    def queued_then_fill(req):
        if req.get("position"):
            return send(req)
        sends.append(dict(req))
        if len(sends) == 1:
            pending.append(dict(req))
            return SimpleNamespace(retcode=fake.TRADE_RETCODE_PLACED, deal=0, order=4242,
                                   volume=0.0, price=0.0, comment="placed")
        result = send(req)
        send(pending.pop())  # the broker executes the earlier queued order too
        return result

    fake.order_send = queued_then_fill
    fake.set_time(at("2026-10-14 15:55"))
    engine.step(at("2026-10-14 15:55"))
    assert not entries(fake) and pending
    fake.set_time(at("2026-10-14 15:55:03"))
    engine.step(at("2026-10-14 15:55:03"))
    assert len(entries(fake)) == 2 and len(fake.positions) == 2


def test_fill_then_position_read_error_and_stop_can_duplicate(tmp_path):
    fake, engine, journal = rig(tmp_path)
    i = list(fake.t).index(int(at("2026-10-14 15:56").timestamp() // 60))
    fake.bl = fake.bl.copy()
    fake.bl[i] = 149.0
    send = fake.order_send
    first = [True]

    def fill_then_read_failure(req):
        result = send(req)
        if first[0] and not req.get("position") and result.retcode == fake.TRADE_RETCODE_DONE:
            first[0] = False
            fake.positions_fail = 1  # _find_ticket cannot read the newly filled position
        return result

    fake.order_send = fill_then_read_failure
    fake.set_time(at("2026-10-14 15:55"))
    with pytest.raises(BrokerUnavailable):
        engine.step(at("2026-10-14 15:55"))
    assert len(entries(fake)) == 1 and journal.get("2026-10-15") is None
    fake.set_time(at("2026-10-14 15:57"))
    engine.step(at("2026-10-14 15:57"))
    assert len(entries(fake)) == 2


def test_short_busy_before_deadline_is_skipped(tmp_path):
    fake, engine, journal = rig(tmp_path, start="2026-10-15 00:54:50")
    clock = [at("2026-10-15 00:54:59")]
    engine.now_fn = lambda: clock[0]
    info = fake.symbol_info

    def delayed(symbol):
        clock[0] = at("2026-10-15 00:55:06")
        return info(symbol)

    fake.symbol_info = delayed
    fake.set_time(at("2026-10-15 00:54:59"))
    engine.step(at("2026-10-15 00:54:59"))
    assert not entries(fake) and journal.get("2026-10-15/short")["status"] == "missed"


def test_short_can_still_fill_late_when_order_send_blocks(tmp_path):
    fake, engine, journal = rig(tmp_path, start="2026-10-15 00:54:50")
    clock = [at("2026-10-15 00:54:59")]
    engine.now_fn = lambda: clock[0]
    send = fake.order_send

    def delayed(req):
        if not req.get("position"):
            clock[0] = at("2026-10-15 00:55:10")
            fake.set_time(clock[0])
        return send(req)

    fake.order_send = delayed
    fake.set_time(clock[0])
    engine.step(clock[0])
    rec = journal.get("2026-10-15/short")
    assert rec["status"] == "open" and rec["sent_vs_fix_sec"] == -1
    assert rec["answered_vs_fix_sec"] == 10
    assert entries(fake)[0].time == int(clock[0].timestamp())


def test_unverified_clock_rejects_false_broker_offset(tmp_path):
    fake, engine, _ = rig(tmp_path, start="2026-10-14 14:50", end="2026-10-14 15:05")
    engine.clock_ok = lambda: False
    fake.set_time(at("2026-10-14 14:55"))
    engine.step(at("2026-10-14 15:55"))  # PC is one hour ahead
    assert engine.offset_h == 0 and not entries(fake)


def test_blocked_time_servers_allow_short_a_minute_early(tmp_path):
    market = bars("2026-10-15 00:53:50", "2026-10-15 01:30")
    fake = FakeMT5(market, 1.17, slip_bp=0)
    physical = at("2026-10-15 00:53:50")
    fake.set_time(physical)
    journal = Journal(tmp_path)
    engine = Engine(cfg(tmp_path), MT5Broker(fake), journal)
    engine.clock_ok = lambda: False
    engine.now_fn = lambda: fake.now + timedelta(seconds=60)
    engine.startup(engine.now_fn())
    fake.set_time(at("2026-10-15 00:53:59"))
    engine.step(engine.now_fn())
    assert entries(fake) and entries(fake)[0].time == int(at("2026-10-15 00:53:59").timestamp())
    assert journal.get("2026-10-15/short")["sent_vs_fix_sec"] == -1


def test_blocked_time_servers_with_correct_utc_zero_clock_can_trade(tmp_path):
    fake, engine, _ = rig(tmp_path)
    engine.clock_ok = lambda: False
    fake.set_time(at("2026-10-14 15:55"))
    engine.step(at("2026-10-14 15:55"))
    assert len(entries(fake)) == 1


def test_clock_jump_follows_wall_and_verification_expires():
    wall, mono = [1000.0], [0.0]
    c = Clock(("a", "b"), query=lambda _: (20.0, 0.01), wall=lambda: wall[0], mono=lambda: mono[0])
    assert c.refresh() and c.verified()
    wall[0] += 25
    mono[0] += 5
    assert c.now().timestamp() == pytest.approx(1025)
    mono[0] += 13 * 3600
    assert not c.verified()


def test_drawdown_while_flat_blocks_entry(tmp_path):
    fake, engine, journal = rig(tmp_path)
    fake.balance = 500
    fake.set_time(at("2026-10-14 15:55"))
    engine.step(at("2026-10-14 15:55"))
    assert not entries(fake) and journal.halted


def test_corrupt_state_recovers_from_backup(tmp_path):
    j = Journal(tmp_path)
    j.update("2026-10-15", status="open", ticket=42, exit_due=at("2026-10-15 00:54").isoformat())
    Journal(tmp_path)  # take startup backup
    (tmp_path / "state.json").write_text('{"slots":', encoding="utf-8")
    recovered = Journal(tmp_path)
    assert recovered.recovered_from == "backup" and recovered.get("2026-10-15")["ticket"] == 42
    assert list(tmp_path.glob("state.corrupt-*.json"))


def test_corrupt_recovery_can_lose_kill_switch(tmp_path):
    j = Journal(tmp_path)
    j.set_peak(1000)
    Journal(tmp_path)  # backup predates the halt
    j.halt("last 60 long trades lost 7R", at("2026-10-14 15:50"))
    (tmp_path / "state.json").write_text('{"slots":', encoding="utf-8")
    recovered = Journal(tmp_path)
    assert recovered.recovered_from == "backup" and recovered.halted is None
    fake = FakeMT5(bars("2026-10-14 15:50", "2026-10-15 01:30"), 1.17, slip_bp=0)
    fake.set_time(at("2026-10-14 15:50"))
    engine = Engine(cfg(tmp_path), MT5Broker(fake), recovered)
    engine.startup(at("2026-10-14 15:50"))
    fake.set_time(at("2026-10-14 15:55"))
    engine.step(at("2026-10-14 15:55"))
    assert len(entries(fake)) == 1


def test_malformed_but_valid_json_crashes_journal_startup(tmp_path):
    (tmp_path / "state.json").write_text('{"slots": []}', encoding="utf-8")
    with pytest.raises(AttributeError):
        Journal(tmp_path)


def test_history_error_eventually_erases_closed_trade_performance(tmp_path):
    fake, engine, journal = rig(tmp_path)
    fake.set_time(at("2026-10-14 15:55"))
    engine.step(at("2026-10-14 15:55"))
    i = list(fake.t).index(int(at("2026-10-14 15:56").timestamp() // 60))
    fake.bl = fake.bl.copy()
    fake.bl[i] = 149.0
    fake.set_time(at("2026-10-14 16:00"))
    assert not fake.positions

    def no_history(*_a, **_kw):
        fake.error = (-10004, "No IPC connection")
        return None

    fake.history_deals_get = no_history
    for n in range(131):
        fake.set_time(at("2026-10-14 16:00") + timedelta(seconds=n))
        engine.step(fake.now)
    rec = journal.get("2026-10-15")
    assert rec["status"] == "closed" and rec["reason"] == "unknown" and rec["r"] is None


def test_partial_fill_is_still_classified_as_complete(tmp_path):
    fake, engine, _ = rig(tmp_path)
    fake.order_send = lambda req: SimpleNamespace(retcode=fake.TRADE_RETCODE_DONE_PARTIAL, price=req["price"],
                                                  volume=req["volume"] / 2, order=42, deal=43, comment="partial")
    result = engine.broker.market_order(fake.name, +1, 0.1)
    assert result.ok and result.category == "done" and result.volume == 0.05


def test_entry_request_uses_new_quote_with_old_stop_and_size(tmp_path):
    fake, engine, _ = rig(tmp_path)
    tick_fn, calls = fake.symbol_info_tick, [0]

    def moving_quote(symbol):
        tick = tick_fn(symbol)
        calls[0] += 1
        if calls[0] >= 2:
            return SimpleNamespace(**{**vars(tick), "ask": tick.ask + 0.1, "bid": tick.bid + 0.1})
        return tick

    fake.symbol_info_tick = moving_quote
    fake.set_time(at("2026-10-14 15:55"))
    engine.step(at("2026-10-14 15:55"))
    req = next(r for r in fake.requests if not r.get("position"))
    assert (req["price"] - req["sl"]) / engine.pip == pytest.approx(65, abs=0.01)


def test_journal_slots_still_grow_without_bound(tmp_path):
    journal = Journal(tmp_path, durable=False)
    for n in range(80):
        journal.update(f"old-{n}", status="closed", pnl=0.0)
    assert len(Journal(tmp_path, durable=False).slots) == 80


def test_preflight_real_account_without_both_keys_not_ready(tmp_path):
    fake, engine, _ = rig(tmp_path)
    fake.trade_mode = fake.ACCOUNT_TRADE_MODE_REAL
    ready, lines = engine.preflight(at("2026-10-14 15:50"))
    assert not ready and any("real-money account" in line and line.startswith("[!!]") for line in lines)


def test_preflight_says_ready_with_unverified_clock_one_minute_ahead(tmp_path):
    fake = FakeMT5(bars("2026-10-15 00:53:50", "2026-10-15 01:30"), 1.17, slip_bp=0)
    fake.set_time(at("2026-10-15 00:53:59"))
    engine = Engine(cfg(tmp_path), MT5Broker(fake), Journal(tmp_path))
    engine.clock_note = "PC clock not checked against time servers (using it as it is)"
    engine.clock_ok = lambda: False
    wall = at("2026-10-15 00:54:59")
    engine.startup(wall, inspect_only=True)
    ready, report = engine.preflight(wall)
    assert ready and report[-1].startswith("READY")


def test_windows_launcher_has_stop_codes_and_logon_task_settings():
    root = Path(__file__).resolve().parents[2]
    bat = (root / "run_bot.bat").read_text(encoding="utf-8")
    task = (root / "install_autostart.ps1").read_text(encoding="utf-8")
    assert "if %ERRORLEVEL%==0 goto end" in bat
    assert "if %ERRORLEVEL%==2 goto end" in bat
    assert "New-ScheduledTaskTrigger -AtLogOn" in task
    assert "-ExecutionTimeLimit ([TimeSpan]::Zero)" in task
    assert "-LogonType Interactive" in task
    assert "Register-ScheduledTask" in task


def test_per_account_lock_excludes_second_instance(tmp_path, monkeypatch):
    from bot.main import SingleInstance, account_lock_path
    import bot.main as main

    monkeypatch.setattr(main.tempfile, "gettempdir", lambda: str(tmp_path))
    path = account_lock_path(123, "Demo-Server")
    first = SingleInstance(path)
    try:
        with pytest.raises(SystemExit, match="another copy"):
            SingleInstance(path)
    finally:
        first.f.close()


def test_min_lot_override_still_exceeds_risk():
    r = size_position(1.0, 150.0, 0.01, 100.0, 0.01, None, 1000.0, below_min="min")
    assert r.lots == 0.01 and r.risk_at_size == 1.5
