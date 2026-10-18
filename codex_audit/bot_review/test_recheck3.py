"""Third independent checks, including inverses of old unsafe reproductions."""
from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest

from bot.broker import BrokerUnavailable, MT5Broker
from bot.engine import Engine
from bot.fake_mt5 import FakeMT5
from bot.journal import Journal
from test_adversarial import at, bars, cfg
from test_recheck import entries, rig


def test_placed_order_is_never_resent_even_after_restart(tmp_path):
    fake, engine, journal = rig(tmp_path)
    sends = []

    def placed(req):
        sends.append(dict(req))
        return SimpleNamespace(retcode=fake.TRADE_RETCODE_PLACED, deal=0, order=4242,
                               volume=0.0, price=0.0, comment="placed")

    fake.order_send = placed
    fake.set_time(at("2026-10-14 15:55"))
    engine.step(fake.now)
    assert journal.get("2026-10-15")["status"] == "unknown"
    assert journal.get("2026-10-15")["order"] == 4242
    for second in (3, 10):
        fake.set_time(at("2026-10-14 15:55") + timedelta(seconds=second))
        engine.step(fake.now)
    fresh = Engine(cfg(tmp_path), MT5Broker(fake), Journal(tmp_path))
    fresh.startup(fake.now)
    fresh.step(fake.now)
    assert len(sends) == 1 and len(entries(fake)) == 0


def test_post_fill_read_error_retains_intent_and_recovers_without_resend(tmp_path):
    fake, engine, journal = rig(tmp_path)
    send = fake.order_send
    first = [True]

    def fill_then_error(req):
        result = send(req)
        if first[0] and not req.get("position") and result.retcode == fake.TRADE_RETCODE_DONE:
            first[0] = False
            fake.positions_fail = 1
        return result

    fake.order_send = fill_then_error
    fake.set_time(at("2026-10-14 15:55"))
    with pytest.raises(BrokerUnavailable):
        engine.step(fake.now)
    assert journal.get("2026-10-15")["status"] == "sending"
    i = list(fake.t).index(int(at("2026-10-14 15:56").timestamp() // 60))
    fake.bl = fake.bl.copy()
    fake.bl[i] = 149.0
    fake.set_time(at("2026-10-14 15:57"))
    engine.step(fake.now)
    assert len(entries(fake)) == 1
    assert journal.get("2026-10-15")["status"] == "closed"


def test_pending_fill_then_stop_loses_saved_risk_from_r_rule(tmp_path):
    fake, engine, journal = rig(tmp_path)
    send = fake.order_send
    once = [True]

    def lost_reply(req):
        result = send(req)
        if once[0] and not req.get("position"):
            once[0] = False
            return None
        return result

    fake.order_send = lost_reply
    fake.set_time(at("2026-10-14 15:55"))
    engine.step(fake.now)
    saved_risk = journal.get("2026-10-15")["risk_amount"]
    assert saved_risk > 0 and journal.get("2026-10-15")["status"] == "unknown"
    i = list(fake.t).index(int(at("2026-10-14 15:56").timestamp() // 60))
    fake.bl = fake.bl.copy()
    fake.bl[i] = 149.0
    fake.set_time(at("2026-10-14 15:57"))
    engine.step(fake.now)
    rec = journal.get("2026-10-15")
    assert rec["status"] == "closed" and rec["pnl"] < 0
    assert rec["risk_amount"] is None and rec["r"] is None


def test_pending_order_is_released_at_exit_without_order_status_check(tmp_path):
    fake, engine, journal = rig(tmp_path)
    fake.leverage = 500
    send = fake.order_send
    pending = []

    def queue_long(req):
        if not req.get("position") and req["type"] == fake.ORDER_TYPE_BUY and not pending:
            pending.append(dict(req))
            return SimpleNamespace(retcode=fake.TRADE_RETCODE_PLACED, deal=0, order=4242,
                                   volume=0.0, price=0.0, comment="placed")
        return send(req)

    fake.order_send = queue_long
    fake.set_time(at("2026-10-14 15:55"))
    engine.step(fake.now)
    assert journal.get("2026-10-15")["status"] == "unknown"
    fake.set_time(at("2026-10-15 00:54"))
    engine.step(fake.now)
    assert journal.get("2026-10-15")["status"] == "missed"
    assert pending  # the simulated broker still has the original live order
    fake.set_time(at("2026-10-15 00:54:59"))
    engine.clock_ok = lambda: True
    engine.step(fake.now)
    assert any(d.type == fake.DEAL_TYPE_SELL for d in entries(fake))
    # The broker can execute the old long after the short was allowed to open.
    send(pending.pop())
    assert len(fake.positions) == 2


def test_unverified_short_is_skipped_and_preflight_not_ready(tmp_path):
    fake = FakeMT5(bars("2026-10-15 00:53:50", "2026-10-15 01:30"), 1.17, slip_bp=0)
    fake.set_time(at("2026-10-15 00:53:50"))
    engine = Engine(cfg(tmp_path), MT5Broker(fake), Journal(tmp_path))
    engine.clock_ok = lambda: False
    engine.clock_note = "PC clock not checked against time servers"
    engine.now_fn = lambda: fake.now + timedelta(seconds=60)
    engine.startup(engine.now_fn())
    ready, report = engine.preflight(engine.now_fn())
    assert not ready and report[-1].startswith("NOT READY")
    fake.set_time(at("2026-10-15 00:53:59"))
    engine.step(engine.now_fn())
    assert not entries(fake) and engine.journal.get("2026-10-15/short")["status"] == "skipped"


def test_backup_preserves_halt_and_bad_shape_is_quarantined(tmp_path):
    journal = Journal(tmp_path)
    journal.halt("test halt", at("2026-10-14 15:50"))
    (tmp_path / "state.json").write_text('{"slots": []}', encoding="utf-8")
    recovered = Journal(tmp_path)
    assert recovered.recovered_from == "backup" and recovered.halted["reason"] == "test halt"
    assert list(tmp_path.glob("state.corrupt-*.json"))


def test_history_read_errors_keep_trade_open_and_block_future_entry(tmp_path):
    fake, engine, journal = rig(tmp_path)
    fake.set_time(at("2026-10-14 15:55"))
    engine.step(fake.now)
    i = list(fake.t).index(int(at("2026-10-14 15:56").timestamp() // 60))
    fake.bl = fake.bl.copy()
    fake.bl[i] = 149.0
    fake.set_time(at("2026-10-14 16:00"))
    assert not fake.positions

    def no_history(*_args, **_kwargs):
        fake.error = (-10004, "No IPC connection")
        return None

    fake.history_deals_get = no_history
    for n in range(131):
        fake.set_time(at("2026-10-14 16:00") + timedelta(seconds=n))
        engine.step(fake.now)
    assert journal.get("2026-10-15")["status"] == "open"
    assert "2026-10-15" in engine._history_errors


def test_moved_quote_keeps_requested_stop_distance(tmp_path):
    fake, engine, _ = rig(tmp_path)
    original = fake.symbol_info_tick
    calls = [0]

    def moving(symbol):
        tick = original(symbol)
        calls[0] += 1
        return SimpleNamespace(**{**vars(tick), "ask": tick.ask + 0.1, "bid": tick.bid + 0.1}) if calls[0] >= 2 else tick

    fake.symbol_info_tick = moving
    fake.set_time(at("2026-10-14 15:55"))
    engine.step(fake.now)
    req = next(r for r in fake.requests if not r.get("position"))
    assert (req["price"] - req["sl"]) / engine.pip == pytest.approx(55, abs=0.01)


def test_malformed_nested_state_can_crash_startup_despite_schema_check(tmp_path):
    (tmp_path / "state.json").write_text('{"slots": {}, "halted": {"reason": "test"}}', encoding="utf-8")
    journal = Journal(tmp_path)
    assert journal.halted == {"reason": "test"}
    fake = FakeMT5(bars("2026-10-14 15:50", "2026-10-15 01:30"), 1.17)
    fake.set_time(at("2026-10-14 15:50"))
    engine = Engine(cfg(tmp_path), MT5Broker(fake), journal)
    with pytest.raises(KeyError, match="at"):
        engine.startup(fake.now)


def test_unverified_fast_pc_clock_can_open_long_before_five_ticks(tmp_path):
    market = bars("2026-10-14 15:53", "2026-10-15 01:30")
    fake = FakeMT5(market, 1.17, slip_bp=0)
    fake.set_time(at("2026-10-14 15:53:55"))
    engine = Engine(cfg(tmp_path), MT5Broker(fake), Journal(tmp_path))
    engine.clock_ok = lambda: False
    engine.now_fn = lambda: fake.now + timedelta(seconds=60)
    engine.startup(engine.now_fn())
    fake.set_time(at("2026-10-14 15:54:00"))
    engine.step(engine.now_fn())
    assert len(engine._lags) < 5
    assert len(entries(fake)) == 1 and entries(fake)[0].time == int(fake.now.timestamp())


def test_clear_halt_retriggers_on_unchanged_losing_r_window(tmp_path):
    fake, engine, journal = rig(tmp_path)
    for n in range(engine.cfg.kill_window):
        journal.update(f"old-{n:02d}", status="closed", side="long", r=-1.0, pnl=-1.0)
    journal.halt("R limit", at("2026-10-14 15:50"))
    journal.clear_halt()
    assert journal.halted is None
    fake.set_time(at("2026-10-14 15:55"))
    engine.step(fake.now)
    assert journal.halted is not None and not entries(fake)


def test_failed_backup_write_can_restore_old_unhalted_state(tmp_path):
    journal = Journal(tmp_path)
    journal.set_peak(1000)
    old_write = journal._write

    def fail_backup(path, payload):
        if path == journal.backup:
            raise OSError("simulated disk error")
        return old_write(path, payload)

    journal._write = fail_backup
    journal.halt("risk limit", at("2026-10-14 15:50"))
    assert journal.halted
    (tmp_path / "state.json").write_text("{broken", encoding="utf-8")
    recovered = Journal(tmp_path)
    assert recovered.recovered_from == "backup" and recovered.halted is None


def test_successful_but_incomplete_history_still_erases_r(tmp_path):
    fake, engine, journal = rig(tmp_path)
    fake.set_time(at("2026-10-14 15:55"))
    engine.step(fake.now)
    i = list(fake.t).index(int(at("2026-10-14 15:56").timestamp() // 60))
    fake.bl = fake.bl.copy()
    fake.bl[i] = 149.0
    fake.set_time(at("2026-10-14 16:00"))
    assert not fake.positions
    read = fake.history_deals_get

    def entry_only(*args, **kwargs):
        result = read(*args, **kwargs)
        return tuple(d for d in result if d.entry == fake.DEAL_ENTRY_IN)

    fake.history_deals_get = entry_only
    for n in range(12):
        fake.set_time(at("2026-10-14 16:00") + timedelta(seconds=n))
        engine.step(fake.now)
    rec = journal.get("2026-10-15")
    assert rec["status"] == "closed" and rec["pnl"] is None and rec["r"] is None
    fake.history_deals_get = read
    engine.step(fake.now)
    assert journal.get("2026-10-15")["r"] is None


def test_verified_clock_normal_long_and_short_are_not_blocked(tmp_path):
    fake, engine, journal = rig(tmp_path)
    engine.clock_ok = lambda: True
    fake.set_time(at("2026-10-14 15:55"))
    engine.step(fake.now)
    assert len(entries(fake)) == 1
    fake.set_time(at("2026-10-15 00:54"))
    engine.step(fake.now)
    fake.set_time(at("2026-10-15 00:54:01"))
    engine.step(fake.now)
    assert journal.get("2026-10-15")["status"] == "closed"
    fake.set_time(at("2026-10-15 00:54:59"))
    engine.step(fake.now)
    assert len(entries(fake)) == 2 and journal.get("2026-10-15/short")["status"] == "open"
