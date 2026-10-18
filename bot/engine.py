"""The trading engine. main.py calls step(now) every few seconds (and at the exact second of the fix sell).

Each gotobi day has up to two trades, both journalled under the gotobi date:
  "YYYY-MM-DD"        the long: bought on D-1 at 15:55 UTC, 55-pip stop, +30-pip take-profit, closed at 00:54 UTC
  "YYYY-MM-DD/short"  the post-fix short: sold at the 09:55 JST fix, 55-pip stop, bought back 30 minutes later
The short is only sent when no position is open, so the two never overlap (no hedging).

Every decision is made from `now` (UTC), the journal and what the broker reports, so a crash or restart at any
moment resumes correctly: an open trade is still closed on time (or at once, if the exit was missed), and no
trade is ever made twice.
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
SHORT = "/short"


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
        self._unresolved: dict[str, int] = {}       # closed trades whose result is not in the history (yet)
        self._history_checked: set[str] = set()
        self._lags: list[float] = []                # PC clock minus the time of each new tick (seconds)
        self.account_id: tuple | None = None        # (login, server) the bot started on; it trades nothing else
        self.clock_note: str | None = None      # set by main.py: how the PC clock was checked
        self.now_fn = None                      # set by main.py: the corrected clock, read again right before a
                                                # time-critical send (the step's `now` can be a few calls old)
        self.clock_ok = lambda: True            # set by main.py: was the PC clock confirmed by time servers?

    def fresh_now(self, now: datetime) -> datetime:
        return self.now_fn() if self.now_fn is not None else now

    def clock_suspect(self) -> float | None:
        """With the PC clock NOT confirmed by time servers, the broker's live prices are the remaining check: a
        new tick is at most a few seconds old, so a PC clock that sits far from them is wrong. Returns the typical
        gap in seconds when it is over 30 s (then no new trades), else None."""
        if self.clock_ok() or len(self._lags) < 5:
            return None
        gap = sorted(self._lags)[len(self._lags) // 2]
        return gap if abs(gap) > 30 else None

    def say(self, key: str, level: int, msg: str, *args) -> None:
        """Log a message once per key (waiting states repeat every poll)."""
        if key not in self._said:
            self._said.add(key)
            log.log(level, msg, *args)

    def tick_time(self, tick) -> datetime:
        return datetime.fromtimestamp(tick.time, UTC) - timedelta(hours=self.offset_h)

    def msc_time(self, obj) -> datetime:
        stamp = obj.time_msc / 1000 if obj.time_msc else float(obj.time)
        return datetime.fromtimestamp(stamp, UTC) - timedelta(hours=self.offset_h)

    def _measure_offset(self, now: datetime, tick, apply: bool = True) -> None:
        """While prices are moving (tick time advanced since the last poll) the newest tick is a few seconds old,
        so tick time minus UTC is the broker's clock offset. Closures never update it (prices do not move).
        apply=False (the PC clock is not confirmed by time servers): an apparent offset could just as well be the
        PC clock being wrong, so it is reported and NOT adopted; prices then look stale and nothing is traded."""
        raw = tick.time_msc / 1000 if tick.time_msc else float(tick.time)
        close_polls = self._prev_poll is not None and (now - self._prev_poll).total_seconds() <= 120
        if self._prev_raw is not None and raw > self._prev_raw and close_polls:
            lag = raw - now.timestamp()
            guess = round(lag / 1800) / 2                     # hours, in half-hour steps
            if abs(lag - guess * 3600) < 120 and abs(guess) <= 14 and guess != self.offset_h:
                if apply:
                    log.warning("broker server clock is UTC%+g h (was assuming %+g h); adjusting", guess,
                                self.offset_h)
                    self.offset_h = guess
                    self._last_tick = None          # times measured with the old offset are not comparable
                    self._lags = []
                else:
                    self.say(f"unverified-offset-{now:%Y%m%d%H}", logging.ERROR,
                             "prices are moving but their times are %+g h from the PC clock, and the PC clock could "
                             "not be checked against time servers: not trading. Fix the Windows clock, allow UDP "
                             "port 123 (time servers), or set server_utc_offset_hours", guess - self.offset_h)
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
        self.account_id = (acct.login, acct.server)
        owner = self.journal.account
        if owner and list(owner) != [acct.login, acct.server] and not inspect_only:
            if self.journal.open_slots():
                raise StartupError(f"this state folder belongs to account {owner[0]} on {owner[1]}, which still has "
                                   f"open trades in it; log MetaTrader 5 in to that account, or give this account "
                                   f"its own state_dir")
            log.warning("state folder was used with account %s on %s; now trading %s on %s", owner[0], owner[1],
                        acct.login, acct.server)
        if not inspect_only:
            self.journal.set_account(acct.login, acct.server)
        if self.journal.recovered_from and not inspect_only:
            log.critical("the journal was rebuilt from %s: checking the broker's positions and history",
                         "its backup" if self.journal.recovered_from == "backup" else "scratch")
            if self.journal.recovered_from == "nothing" and not self.journal.halted:
                # nothing is known about the kill switch or the last trades: manage what is open, open nothing new
                self.journal.halt("state.json and its backup were unreadable; check the account, then run the bot "
                                  "once with --clear-halt to resume", now)
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
        log.info("ready: %s, account %s (%s, %s %.2f), risk %.2f%% per trade%s. Next: gotobi %s, buy %s, close %s%s",
                 self.symbol, acct.login, "demo" if demo else "REAL", acct.currency, acct.balance, self.cfg.risk_pct,
                 " [DRY RUN]" if self.dry_run else "", s.gotobi, iso(s.entry), iso(s.exit), self._short_text(s))
        if self.journal.halted:
            log.critical("kill switch is ON since %s: %s", self.journal.halted.get("at"),
                         self.journal.halted.get("reason"))

    def _short_text(self, s) -> str:
        if not self.cfg.post_fix_short:
            return ""
        return f"; short {s.short_open.isoformat(timespec='milliseconds')} -> {iso(s.short_close)}"

    # ------------------------------------------------------------------ one poll
    def step(self, now: datetime) -> None:
        acct = self.broker.account()
        if acct is None:
            raise BrokerUnavailable("account_info failed")
        if not self._same_account(acct):
            return
        everything = self.broker.symbol_positions(self.symbol)       # raises BrokerUnavailable on error
        positions = [p for p in everything if p.magic == self.cfg.magic]
        self._reconcile(now, positions)
        live = self.broker.orders(self.symbol, self.cfg.magic)       # queued orders of ours: leftovers
        if live:
            self._cancel_leftovers(live)
        self._resolve_pending(now, live)
        tick, fresh = self._prices(now)
        if positions:
            self._manage(now, positions)
            return
        if everything:          # someone else's trade on this symbol (manual, another robot): stay out of its way
            self.say(f"foreign-{sorted(p.ticket for p in everything)}", logging.WARNING,
                     "a %s position this bot did not open is open (ticket %s): no new trades until it is closed",
                     self.symbol, ", ".join(str(p.ticket) for p in everything))
            return
        if live or self.journal.pending() or any(k in self._unresolved for k, _ in self.journal.open_slots()):
            return              # an earlier order is not accounted for yet: nothing new until it is
        self._maybe_enter(now, tick, fresh)
        self._maybe_short(now, tick, fresh)

    def _cancel_leftovers(self, live: list) -> None:
        """The bot only sends market orders, so a live order of ours can only be a request the broker queued
        ("placed") or the unfilled rest of a partial fill. Cancel it, so it cannot fill later on top of another
        trade; while any is live, nothing new is opened. A fill that beats the cancel is adopted as usual."""
        for o in live:
            if self.dry_run:
                self.say(f"live-{o.ticket}", logging.WARNING, "live order %s (%s) found; dry run, not cancelling",
                         o.ticket, o.comment)
                continue
            r = self.broker.cancel(o.ticket)
            if r.ok:
                log.warning("cancelled leftover live order %s (%s, %.2f lots): the bot only sends market orders",
                            o.ticket, o.comment, o.volume_current)
            else:
                self.say(f"cancelfail-{o.ticket}-{r.retcode}", logging.ERROR, "could not cancel live order %s (%s "
                         "%s); retrying every poll, no new trades meanwhile", o.ticket, r.retcode, r.message)

    def _resolve_pending(self, now: datetime, live: list = ()) -> None:
        """Orders sent whose outcome never came back ("sending": the bot stopped or failed right after sending;
        "unknown": no reply, a timeout, or only "placed"). They are NEVER sent again. A fill shows up as an open
        position, which _reconcile has just adopted into the same slot, or as deals in the history (a fill that
        already stopped out), which is recorded here. When the trade's window is over with no sign of a fill and
        no live order left, the slot is marked missed."""
        for key, rec in self.journal.pending():
            found = re.fullmatch(r"(\d{4}-\d{2}-\d{2})(/short)?", key)
            if not found:
                continue
            if any(o.comment == rec.get("comment") or (rec.get("order") and o.ticket == rec["order"]) for o in live):
                continue        # still queued at the broker: being cancelled; decide once it is gone
            s = self.cal.slot(date.fromisoformat(found.group(1)))
            short = bool(found.group(2))
            if self._recover_from_history(now, key, s, side=-1 if short else +1):
                continue
            # a long sent at ~15:55 is settled by its 00:54 exit (and must not block the short at the fix);
            # the short's own deals get two extra minutes to reach the history
            if now >= (s.short_close + timedelta(minutes=2) if short else s.exit):
                self._mark(now, key, "missed", "the order's outcome never came back and the broker shows no fill")

    def _same_account(self, acct) -> bool:
        """The terminal must still be on the account the bot started with, and a real-money account still needs
        both keys. Otherwise the bot does nothing at all: no entries, and no bookkeeping of trades it cannot see."""
        if self.account_id is not None and (acct.login, acct.server) != self.account_id:
            self.say(f"account-{acct.login}-{acct.server}", logging.CRITICAL,
                     "MetaTrader 5 is now on account %s (%s), not %s (%s) as when the bot started: paused. Log the "
                     "terminal back in to %s, or restart the bot to use the new account", acct.login, acct.server,
                     self.account_id[0], self.account_id[1], self.account_id[0])
            return False
        if acct.trade_mode != self.broker.mt5.ACCOUNT_TRADE_MODE_DEMO and not (
                self.cfg.allow_live and self.allow_live_flag):
            self.say(f"real-{acct.login}", logging.CRITICAL, "account %s is a real-money account and live trading "
                     "is not unlocked (allow_live = true AND --allow-live): paused", acct.login)
            return False
        return True

    def poll_interval(self, now: datetime) -> float:
        s = self.cal.next_slot(now - timedelta(minutes=5))
        near_entry = -60 <= (now - s.entry).total_seconds() <= 300
        near_exit = -180 <= (now - s.exit).total_seconds() <= 60
        wait = 1.0 if near_entry or near_exit else self.cfg.poll_sec
        if self.cfg.post_fix_short:
            for d in (now.date(), now.date() + timedelta(days=1)):
                if not self.cal.is_trade_day(d):
                    continue
                t = self.cal.slot(d)
                if t.short_open <= now <= t.short_late:
                    wait = min(wait, 0.25)                    # the sell window is a few seconds wide
                for event in (t.short_open, t.short_close):
                    dt = (event - now).total_seconds()
                    if 0 < dt < wait:
                        wait = dt + 0.001                     # wake at the very moment it is due
        return wait

    def quiet(self, now: datetime) -> bool:
        """No trade action due within 5 minutes: safe for slow housekeeping such as the clock check."""
        for d in (now.date() - timedelta(days=1), now.date(), now.date() + timedelta(days=1)):
            if self.cal.is_trade_day(d):
                s = self.cal.slot(d)
                if any(abs((e - now).total_seconds()) <= 300 for e in (s.entry, s.exit, s.short_open, s.short_close)):
                    return False
        return True

    # ------------------------------------------------------------------ prices
    def _prices(self, now: datetime):
        tick = self.broker.tick(self.symbol)
        fresh = False
        if tick is not None:
            raw = tick.time_msc / 1000 if tick.time_msc else float(tick.time)
            moved = self._prev_raw is not None and raw > self._prev_raw
            if self.cfg.auto_server_offset:
                self._measure_offset(now, tick, apply=self.clock_ok())
            else:
                self._prev_raw = raw
            tt = self.tick_time(tick)
            if moved:                         # a new price since the last poll: it is at most a few seconds old
                self._lags = (self._lags + [(now - tt).total_seconds()])[-20:]
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
        """Journal vs broker: record trades the broker closed (stop, target, manual close) and adopt unknown ones."""
        ids = {p.ticket for p in positions} | {p.identifier for p in positions}
        for key, rec in self.journal.open_slots():
            if rec.get("ticket") not in ids:
                self._finalize(now, key, rec)
        known = {rec.get("ticket") for _, rec in self.journal.open_slots()}
        for p in positions:
            if p.ticket not in known and p.identifier not in known:
                self._adopt(now, p)

    def _slot_of_position(self, p) -> tuple[str, datetime]:
        short = p.type == self.broker.mt5.POSITION_TYPE_SELL
        found = re.search(r"(\d{4}-\d{2}-\d{2})", p.comment or "")
        if found:
            d = date.fromisoformat(found.group(1))
            s = self.cal.slot(d)
            return (d.isoformat() + SHORT, s.short_close) if short else (d.isoformat(), s.exit)
        opened = self.tick_time(p)
        for d in (opened.date(), opened.date() + timedelta(days=1), opened.date() + timedelta(days=2)):
            if self.cal.is_trade_day(d):
                s = self.cal.slot(d)
                if short and s.fix - timedelta(minutes=5) <= opened < s.short_close:
                    return d.isoformat() + SHORT, s.short_close
                if not short and s.entry - timedelta(hours=1) <= opened < s.exit:
                    return d.isoformat(), s.exit
        hold = timedelta(minutes=self.cfg.short_minutes) if short else timedelta(hours=9)
        return f"unknown-{p.ticket}", opened + hold

    def _adopt(self, now: datetime, p) -> None:
        key, due = self._slot_of_position(p)
        existing = self.journal.get(key)
        if existing is not None and existing.get("status") not in ("sending", "unknown"):
            key, existing = f"{key}#{p.ticket}", None
        short = p.type == self.broker.mt5.POSITION_TYPE_SELL
        log.warning("adopting %s position %s (%.2f lots at %.3f) as %s; it will be closed at %s",
                    "sell" if short else "buy", p.ticket, p.volume, p.price_open, key, iso(due))
        self.journal.update(key, status="open", ticket=p.ticket, adopted=True, opened=iso(self.tick_time(p)),
                            entry_price=p.price_open, sl=p.sl, volume=p.volume, exit_due=iso(due),
                            risk_amount=existing.get("risk_amount") if existing else None,  # our own order: R counts
                            **({"side": "short"} if short else {}))

    def _finalize(self, now: datetime, key: str, rec: dict) -> None:
        m = self.broker.mt5
        deals = self.broker.deals(rec["ticket"])
        if deals is None:      # the history could not be read: that is not "no closing deal". Keep the trade
            self._unresolved[key] = self._unresolved.get(key, 0) + 1     # unresolved, no new trades, keep asking
            self.say(f"history-{key}-{now:%Y%m%d%H}", logging.ERROR, "gotobi %s: the trade history cannot be read "
                     "(%s); the trade stays unresolved and no new trade opens until it is", key,
                     self.broker.mt5.last_error())
            return
        outs = [d for d in deals if d.entry != m.DEAL_ENTRY_IN]
        if not outs:   # trade history can lag a few seconds behind the position list: never write the trade off
            n = self._finalize_tries.get(key, 0) + 1
            self._finalize_tries[key] = n
            if n >= 12:
                self._unresolved[key] = n
                self.say(f"noclose-{key}-{now:%Y%m%d%H}", logging.ERROR, "gotobi %s: position %s is gone but its "
                         "closing deal is not in the history; the trade stays unresolved and no new trade opens "
                         "until it shows up", key, rec["ticket"])
            return
        self._unresolved.pop(key, None)
        last = max(outs, key=lambda d: (d.time_msc, d.ticket))
        pnl = sum(d.profit + d.swap + d.commission + d.fee for d in deals)
        if last.reason == m.DEAL_REASON_SL:
            reason = "stop"
        elif last.reason == m.DEAL_REASON_TP:
            reason = "target"
        elif rec.get("exit_sent"):
            reason = "time"
        else:
            reason = "external"
        risk = rec.get("risk_amount")
        r = round(pnl / risk, 4) if risk else None
        extra = {}
        ins = [d for d in deals if d.entry == m.DEAL_ENTRY_IN]
        found = re.fullmatch(r"(\d{4}-\d{2}-\d{2})" + SHORT, key)
        if found and ins:             # how close to 09:55:00 JST the sell really filled (the edge depends on it)
            fix = self.cal.slot(date.fromisoformat(found.group(1))).fix
            extra["filled_vs_fix_sec"] = round((self.msc_time(min(ins, key=lambda d: d.time_msc)) - fix)
                                               .total_seconds(), 3)
        self.journal.update(key, status="closed", reason=reason, close_price=last.price,
                            closed=iso(self.tick_time(last)), pnl=round(pnl, 2), r=r, **extra)
        log.info("gotobi %s closed (%s) at %.3f: %+.2f%s", key, reason, last.price, pnl,
                 f" ({r:+.2f}R)" if r is not None else "")
        acct = self.broker.account()
        if acct is not None:
            self._kill_switch(now, acct.balance, acct.equity)

    def _kill_switch(self, now: datetime, balance: float, equity: float | None = None) -> None:
        """Checked after every closed trade and again right before every entry (money can also go while flat:
        manual trades, withdrawals). The drawdown rule uses equity when known."""
        self.journal.set_peak(balance)
        if self.journal.halted:
            return
        # the R rule watches the main trade (the long), counting from the last --clear-halt; the drawdown rule
        # watches the whole account
        since = self.journal.r_reset_at
        rs = [rec["r"] for _, rec in self.journal.closed() if rec.get("r") is not None and rec.get("side") != "short"
              and (since is None or (rec.get("closed") or "") > since)]
        w = self.cfg.kill_window
        level = equity if equity is not None else balance
        if len(rs) >= w and sum(rs[-w:]) < self.cfg.kill_sum_r:
            self.journal.halt(f"the last {w} trades lost {sum(rs[-w:]):.1f}R (limit {self.cfg.kill_sum_r}R)", now)
        elif self.journal.peak_balance and level <= self.journal.peak_balance * (1 - self.cfg.kill_max_drawdown):
            self.journal.halt(f"equity {level:.2f} is {self.cfg.kill_max_drawdown:.0%} or more below its peak "
                              f"{self.journal.peak_balance:.2f}", now)
        if self.journal.halted:
            log.critical("KILL SWITCH ON: %s. No new trades until you run the bot once with --clear-halt.",
                         self.journal.halted["reason"])

    def _mark(self, now: datetime, key: str, status: str, note: str, **extra) -> None:
        self.journal.update(key, status=status, note=note, at=iso(now), **extra)
        log.info("gotobi %s %s: %s", key, status, note)

    # ------------------------------------------------------------------ exits
    def _manage(self, now: datetime, positions: list) -> None:
        m = self.broker.mt5
        for p in positions:
            found = self.journal.slot_of_ticket(p.ticket) or self.journal.slot_of_ticket(p.identifier)
            if found is None:
                continue
            key, rec = found
            due = datetime.fromisoformat(rec["exit_due"])
            if now < due:
                continue
            side = -1 if p.type == m.POSITION_TYPE_BUY else +1        # sell to close a buy, buy to close a sell
            r = self.broker.market_order(self.symbol, side, p.volume, deviation=self.cfg.deviation_points,
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

    # ------------------------------------------------------------------ entries: the long
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
        if self._algo_off(key):
            return
        if not self.clock_ok() and len(self._lags) < 5:
            self.say(f"clock-wait-{key}", logging.WARNING, "gotobi %s: the PC clock is not confirmed by time servers; "
                     "checking it against the broker's live prices before trading", key)
            return
        gap = self.clock_suspect()
        if gap is not None:
            self.say(f"clock-{key}", logging.ERROR, "gotobi %s: the PC clock is about %.0f s off the broker's prices "
                     "and could not be checked against time servers: not trading. Fix the Windows clock or allow "
                     "UDP port 123", key, gap)
            return
        acct = self.broker.account()
        if acct is None:
            raise BrokerUnavailable("account_info failed")
        self._kill_switch(now, acct.balance, acct.equity)
        if self.journal.halted:
            self._mark(now, key, "skipped", "kill switch is on")
            return
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
        tp_dist = cfg.take_profit_pips * self.pip if cfg.take_profit_pips else 0.0
        comment = f"gotobi {key}"
        if not self.dry_run:     # written BEFORE sending: whatever happens next, this slot is never sent twice
            self._intent(now, key, comment, size, risk_amount, acct, s.exit, spread)
        r = self.broker.market_order(self.symbol, +1, size.lots, sl_dist=cfg.stop_pips * self.pip, tp_dist=tp_dist,
                                     digits=self.digits, deviation=cfg.deviation_points, magic=cfg.magic,
                                     comment=comment, check_only=self.dry_run)
        if self.dry_run:
            self._mark(now, key, "dryrun", f"order_check {'accepted' if r.ok else 'rejected'} ({r.retcode} {r.message})",
                       lots=size.lots, sl=r.sl or sl, tp=r.tp or None, ask=tick.ask,
                       risk_amount=round(size.risk_at_size, 2))
            return
        if r.ok:
            ticket = self._find_ticket(r, comment)
            self.journal.update(key, status="open", ticket=ticket, opened=iso(now), entry_price=r.price or tick.ask,
                                sl=r.sl or sl, tp=r.tp or None, volume=r.volume or size.lots)
            self._partial(key, r, size.lots)
            log.info("gotobi %s: bought %.2f lots at %.3f, stop %.3f%s, risking %.2f %s; closes %s", key,
                     r.volume or size.lots, r.price or tick.ask, r.sl or sl, f", target {r.tp:.3f}" if r.tp else "",
                     size.risk_at_size, acct.currency, iso(s.exit))
        else:
            self._failed_send(now, key, r)

    def _partial(self, key: str, r, wanted: float) -> None:
        if r.volume and r.volume < wanted - 1e-9:
            log.warning("gotobi %s: only %.2f of %.2f lots filled; any unfilled rest left at the broker is "
                        "cancelled, and the trade is managed at the filled size", key, r.volume, wanted)

    def _intent(self, now: datetime, key: str, comment: str, size, risk_amount: float, acct, due, spread: float,
                **extra) -> None:
        self.journal.update(key, status="sending", sent_at=iso(now), comment=comment, intended_volume=size.lots,
                            risk_amount=round(size.risk_at_size, 2), risk_target=round(risk_amount, 2),
                            equity_at_entry=round(acct.equity, 2), exit_due=iso(due), size_note=size.note,
                            spread_pips=round(spread, 2), **extra)

    def _failed_send(self, now: datetime, key: str, r) -> None:
        if r.category == "unknown":       # it may have filled: never resend; _resolve_pending watches the broker
            self.journal.update(key, status="unknown", order=r.order or None,
                                note=f"no definite answer ({r.retcode} {r.message}); not resending")
            log.warning("gotobi %s: order outcome unknown (%s %s); not sending again, watching the broker's "
                        "positions and history for a fill", key, r.retcode, r.message)
        elif r.category in ("transient", "market_closed"):     # definitely not executed: free to try again
            self.journal.forget(key, f"not filled ({r.retcode} {r.message})")
            self.say(f"retry-{key}-{r.retcode}", logging.WARNING, "gotobi %s: order not filled (%s %s), retrying",
                     key, r.retcode, r.message)
        else:
            self._mark(now, key, "skipped", f"order rejected: {r.retcode} {r.message}")

    def _algo_off(self, key: str) -> bool:
        term = self.broker.terminal()
        if term is not None and (not term.trade_allowed or term.tradeapi_disabled):
            self.say(f"algo-off-{key}", logging.ERROR, "gotobi %s: trading is switched off in MetaTrader 5 (Algo Trading "
                     "button or the Python API option); waiting for it to be switched on", key)
            return True
        return False

    # ------------------------------------------------------------------ entries: the post-fix short
    def _maybe_short(self, now: datetime, tick, fresh: bool) -> None:
        """Sell at the 09:55 JST fix (step() only calls this when no position is open: never a hedge)."""
        cfg = self.cfg
        if not cfg.post_fix_short:
            return
        s = self.cal.short_active(now)
        if s is None:
            return
        key = s.gotobi.isoformat() + SHORT
        if self.journal.get(key) is not None:
            return
        if not self.dry_run and key not in self._history_checked:
            recovered = self._recover_from_history(now, key, s, side=-1)
            self._history_checked.add(key)
            if recovered:
                return
        if self.journal.halted:
            self._mark(now, key, "skipped", "kill switch is on")
            return
        if now > s.short_late:
            self._mark(now, key, "missed", f"could not sell within {cfg.short_max_late_sec:g} s of the fix")
            return
        if not fresh:
            self.say(f"wait-closed-{key}", logging.INFO, "gotobi %s: no live prices at the fix", key)
            return
        spread = (tick.ask - tick.bid) / self.pip
        if spread > cfg.max_spread_pips:
            self.say(f"wait-spread-{key}", logging.INFO, "gotobi %s: spread %.1f pips is above %.1f at the fix",
                     key, spread, cfg.max_spread_pips)
            return
        if self._algo_off(key):
            return
        if not self.clock_ok():     # the sell has to land within seconds of 09:55:00 JST: an unchecked clock won't do
            self._mark(now, key, "skipped", "the PC clock is not confirmed by time servers, and the fix-second sell "
                                            "needs it (allow UDP port 123)")
            return
        acct = self.broker.account()
        if acct is None:
            raise BrokerUnavailable("account_info failed")
        self._kill_switch(now, acct.balance, acct.equity)
        if self.journal.halted:
            self._mark(now, key, "skipped", "kill switch is on")
            return
        info = self.broker.symbol(self.symbol)
        sl = round(tick.bid + cfg.short_stop_pips * self.pip, self.digits)
        risk_amount = acct.equity * cfg.risk_pct / 100
        loss = self.broker.loss_per_lot(self.symbol, tick.bid, sl, side=-1)
        margin = self.broker.margin_per_lot(self.symbol, tick.bid, side=-1)
        size = size_position(risk_amount, loss, info.volume_min, info.volume_max, info.volume_step, margin,
                             acct.margin_free, cfg.max_margin_use, cfg.below_min_lot)
        if size.lots is None:
            self._mark(now, key, "skipped", size.note)
            return
        sent = self.fresh_now(now)          # the calls above take time on a busy terminal: check the deadline again
        if sent > s.short_late:
            self._mark(now, key, "missed", f"ready to sell only {(sent - s.fix).total_seconds():+.1f} s from the fix, "
                                           f"past the {cfg.short_max_late_sec:g} s limit")
            return
        comment = f"gotobi-s {s.gotobi.isoformat()}"
        if not self.dry_run:     # written BEFORE sending: whatever happens next, this slot is never sent twice
            self._intent(now, key, comment, size, risk_amount, acct, s.short_close, spread, side="short",
                         sent_vs_fix_sec=round((sent - s.fix).total_seconds(), 3))
        r = self.broker.market_order(self.symbol, -1, size.lots, sl_dist=cfg.short_stop_pips * self.pip,
                                     digits=self.digits, deviation=cfg.deviation_points, magic=cfg.magic,
                                     comment=comment, check_only=self.dry_run)
        if self.dry_run:
            self._mark(now, key, "dryrun", f"order_check {'accepted' if r.ok else 'rejected'} ({r.retcode} {r.message})",
                       side="short", lots=size.lots, sl=r.sl or sl, bid=tick.bid,
                       risk_amount=round(size.risk_at_size, 2))
            return
        if r.ok:
            ticket = self._find_ticket(r, comment)
            done = self.fresh_now(now)
            self.journal.update(key, status="open", side="short", ticket=ticket, opened=iso(sent),
                                answered_vs_fix_sec=round((done - s.fix).total_seconds(), 3),
                                entry_price=r.price or tick.bid, sl=r.sl or sl, volume=r.volume or size.lots)
            self._partial(key, r, size.lots)
            log.info("gotobi %s: sold %.2f lots at %.3f (sent %+.2f s from the fix, confirmed %+.2f s), stop %.3f; "
                     "buys back %s", key, r.volume or size.lots, r.price or tick.bid, (sent - s.fix).total_seconds(),
                     (done - s.fix).total_seconds(), r.sl or sl, iso(s.short_close))
            if (done - s.fix).total_seconds() > cfg.short_max_late_sec:
                log.warning("gotobi %s: the terminal took until %+.1f s after the fix to confirm the sell; its real "
                            "fill time is recorded when the trade closes (filled_vs_fix_sec)", key,
                            (done - s.fix).total_seconds())
        else:
            self._failed_send(now, key, r)

    def _recover_from_history(self, now: datetime, key: str, s, side: int = +1) -> bool:
        """Second guard against trading twice: if the broker's history already holds this bot's buy (or, for the
        short, sell) inside this trade's window (the journal was lost or is stale), record that trade instead."""
        m = self.broker.mt5
        since = s.entry - timedelta(minutes=10) if side > 0 else s.fix - timedelta(minutes=2)
        kind = m.DEAL_TYPE_BUY if side > 0 else m.DEAL_TYPE_SELL
        deals = self.broker.deals_between(since - timedelta(days=2), now + timedelta(days=2))
        mine = [d for d in deals if d.entry == m.DEAL_ENTRY_IN and d.magic == self.cfg.magic and d.symbol == self.symbol
                and d.type == kind and self.tick_time(d) >= since]
        if not mine:
            return False
        first = min(mine, key=lambda d: d.time_msc)
        log.error("gotobi %s: the broker already shows a %s at %s (position %s) that the journal does not know; "
                  "recording it instead of trading again", key, "buy" if side > 0 else "sell",
                  iso(self.tick_time(first)), first.position_id)
        known = self.journal.get(key) or {}        # an order intent of ours keeps its risk, so R still counts
        self.journal.update(key, status="open", ticket=first.position_id, recovered=True,
                            opened=iso(self.tick_time(first)), entry_price=first.price, volume=first.volume,
                            exit_due=iso(s.exit if side > 0 else s.short_close), risk_amount=known.get("risk_amount"),
                            **({} if side > 0 else {"side": "short"}))
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
            line(cfg.allow_live and self.allow_live_flag,
                 "real-money account: traded only with allow_live = true in the config AND the --allow-live flag "
                 f"(config: {'yes' if cfg.allow_live else 'no'}, flag: {'yes' if self.allow_live_flag else 'no'})")
        if self.journal.recovered_from:
            line(False, "state.json could not be read: the journal was rebuilt from "
                        f"{'its backup' if self.journal.recovered_from == 'backup' else 'scratch'} (see bot.log)",
                 blocking=False)
        line(term.trade_allowed, "Algo Trading button is " + ("on" if term.trade_allowed else "OFF: switch it on"))
        line(not term.tradeapi_disabled, "Python API trading is " + (
            "allowed" if not term.tradeapi_disabled else
            "DISABLED: untick Tools > Options > Expert Advisors > 'Disable algorithmic trading via external Python API'"))
        info = self.broker.symbol(self.symbol)
        line(info.trade_mode == m.SYMBOL_TRADE_MODE_FULL, f"symbol {self.symbol}: lots {info.volume_min}-{info.volume_max} "
             f"step {info.volume_step}, contract {info.trade_contract_size:,.0f}, digits {info.digits}")
        others = [p for p in self.broker.symbol_positions(self.symbol) if p.magic != cfg.magic]
        if others:
            line(False, f"{len(others)} open {self.symbol} position(s) were not opened by this bot: it enters nothing "
                        "while any is open", blocking=False)
        live = self.broker.orders(self.symbol, cfg.magic)
        if live:
            line(False, f"{len(live)} live order(s) of this bot are queued at the broker: it cancels them and opens "
                        "nothing until they are gone", blocking=False)
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
        if self.clock_note:
            checked = self.clock_ok()
            line(checked or not cfg.post_fix_short, self.clock_note + (
                "" if checked or not cfg.post_fix_short else
                ": the post-fix short needs a checked clock (allow UDP port 123, or set post_fix_short = false)"))
        if tick is not None:
            sl = round(tick.ask - cfg.stop_pips * self.pip, self.digits)
            tp = round(tick.ask + cfg.take_profit_pips * self.pip, self.digits) if cfg.take_profit_pips else 0.0
            risk = acct.equity * cfg.risk_pct / 100
            loss = self.broker.loss_per_lot(self.symbol, tick.ask, sl)
            margin = self.broker.margin_per_lot(self.symbol, tick.ask)
            size = size_position(risk, loss, info.volume_min, info.volume_max, info.volume_step, margin,
                                 acct.margin_free, cfg.max_margin_use, cfg.below_min_lot)
            line(size.lots is not None, f"trade size at {cfg.risk_pct}% risk: " + (
                f"{size.lots} lots, losing {size.risk_at_size:,.2f} {acct.currency} if the {cfg.stop_pips:g}-pip stop "
                f"is hit" + (f", take-profit +{cfg.take_profit_pips:g} pips" if tp else ", no take-profit")
                + (f" ({size.note})" if size.note != "ok" else "") if size.lots else size.note))
            if size.lots and live:
                r = self.broker.market_order(self.symbol, +1, size.lots, sl=sl, tp=tp, deviation=cfg.deviation_points,
                                             magic=cfg.magic, comment="gotobi preflight", check_only=True)
                line(r.ok, f"broker order check of that buy with its stop and target: "
                           f"{'accepted' if r.ok else 'REJECTED'} ({r.retcode} {r.message})")
                if cfg.post_fix_short:
                    ssl = round(tick.bid + cfg.short_stop_pips * self.pip, self.digits)
                    r = self.broker.market_order(self.symbol, -1, size.lots, sl=ssl, deviation=cfg.deviation_points,
                                                 magic=cfg.magic, comment="gotobi preflight", check_only=True)
                    line(r.ok, f"broker order check of the post-fix sell with its stop: "
                               f"{'accepted' if r.ok else 'REJECTED'} ({r.retcode} {r.message})")
        s = self.cal.next_slot(now)
        local = lambda t: t.astimezone().strftime("%a %d %b %H:%M")    # noqa: E731
        line(True, f"next trade: gotobi {s.gotobi}: buy {iso(s.entry)} (your PC: {local(s.entry)}), "
                   f"close {iso(s.exit)} (your PC: {local(s.exit)})")
        if cfg.post_fix_short:
            line(True, f"then the post-fix short: sell {s.short_open.isoformat(timespec='seconds')} (09:55 JST "
                       f"{cfg.short_send_sec:+g} s), buy back {iso(s.short_close)} (your PC: {local(s.short_close)})")
        out.append("READY: start run_bot.bat" if ready else "NOT READY: fix the lines marked !!")
        return ready, out

    # ------------------------------------------------------------------ status
    def status(self, now: datetime) -> str:
        s = self.cal.next_slot(now)
        lines = [f"symbol {self.symbol}; next gotobi {s.gotobi}: buy {iso(s.entry)}, close {iso(s.exit)}"
                 + self._short_text(s)]
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
