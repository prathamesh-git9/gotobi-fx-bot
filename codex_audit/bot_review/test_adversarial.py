"""Independent characterization and entry-point soak checks; no live terminal needed."""
from __future__ import annotations

import gc
import json
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import MetaTrader5 as real_mt5
import numpy as np
import pandas as pd
import pytest

from bot import main as entry
from bot.broker import MT5Broker
from bot.broker import BrokerUnavailable
from bot.clock import Clock
from bot.config import Config
from bot.engine import Engine
from bot.fake_mt5 import FakeMT5
from bot.journal import Journal
from bot.sizing import size_position

UTC = timezone.utc


def at(s):
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


def bars(start, end):
    idx = pd.date_range(start, end, freq="1min")
    wd, mins = idx.weekday, idx.hour * 60 + idx.minute
    idx = idx[(wd < 5) & ~((wd == 4) & (mins >= 21 * 60)) | ((wd == 6) & (mins >= 21 * 60 + 5))]
    bid = np.full(len(idx), 150.0)
    ask = bid + 0.01
    return pd.DataFrame({c: bid.copy() for c in ("bopen", "bhigh", "blow", "bclose")}
                        | {c: ask.copy() for c in ("aopen", "ahigh", "alow", "aclose")}, index=idx)


def cfg(path, **kwargs):
    values = dict(symbols=("USDJPYm",), state_dir=str(path), risk_pct=6, poll_sec=60, clock_sync=False)
    values.update(kwargs)
    return replace(Config(), **values)


class SimTime:
    def __init__(self, fake, start, end, restart=None, hook=None):
        self.fake, self.now, self.end, self.restart, self.hook = fake, start, end, restart, hook
        self.sleeps = []
        self.loops = 0
        fake.set_time(start)

    def utcnow(self):
        self.loops += 1
        return self.now

    def sleep(self, seconds):
        assert isinstance(seconds, (float, int)) and np.isfinite(seconds)
        assert 0 < seconds <= 60, f"insane sleep {seconds!r} at {self.now}"
        self.sleeps.append(seconds)
        self.now += timedelta(seconds=seconds)
        self.fake.set_time(self.now)
        if self.hook:
            self.hook(self)
        if self.restart and self.now >= self.restart:
            self.restart = None
            raise KeyboardInterrupt
        if self.now >= self.end:
            raise KeyboardInterrupt


def run_main(monkeypatch, sim, settings, fake, clock_factory=None):
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake)
    monkeypatch.setattr(entry, "load_config", lambda _: settings)
    monkeypatch.setattr(entry, "setup_logging", lambda _: None)
    monkeypatch.setattr(entry, "SingleInstance", lambda _: None)
    monkeypatch.setattr(entry, "keep_awake", lambda: None)
    monkeypatch.setattr(entry, "utcnow", sim.utcnow)
    if clock_factory is not None:
        monkeypatch.setattr(entry, "Clock", clock_factory)
    elif settings.clock_sync:
        class FailingTimeServers:
            def __init__(self, _servers):
                self.refresh_count = 0

            def refresh(self):
                self.refresh_count += 1
                return False

            def maybe_refresh(self):
                return self.refresh()

            def now(self):
                return sim.utcnow()

            def describe(self):
                return "time servers unavailable; PC clock used"

        monkeypatch.setattr(entry, "Clock", FailingTimeServers)
    monkeypatch.setattr(entry.time, "sleep", sim.sleep)
    return entry.main([])


def test_main_four_month_soak_with_faults_and_restart(monkeypatch, tmp_path):
    """Run the actual entry point through four months of schedules and injected outages."""
    start, end = at("2026-01-04 20:00"), at("2026-05-01 03:00")
    market = bars("2026-01-04 20:00", "2026-05-01 03:00")
    fake = FakeMT5(market, 1.17, balance=1000, leverage=30, slip_bp=0)
    settings = cfg(tmp_path, clock_sync=True)
    fired = set()
    allocated = []
    checkpoints = iter([at("2026-02-01 00:00"), at("2026-03-01 00:00"),
                        at("2026-04-01 00:00"), at("2026-05-01 00:00")])
    next_checkpoint = [next(checkpoints)]

    def inject(sim):
        n = sim.now
        assert len(fake.positions) <= 1
        if next_checkpoint[0] is not None and n >= next_checkpoint[0]:
            gc.collect()
            allocated.append(sys.getallocatedblocks())
            next_checkpoint[0] = next(checkpoints, None)
        for key, moment, fault in (
            ("positions", at("2026-02-09 15:55"), "positions"),
            ("requote", at("2026-03-04 15:55"), "requote"),
            ("exception", at("2026-04-09 15:55"), "exception"),
            ("rejection", at("2026-04-14 15:55"), "rejection"),
            ("disconnect", at("2026-03-19 15:55"), "disconnect"),
        ):
            if key not in fired and n >= moment:
                fired.add(key)
                if fault == "positions":
                    fake.positions_fail = 1
                elif fault == "requote":
                    fake.fail_next("open", fake.TRADE_RETCODE_REQUOTE)
                else:
                    if fault == "exception":
                        exception_due.add("account")
                    elif fault == "rejection":
                        fake.fail_next("open", fake.TRADE_RETCODE_INVALID_STOPS)
                    elif fault == "disconnect":
                        fake.connected = False
        if "disconnect" in fired and n >= at("2026-03-19 15:57"):
            fake.connected = True

    exception_due = set()
    original_account = fake.account_info

    def account_with_fault():
        if "account" in exception_due:
            exception_due.clear()
            raise RuntimeError("injected unexpected terminal exception")
        return original_account()

    fake.account_info = account_with_fault
    sim = SimTime(fake, start, end, restart=at("2026-02-10 00:00"), hook=inject)
    assert run_main(monkeypatch, sim, settings, fake) == 0
    assert fake.positions, "restart was meant to occur during an open trade"
    assert run_main(monkeypatch, sim, settings, fake) == 0
    state = Journal(tmp_path)
    assert {"positions", "requote", "exception", "rejection", "disconnect"} <= fired
    assert sim.loops > 100_000
    assert not fake.positions
    assert not state.open_slots()
    assert all(rec.get("exit_late_sec", 0) <= 60 for rec in state.slots.values()
               if rec.get("status") == "closed")
    opens = [d for d in fake.deal_log if d.entry == fake.DEAL_ENTRY_IN]
    assert len(opens) >= 30
    assert len({(d.comment, d.type) for d in opens}) == len(opens), "duplicate entry"
    assert all(d.position_id in {x.position_id for x in fake.deal_log if x.entry == fake.DEAL_ENTRY_OUT}
               for d in opens), "stranded position"
    gc.collect()
    assert len(state.slots) < 60
    assert len(allocated) == 4 and allocated[-1] - allocated[0] < 100_000

    clean_fake = FakeMT5(market, 1.17, balance=1000, leverage=30, slip_bp=0)
    clean_sim = SimTime(clean_fake, start, end)
    assert run_main(monkeypatch, clean_sim, cfg(tmp_path / "clean"), clean_fake) == 0
    affected = {"2026-02-10", "2026-03-05", "2026-03-20", "2026-04-10", "2026-04-15"}

    def signature(f):
        return [(d.comment, d.type, d.time) for d in f.deal_log if d.entry == f.DEAL_ENTRY_IN
                and not any(day in d.comment for day in affected)]

    assert signature(fake) == signature(clean_fake)


def test_demo_to_real_account_switch_is_not_rechecked(tmp_path):
    fake = FakeMT5(bars("2026-10-14 15:50", "2026-10-15 01:30"), 1.17, slip_bp=0)
    settings = cfg(tmp_path)
    fake.set_time(at("2026-10-14 15:50"))
    engine = Engine(settings, MT5Broker(fake), Journal(tmp_path))
    engine.startup(at("2026-10-14 15:50"))
    fake.trade_mode = fake.ACCOUNT_TRADE_MODE_REAL
    fake.set_time(at("2026-10-14 15:55"))
    engine.step(at("2026-10-14 15:55"))
    assert fake.positions, "characterization: a trade is opened after switching to real money"


def test_broker_ignores_foreign_position_and_can_hedge(tmp_path):
    fake = FakeMT5(bars("2026-10-14 15:50", "2026-10-15 01:30"), 1.17, slip_bp=0)
    settings = cfg(tmp_path)
    fake.set_time(at("2026-10-14 15:50"))
    engine = Engine(settings, MT5Broker(fake), Journal(tmp_path))
    engine.startup(at("2026-10-14 15:50"))
    fake.set_time(at("2026-10-14 15:54"))
    manual = fake.order_send({"action": fake.TRADE_ACTION_DEAL, "symbol": fake.name, "volume": 0.01,
                              "type": fake.ORDER_TYPE_SELL, "price": 150., "magic": 0,
                              "type_time": fake.ORDER_TIME_GTC, "type_filling": fake.ORDER_FILLING_IOC})
    assert manual.retcode == fake.TRADE_RETCODE_DONE
    fake.set_time(at("2026-10-14 15:55"))
    engine.step(at("2026-10-14 15:55"))
    assert {p.type for p in fake.positions.values()} == {fake.POSITION_TYPE_BUY, fake.POSITION_TYPE_SELL}


def test_min_lot_setting_can_exceed_risk():
    result = size_position(1.0, 150.0, 0.01, 100.0, 0.01, None, 1000.0, below_min="min")
    assert result.lots == 0.01 and result.risk_at_size == 1.5


def test_clock_failure_retains_stale_correction():
    wall = [1_000_000.0]
    answers = [(20.0, 0.01), (20.1, 0.01)]
    def query(_):
        if answers:
            return answers.pop(0)
        raise OSError("time service down")
    clock = Clock(("a", "b"), query=query, wall=lambda: wall[0])
    assert clock.refresh()
    wall[0] += 3600
    assert not clock.refresh()
    assert clock.offset == pytest.approx(20.05)
    assert clock.measured_at == 1_000_000.0


def test_ambiguous_fill_then_stop_can_duplicate_in_same_window(tmp_path):
    market = bars("2026-10-14 15:50", "2026-10-15 01:30")
    market.loc[pd.Timestamp("2026-10-14 15:56"), "blow"] = 149.0
    fake = FakeMT5(market, 1.17, slip_bp=0)
    fake.set_time(at("2026-10-14 15:50"))
    engine = Engine(cfg(tmp_path), MT5Broker(fake), Journal(tmp_path))
    engine.startup(at("2026-10-14 15:50"))
    original_send = fake.order_send
    first = [True]

    def acknowledged_lost(req):
        result = original_send(req)
        if first[0] and not req.get("position"):
            first[0] = False
            return None  # broker filled it, IPC response was lost
        return result

    fake.order_send = acknowledged_lost
    fake.set_time(at("2026-10-14 15:55"))
    engine.step(at("2026-10-14 15:55"))
    assert len([d for d in fake.deal_log if d.entry == fake.DEAL_ENTRY_IN]) == 1
    fake.set_time(at("2026-10-14 15:57"))  # first fill has now stopped out
    engine.step(at("2026-10-14 15:57"))
    assert len([d for d in fake.deal_log if d.entry == fake.DEAL_ENTRY_IN]) == 2


def test_short_order_can_be_sent_after_deadline_while_logged_on_time(tmp_path):
    fake = FakeMT5(bars("2026-10-14 15:50", "2026-10-15 01:30"), 1.17, slip_bp=0)
    fake.set_time(at("2026-10-15 00:54:58"))
    engine = Engine(cfg(tmp_path), MT5Broker(fake), Journal(tmp_path))
    engine.startup(at("2026-10-15 00:54:58"))
    original_send = fake.order_send

    def delayed_send(req):
        if req.get("type") == fake.ORDER_TYPE_SELL and not req.get("position"):
            fake.set_time(at("2026-10-15 00:55:10"))
        return original_send(req)

    fake.order_send = delayed_send
    engine.step(at("2026-10-15 00:54:59"))
    short = engine.journal.get("2026-10-15/short")
    assert short["status"] == "open"
    assert short["sent_vs_fix_sec"] == -1
    assert fake.deal_log[-1].time == int(at("2026-10-15 00:55:10").timestamp())


def test_main_clock_server_failure_with_pc_one_hour_ahead_trades_early(monkeypatch, tmp_path):
    fake = FakeMT5(bars("2026-10-14 14:45", "2026-10-14 15:05"), 1.17, slip_bp=0)
    sim = SimTime(fake, at("2026-10-14 14:50"), at("2026-10-14 15:00"))

    def no_time_server(_host):
        raise OSError("UDP 123 unavailable")

    def clock_factory(servers):
        return Clock(servers, query=no_time_server, wall=lambda: sim.now.timestamp() + 3600)

    assert run_main(monkeypatch, sim, cfg(tmp_path, clock_sync=True), fake, clock_factory) == 0
    entries = [d for d in fake.deal_log if d.entry == fake.DEAL_ENTRY_IN]
    assert len(entries) == 1
    assert datetime.fromtimestamp(entries[0].time, UTC) < at("2026-10-14 15:00")


def test_drawdown_is_not_checked_while_flat(tmp_path):
    fake = FakeMT5(bars("2026-10-14 15:50", "2026-10-15 01:30"), 1.17, slip_bp=0)
    fake.set_time(at("2026-10-14 15:50"))
    engine = Engine(cfg(tmp_path), MT5Broker(fake), Journal(tmp_path))
    engine.startup(at("2026-10-14 15:50"))
    fake.balance = 400.0  # a withdrawal or another strategy halved the account while flat
    fake.set_time(at("2026-10-14 15:55"))
    engine.step(at("2026-10-14 15:55"))
    assert fake.positions and not engine.journal.halted


def test_corrupt_state_aborts_main_before_watchdog_loop(monkeypatch, tmp_path):
    (tmp_path / "state.json").write_text('{"slots":', encoding="utf-8")
    fake = FakeMT5(bars("2026-10-14 15:50", "2026-10-14 16:00"), 1.17)
    sim = SimTime(fake, at("2026-10-14 15:50"), at("2026-10-14 16:00"))
    with pytest.raises(json.JSONDecodeError):
        run_main(monkeypatch, sim, cfg(tmp_path), fake)


def test_disconnect_across_exit_strands_position_until_reconnect(tmp_path):
    fake = FakeMT5(bars("2026-10-14 15:50", "2026-10-15 01:30"), 1.17, slip_bp=0)
    fake.set_time(at("2026-10-14 15:50"))
    engine = Engine(cfg(tmp_path), MT5Broker(fake), Journal(tmp_path))
    engine.startup(at("2026-10-14 15:50"))
    fake.set_time(at("2026-10-14 15:55"))
    engine.step(at("2026-10-14 15:55"))
    assert fake.positions
    fake.set_time(at("2026-10-15 00:55"))
    fake.connected = False
    with pytest.raises(BrokerUnavailable):
        engine.step(at("2026-10-15 00:55"))
    assert fake.positions  # 00:54 timed exit was missed; the 55-pip SL is still on the server
    fake.connected = True
    engine.step(at("2026-10-15 00:56"))
    assert not fake.positions


def test_installed_mt5_api_names_and_documented_call_forms():
    names = {"initialize": ("path", "login", "password", "server"),
             "positions_get": ("symbol",), "history_deals_get": ("date_from", "date_to", "position"),
             "order_calc_profit": ("action", "symbol", "volume", "price_open", "price_close"),
             "order_calc_margin": ("action", "symbol", "volume", "price"),
             "order_check": ("request",), "order_send": ("request",)}
    for name, params in names.items():
        fn = getattr(real_mt5, name)
        doc = fn.__doc__ or ""
        assert all(p in doc for p in params), (name, doc)
    for name in ("shutdown", "last_error", "terminal_info", "account_info", "symbol_info",
                 "symbol_select", "symbol_info_tick"):
        assert callable(getattr(real_mt5, name))
    for name in ("TRADE_ACTION_DEAL", "ORDER_TIME_GTC", "ORDER_TYPE_BUY", "ORDER_TYPE_SELL",
                 "ORDER_FILLING_FOK", "ORDER_FILLING_IOC", "ORDER_FILLING_RETURN",
                 "TRADE_RETCODE_DONE", "TRADE_RETCODE_PLACED", "TRADE_RETCODE_DONE_PARTIAL",
                 "TRADE_RETCODE_REQUOTE", "TRADE_RETCODE_TIMEOUT", "DEAL_ENTRY_IN",
                 "DEAL_REASON_SL", "DEAL_REASON_TP", "POSITION_TYPE_BUY", "POSITION_TYPE_SELL",
                 "ACCOUNT_TRADE_MODE_DEMO"):
        assert hasattr(real_mt5, name)
