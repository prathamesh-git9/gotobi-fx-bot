"""The trading engine. main.py calls step(now) every few seconds.

Every decision is made from `now` (UTC), the journal and what the broker reports, so a crash or restart at any
moment resumes correctly: an open trade is still closed on time (or at once, if the exit was missed), and a
gotobi day is never traded twice.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta

from .broker import BrokerUnavailable
from .gotobi_calendar import UTC, GotobiCalendar
from .sizing import size_position

log = logging.getLogger("gotobi.engine")
CLOSURE = timedelta(minutes=30)      # this long without a price = the market was shut (weekend, holiday, outage)


class LiveAccountRefused(RuntimeError):
    pass


class StartupError(RuntimeError):
    pass


def iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds")


class Engine:
    def __init__(self, cfg, broker, journal, dry_run: bool = False, allow_live_flag: bool = False):
        self.cfg, self.broker, self.journal = cfg, broker, journal
        self.dry_run = dry_run
        self.allow_live_flag = allow_live_flag
        self.cal = GotobiCalendar.from_config(cfg)
        self.symbol: str | None = None
        self.pip = self.digits = None
        self.fresh_since: datetime | None = None
        self.reopen_at = datetime.fromisoformat(journal.reopen_at) if journal.reopen_at else None
        self._last_tick: datetime | None = None
        self.offset_h = cfg.server_utc_offset_hours
        self._prev_raw: float | None = None
        self._prev_poll: datetime | None = None
        self._said: set[str] = set()
        self._finalize_tries: dict[str, int] = {}
        self._history_checked: set[str] = set()

    def say(self, key: str, level: int, msg: str, *args) -> None:
        """Log a message once per key (waiting states repeat every poll)."""
        if key not in self._said:
            self._said.add(key)
            log.log(level, msg, *args)

    def tick_time(self, tick) -> datetime:
        return datetime.fromtimestamp(tick.time, UTC) - timedelta(hours=self.offset_h)

    def _measure_offset(self, now: datetime, tick) -> None:
        """While prices are moving (tick time advanced since the last poll) the newest tick is a few seconds old,
        so tick time minus UTC is the broker's clock offset. Closures never update it (prices do not move)."""
        raw = tick.time_msc / 1000 if tick.time_msc else float(tick.time)
        close_polls = self._prev_poll is not None and (now - self._prev_poll).total_seconds() <= 120
        if self._prev_raw is not None and raw > self._prev_raw and close_polls:
            lag = raw - now.timestamp()
            guess = round(lag / 1800) / 2                     # hours, in half-hour steps
            if abs(lag - guess * 3600) < 120 and abs(guess) <= 14 and guess != self.offset_h:
                log.warning("broker server clock is UTC%+g h (was assuming %+g h); adjusting", guess, self.offset_h)
                self.offset_h = guess
                self._last_tick = None          # times measured with the old offset are not comparable
        self._prev_raw, self._prev_poll = raw, now

    # ------------------------------------------------------------------ startup
    def startup(self, now: datetime, inspect_only: bool = False) -> None:
        m = self.broker.mt5
        acct = self.broker.account()
        if acct is None:
            raise StartupError("no account information: is MetaTrader 5 running and logged in?")
        demo = acct.trade_mode == m.ACCOUNT_TRADE_MODE_DEMO
        if not demo and not inspect_only and not (self.cfg.allow_live and self.allow_live_flag):
            raise LiveAccountRefused(
                f"account {acct.login} is a real-money account (trade_mode={acct.trade_mode}); refusing to trade. "
                "Real money needs allow_live = true in the config AND the --allow-live flag.")
        if not demo:
            log.warning("REAL-MONEY ACCOUNT %s: live trading enabled by config and flag", acct.login)
        term = self.broker.terminal()
        if term is not None and not term.trade_allowed:
            log.warning("Algo Trading is switched off in the terminal: no trades until it is on")
        if term is not None and term.tradeapi_disabled:
            log.warning("MT5 option 'Disable algorithmic trading via external Python API' is ticked "
                        "(Tools > Options > Expert Advisors): no trades until it is unticked")
        self.symbol = self.broker.resolve_symbol(self.cfg.symbols)
        if not self.symbol:
            raise StartupError(f"none of {', '.join(self.cfg.symbols)} is available in this terminal")
        info = self.broker.symbol(self.symbol)
        self.digits = info.digits
        self.pip = info.point * 10 if info.digits in (3, 5) else info.point
        tick = self.broker.tick(self.symbol)
        if tick is not None:
            self._prev_raw = tick.time_msc / 1000 if tick.time_msc else float(tick.time)
            self._prev_poll = now
            self._last_tick = self.tick_time(tick)
            age = (now - self.tick_time(tick)).total_seconds()
            if age < -120 and not self.cfg.auto_server_offset:
                raise StartupError(f"the latest price is {-age:.0f}s in the future: fix the PC clock "
                                   "or server_utc_offset_hours")
            if age < -120:
                log.info("broker clock is ahead of UTC; the offset will be measured from live prices")
                self._last_tick = None
            elif age <= self.cfg.stale_tick_sec:
                log.info("clock check: latest price is %.0fs old", age)
            else:
                log.info("market looks shut (latest price %.0f min old)", age / 60)
        if acct.balance:
            self.journal.set_peak(acct.balance)
        self._reconcile(now, self.broker.positions(self.symbol, self.cfg.magic))
        s = self.cal.next_slot(now)
        log.info("ready: %s, account %s (%s, %s %.2f), risk %.2f%% per trade%s. Next: gotobi %s, buy %s, close %s",
                 self.symbol, acct.login, "demo" if demo else "REAL", acct.currency, acct.balance, self.cfg.risk_pct,
                 " [DRY RUN]" if self.dry_run else "", s.gotobi, iso(s.entry), iso(s.exit))
        if self.journal.halted:
            log.critical("kill switch is ON since %s: %s", self.journal.halted["at"], self.journal.halted["reason"])

    # ------------------------------------------------------------------ one poll
    def step(self, now: datetime) -> None:
        positions = self.broker.positions(self.symbol, self.cfg.magic)   # raises BrokerUnavailable on error
        self._reconcile(now, positions)
        tick, fresh = self._prices(now)
        if positions:
            self._manage(now, positions)
            return
        self._maybe_enter(now, tick, fresh)

    def poll_interval(self, now: datetime) -> float:
        s = self.cal.next_slot(now - timedelta(minutes=5))
        near_entry = -60 <= (now - s.entry).total_seconds() <= 300
        near_exit = -180 <= (now - s.exit).total_seconds() <= 60
        return 1.0 if near_entry or near_exit else self.cfg.poll_sec

    # ------------------------------------------------------------------ prices
    def _prices(self, now: datetime):
        tick = self.broker.tick(self.symbol)
        fresh = False
        if tick is not None:
            if self.cfg.auto_server_offset:
                self._measure_offset(now, tick)
            tt = self.tick_time(tick)
            if self._last_tick is not None and tt - self._last_tick >= CLOSURE:   # prices back after a closure
                self.reopen_at = tt
                self.journal.reopen_at = iso(tt)
                self.journal.save()
            if self._last_tick is None or tt > self._last_tick:
                self._last_tick = tt
            age = (now - tt).total_seconds()
            if age < -120:
                if not self.cfg.auto_server_offset:
                    self.say(f"future-{now:%Y%m%d%H}", logging.ERROR,
                             "the latest price is %.0fs ahead of the PC clock: check the clock", -age)
            else:
                fresh = age <= self.cfg.stale_tick_sec
        if fresh and self.fresh_since is None:
            self.fresh_since = now
        if not fresh:
            self.fresh_since = None
        return tick, fresh

    # ------------------------------------------------------------------ bookkeeping
    def _reconcile(self, now: datetime, positions: list) -> None:
        """Journal vs broker: record trades the broker closed (stop hit, manual close) and adopt unknown ones."""
        ids = {p.ticket for p in positions} | {p.identifier for p in positions}
        for key, rec in self.journal.open_slots():
            if rec.get("ticket") not in ids:
                self._finalize(now, key, rec)
        known = {rec.get("ticket") for _, rec in self.journal.open_slots()}
        for p in positions:
            if p.ticket not in known and p.identifier not in known:
                self._adopt(now, p)

    def _slot_of_position(self, p) -> tuple[str, datetime]:
        found = re.search(r"(\d{4}-\d{2}-\d{2})", p.comment or "")
        if found:
            d = date.fromisoformat(found.group(1))
            return d.isoformat(), self.cal.slot(d).exit
        opened = self.tick_time(p)
        for d in (opened.date(), opened.date() + timedelta(days=1), opened.date() + timedelta(days=2)):
            if self.cal.is_trade_day(d):
                s = self.cal.slot(d)
                if s.entry - timedelta(hours=1) <= opened < s.exit:
                    return d.isoformat(), s.exit
        return f"unknown-{p.ticket}", opened + timedelta(hours=9)

    def _adopt(self, now: datetime, p) -> None:
        key, due = self._slot_of_position(p)
        if self.journal.get(key) is not None:
            key = f"{key}#{p.ticket}"
        log.warning("adopting position %s (%.2f lots at %.3f) as %s; it will be closed at %s",
                    p.ticket, p.volume, p.price_open, key, iso(due))
        self.journal.update(key, status="open", ticket=p.ticket, adopted=True, opened=iso(self.tick_time(p)),
                            entry_price=p.price_open, sl=p.sl, volume=p.volume, exit_due=iso(due), risk_amount=None)

    def _finalize(self, now: datetime, key: str, rec: dict) -> None:
        m = self.broker.mt5
        deals = self.broker.deals(rec["ticket"])
        outs = [d for d in deals if d.entry != m.DEAL_ENTRY_IN]
        if not outs:   # trade history can lag a few seconds behind the position list
            n = self._finalize_tries.get(key, 0) + 1
            self._finalize_tries[key] = n
            if n < 12:
                return
            self.journal.update(key, status="closed", reason="unknown", pnl=None, r=None, closed=iso(now),
                                note="position gone but no closing deal found in the history")
            log.error("gotobi %s: position %s is gone but its closing deal was not found", key, rec["ticket"])
            return
        last = max(outs, key=lambda d: (d.time_msc, d.ticket))
        pnl = sum(d.profit + d.swap + d.commission + d.fee for d in deals)
        if last.reason == m.DEAL_REASON_SL:
            reason = "stop"
        elif rec.get("exit_sent"):
            reason = "time"
        else:
            reason = "external"
        risk = rec.get("risk_amount")
        r = round(pnl / risk, 4) if risk else None
        self.journal.update(key, status="closed", reason=reason, close_price=last.price,
                            closed=iso(self.tick_time(last)), pnl=round(pnl, 2), r=r)
        log.info("gotobi %s closed (%s) at %.3f: %+.2f%s", key, reason, last.price, pnl,
                 f" ({r:+.2f}R)" if r is not None else "")
        acct = self.broker.account()
        if acct is not None:
            self._kill_switch(now, acct.balance)

    def _kill_switch(self, now: datetime, balance: float) -> None:
        self.journal.set_peak(balance)
        if self.journal.halted:
            return
        rs = [rec["r"] for _, rec in self.journal.closed() if rec.get("r") is not None]
        w = self.cfg.kill_window
        if len(rs) >= w and sum(rs[-w:]) < self.cfg.kill_sum_r:
            self.journal.halt(f"the last {w} trades lost {sum(rs[-w:]):.1f}R (limit {self.cfg.kill_sum_r}R)", now)
        elif self.journal.peak_balance and balance < self.journal.peak_balance * (1 - self.cfg.kill_max_drawdown):
            self.journal.halt(f"balance {balance:.2f} is more than {self.cfg.kill_max_drawdown:.0%} below its "
                              f"peak {self.journal.peak_balance:.2f}", now)
        if self.journal.halted:
            log.critical("KILL SWITCH ON: %s. No new trades until 'halted' is removed from state.json.",
                         self.journal.halted["reason"])

    def _mark(self, now: datetime, key: str, status: str, note: str, **extra) -> None:
        self.journal.update(key, status=status, note=note, at=iso(now), **extra)
        log.info("gotobi %s %s: %s", key, status, note)

    # ------------------------------------------------------------------ exits
    def _manage(self, now: datetime, positions: list) -> None:
        for p in positions:
            found = self.journal.slot_of_ticket(p.ticket) or self.journal.slot_of_ticket(p.identifier)
            if found is None:
                continue
            key, rec = found
            due = datetime.fromisoformat(rec["exit_due"])
            if now < due:
                continue
            r = self.broker.market_order(self.symbol, -1, p.volume, deviation=self.cfg.deviation_points,
                                         magic=self.cfg.magic, comment=f"gotobi exit {key}"[:31], position=p.ticket)
            if r.ok:
                late = (now - due).total_seconds()
                self.journal.update(key, exit_sent=iso(now), exit_fill=r.price, exit_late_sec=round(late))
                if late > 60:
                    log.warning("gotobi %s: exit was %.0f min late (bot was not running at %s)", key, late / 60,
                                iso(due))
            else:
                self.say(f"closefail-{key}-{r.retcode}", logging.ERROR,
                         "gotobi %s: close failed (%s %s); retrying every poll", key, r.retcode, r.message)

    # ------------------------------------------------------------------ entries
    def _maybe_enter(self, now: datetime, tick, fresh: bool) -> None:
        cfg = self.cfg
        s = self.cal.active(now)
        if s is None:
            return
        key = s.gotobi.isoformat()
        if self.journal.get(key) is not None:
            return
        if not self.dry_run and key not in self._history_checked:     # once per window per run of the bot
            recovered = self._recover_from_history(now, key, s)
            self._history_checked.add(key)
            if recovered:
                return
        if self.journal.halted:
            self._mark(now, key, "skipped", "kill switch is on")
            return
        if now >= s.exit - timedelta(minutes=cfg.min_hold_min):
            self._mark(now, key, "missed", "too close to the exit")
            return
        if not fresh:
            self.say(f"wait-closed-{key}", logging.INFO,
                     "gotobi %s: waiting for live prices (market shut or price feed down)", key)
            return
        # after a market closure (weekend, or a price-feed outage) wait reopen_wait_min from the first price back,
        # as the backtest did; if the bot missed this weekend's reopen, wait from when it saw prices itself
        wait = timedelta(minutes=cfg.reopen_wait_min)
        anchor, ro = s.entry, self.reopen_at
        recent = ro is not None and ro > s.entry - wait
        if not recent and s.entry.weekday() >= 5:
            ro, recent = self.fresh_since, True
        if recent:
            anchor = max(anchor, ro + wait)
        if now < anchor:
            self.say(f"wait-reopen-{key}", logging.INFO, "gotobi %s: market open, waiting until %s for spreads to settle",
                     key, iso(anchor))
            return
        # the delay limit runs from the schedule on weekdays (a feed outage must not stretch it) and from the
        # reopen for entries scheduled inside the weekend closure
        start = anchor if s.entry.weekday() >= 5 else s.entry
        if now > start + timedelta(minutes=cfg.max_entry_delay_min):
            self._mark(now, key, "missed", f"could not enter within {cfg.max_entry_delay_min} min of schedule")
            return
        spread = (tick.ask - tick.bid) / self.pip
        if spread > cfg.max_spread_pips:
            self.say(f"wait-spread-{key}", logging.INFO, "gotobi %s: spread %.1f pips is above %.1f, waiting",
                     key, spread, cfg.max_spread_pips)
            return
        term = self.broker.terminal()
        if term is not None and (not term.trade_allowed or term.tradeapi_disabled):
            self.say(f"algo-off-{key}", logging.ERROR, "gotobi %s: trading is switched off in MetaTrader 5 (Algo Trading "
                     "button or the Python API option); waiting for it to be switched on", key)
            return
        acct = self.broker.account()
        if acct is None:
            raise BrokerUnavailable("account_info failed")
        info = self.broker.symbol(self.symbol)
        sl = round(tick.ask - cfg.stop_pips * self.pip, self.digits)
        risk_amount = acct.equity * cfg.risk_pct / 100
        loss = self.broker.loss_per_lot(self.symbol, tick.ask, sl)
        margin = self.broker.margin_per_lot(self.symbol, tick.ask)
        size = size_position(risk_amount, loss, info.volume_min, info.volume_max, info.volume_step, margin,
                             acct.margin_free, cfg.max_margin_use, cfg.below_min_lot)
        if size.lots is None:
            self._mark(now, key, "skipped", size.note)
            return
        comment = f"gotobi {key}"
        r = self.broker.market_order(self.symbol, +1, size.lots, sl=sl, deviation=cfg.deviation_points,
                                     magic=cfg.magic, comment=comment, check_only=self.dry_run)
        if self.dry_run:
            self._mark(now, key, "dryrun", f"order_check {'accepted' if r.ok else 'rejected'} ({r.retcode} {r.message})",
                       lots=size.lots, sl=sl, ask=tick.ask, risk_amount=round(size.risk_at_size, 2))
            return
        if r.ok:
            ticket = self._find_ticket(r, comment)
            self.journal.update(key, status="open", ticket=ticket, opened=iso(now), entry_price=r.price or tick.ask,
                                sl=sl, volume=r.volume or size.lots, risk_amount=round(size.risk_at_size, 2),
                                risk_target=round(risk_amount, 2), equity_at_entry=round(acct.equity, 2),
                                exit_due=iso(s.exit), size_note=size.note, spread_pips=round(spread, 2))
            log.info("gotobi %s: bought %.2f lots at %.3f, stop %.3f, risking %.2f %s; closes %s", key,
                     r.volume or size.lots, r.price or tick.ask, sl, size.risk_at_size, acct.currency, iso(s.exit))
        elif r.category in ("transient", "market_closed"):
            self.say(f"retry-{key}-{r.retcode}", logging.WARNING, "gotobi %s: order not filled (%s %s), retrying",
                     key, r.retcode, r.message)
        else:
            self._mark(now, key, "skipped", f"order rejected: {r.retcode} {r.message}")

    def _recover_from_history(self, now: datetime, key: str, s) -> bool:
        """Second guard against trading a day twice: if the broker's history already holds a buy by this bot inside
        this trade window (the journal was lost or is stale), record that trade instead of buying again."""
        m = self.broker.mt5
        deals = self.broker.deals_between(s.entry - timedelta(days=2), now + timedelta(days=2))
        mine = [d for d in deals if d.entry == m.DEAL_ENTRY_IN and d.magic == self.cfg.magic and d.symbol == self.symbol
                and self.tick_time(d) >= s.entry - timedelta(minutes=10)]
        if not mine:
            return False
        first = min(mine, key=lambda d: d.time_msc)
        log.error("gotobi %s: the broker already shows a buy at %s (position %s) that the journal does not know; "
                  "recording it instead of buying again", key, iso(self.tick_time(first)), first.position_id)
        self.journal.update(key, status="open", ticket=first.position_id, recovered=True,
                            opened=iso(self.tick_time(first)), entry_price=first.price, volume=first.volume,
                            exit_due=iso(s.exit), risk_amount=None)
        self._finalize(now, key, self.journal.get(key))     # position is gone (else it would have been adopted)
        return True

    def _find_ticket(self, r, comment: str) -> int:
        for p in self.broker.positions(self.symbol, self.cfg.magic):
            if r.order and (p.ticket == r.order or p.identifier == r.order):
                return p.ticket
        mine = [p for p in self.broker.positions(self.symbol, self.cfg.magic) if p.comment == comment]
        return max(mine, key=lambda p: p.time_msc).ticket if mine else r.order

    # ------------------------------------------------------------------ pre-flight
    def preflight(self, now: datetime) -> tuple[bool, list[str]]:
        """Check the real terminal and account without trading. Returns (ready, report lines)."""
        m, cfg, out, ready = self.broker.mt5, self.cfg, [], True

        def line(ok, text, blocking=True):
            nonlocal ready
            out.append(f"[{'OK' if ok else ('!!' if blocking else '--')}] {text}")
            ready = ready and (ok or not blocking)

        acct, term = self.broker.account(), self.broker.terminal()
        demo = acct.trade_mode == m.ACCOUNT_TRADE_MODE_DEMO
        line(True, f"account {acct.login} on {acct.server}: {'DEMO' if demo else 'REAL MONEY'}, {acct.currency} "
                   f"{acct.balance:,.2f}, leverage 1:{acct.leverage}")
        if not demo:
            line(cfg.allow_live, "real-money account: the bot trades it only with allow_live = true AND --allow-live")
        line(term.trade_allowed, "Algo Trading button is " + ("on" if term.trade_allowed else "OFF: switch it on"))
        line(not term.tradeapi_disabled, "Python API trading is " + (
            "allowed" if not term.tradeapi_disabled else
            "DISABLED: untick Tools > Options > Expert Advisors > 'Disable algorithmic trading via external Python API'"))
        info = self.broker.symbol(self.symbol)
        line(info.trade_mode == m.SYMBOL_TRADE_MODE_FULL, f"symbol {self.symbol}: lots {info.volume_min}-{info.volume_max} "
             f"step {info.volume_step}, contract {info.trade_contract_size:,.0f}, digits {info.digits}")
        tick = self.broker.tick(self.symbol)
        raw_age = now.timestamp() - tick.time if tick is not None else None
        live = raw_age is not None and any(abs(raw_age + h * 3600) < 120 for h in [x / 2 for x in range(-28, 29)])
        if live:
            guess = round(-raw_age / 1800) / 2
            spread = (tick.ask - tick.bid) / self.pip
            line(True, f"prices are live; broker clock is UTC{guess:+g} h "
                       f"({'auto-detected' if cfg.auto_server_offset else f'config says {cfg.server_utc_offset_hours:+g}'})")
            if not cfg.auto_server_offset and guess != cfg.server_utc_offset_hours:
                line(False, f"set server_utc_offset_hours = {guess} (or auto_server_offset = true)")
            line(spread <= cfg.max_spread_pips, f"spread now {spread:.1f} pips (bot waits above {cfg.max_spread_pips})",
                 blocking=False)
        else:
            line(False, "market is shut or prices are stale right now: run --preflight again during market hours",
                 blocking=False)
        if tick is not None:
            sl = round(tick.ask - cfg.stop_pips * self.pip, self.digits)
            risk = acct.equity * cfg.risk_pct / 100
            loss = self.broker.loss_per_lot(self.symbol, tick.ask, sl)
            margin = self.broker.margin_per_lot(self.symbol, tick.ask)
            size = size_position(risk, loss, info.volume_min, info.volume_max, info.volume_step, margin,
                                 acct.margin_free, cfg.max_margin_use, cfg.below_min_lot)
            line(size.lots is not None, f"trade size at {cfg.risk_pct}% risk: " + (
                f"{size.lots} lots, losing {size.risk_at_size:,.2f} {acct.currency} if the 55-pip stop is hit"
                + (f" ({size.note})" if size.note != "ok" else "") if size.lots else size.note))
            if size.lots and live:
                r = self.broker.market_order(self.symbol, +1, size.lots, sl=sl, deviation=cfg.deviation_points,
                                             magic=cfg.magic, comment="gotobi preflight", check_only=True)
                line(r.ok, f"broker order check of that buy with its stop: "
                           f"{'accepted' if r.ok else 'REJECTED'} ({r.retcode} {r.message})")
        s = self.cal.next_slot(now)
        local = lambda t: t.astimezone().strftime("%a %d %b %H:%M")    # noqa: E731
        line(True, f"next trade: gotobi {s.gotobi}: buy {iso(s.entry)} (your PC: {local(s.entry)}), "
                   f"close {iso(s.exit)} (your PC: {local(s.exit)})")
        out.append("READY: start run_bot.bat" if ready else "NOT READY: fix the lines marked !!")
        return ready, out

    # ------------------------------------------------------------------ status
    def status(self, now: datetime) -> str:
        s = self.cal.next_slot(now)
        lines = [f"symbol {self.symbol}; next gotobi {s.gotobi}: buy {iso(s.entry)}, close {iso(s.exit)}"]
        for key, rec in self.journal.open_slots():
            lines.append(f"OPEN {key}: {rec.get('volume')} lots at {rec.get('entry_price')}, stop {rec.get('sl')}, "
                         f"closes {rec.get('exit_due')}")
        closed = self.journal.closed()
        if closed:
            pnl = sum(rec.get("pnl") or 0 for _, rec in closed)
            wins = sum(1 for _, rec in closed if (rec.get("pnl") or 0) > 0)
            lines.append(f"{len(closed)} closed trades, {wins} won, total {pnl:+.2f}")
            for key, rec in closed[-5:]:
                lines.append(f"  {key}: {rec.get('reason')} {rec.get('pnl'):+.2f}" if rec.get("pnl") is not None
                             else f"  {key}: {rec.get('reason')}")
        if self.journal.halted:
            lines.append(f"KILL SWITCH ON: {self.journal.halted['reason']}")
        return "\n".join(lines)
