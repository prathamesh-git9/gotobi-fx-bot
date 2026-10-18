"""Mutation check: plant known bugs in a scratch copy of the bot and confirm the fast test suite catches each one.

  python tests/mutation_check.py              all of them
  python tests/mutation_check.py duplicate    only those whose name contains "duplicate"

A 'survived' mutation means no test noticed that bug: a hole in the tests (or a harmless change).
The real files are never modified.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MUTATIONS = [
    ("no duplicate-entry guard", "engine.py",
     "        if self.journal.get(key) is not None:\n            return\n"
     "        if not self.dry_run and key not in self._history_checked:     # once per window",
     "        if not self.dry_run and key not in self._history_checked:     # once per window"),
    ("broker-history guard disabled", "engine.py",
     "            recovered = self._recover_from_history(now, key, s)\n            self._history_checked.add(key)\n"
     "            if recovered:\n                return",
     "            recovered = self._recover_from_history(now, key, s)\n            self._history_checked.add(key)\n"
     "            if False:\n                return"),
    ("positions_get error treated as 'no positions'", "broker.py",
     '        raise BrokerUnavailable(f"{what} failed: {err}")', "        return []"),
    ("MT5's empty-list reply (None + success) taken as an error", "broker.py",
     "        if err and err[0] == 1:\n            return []\n        raise BrokerUnavailable",
     "        if False:\n            return []\n        raise BrokerUnavailable"),
    ("exit one minute late", "engine.py",
     "            if now < due:\n                continue", "            if now < due + timedelta(minutes=1):\n                continue"),
    ("Japanese holidays ignored", "gotobi_calendar.py",
     "        if self.move_holidays and d in self._jp:", "        if False and d in self._jp:"),
    ("lots rounded to nearest instead of down", "sizing.py",
     "    return round(math.floor(x / step + 1e-9) * step, 8)", "    return round(round(x / step) * step, 8)"),
    ("stop 10x too tight", "engine.py",
     "sl_dist=cfg.stop_pips * self.pip, tp_dist=tp_dist,", "sl_dist=cfg.stop_pips * self.pip * 0.1, tp_dist=tp_dist,"),
    ("sized for a stop 10x too tight", "engine.py",
     "        sl = round(tick.ask - cfg.stop_pips * self.pip, self.digits)\n        risk_amount = ",
     "        sl = round(tick.ask - cfg.stop_pips * self.pip * 0.1, self.digits)\n        risk_amount = "),
    ("live-account lock needs only one key", "engine.py",
     "if not demo and not inspect_only and not (self.cfg.allow_live and self.allow_live_flag):",
     "if not demo and not inspect_only and not (self.cfg.allow_live or self.allow_live_flag):"),
    ("no wait after the reopen", "engine.py",
     "        if recent:\n            anchor = max(anchor, ro + wait)", "        if False:\n            anchor = max(anchor, ro + wait)"),
    ("no filling-mode fallback", "broker.py",
     "            if rc == m.TRADE_RETCODE_INVALID_FILL:\n                last = r\n                continue",
     '            if rc == m.TRADE_RETCODE_INVALID_FILL:\n                return OrderResult(False, "fatal", rc)'),
    ("kill switch off by one trade", "engine.py",
     "if len(rs) >= w and sum(rs[-w:]) < self.cfg.kill_sum_r:", "if len(rs) > w and sum(rs[-w:]) < self.cfg.kill_sum_r:"),
    ("stale prices treated as live", "engine.py",
     "fresh = age <= self.cfg.stale_tick_sec", "fresh = True"),
    ("journal not saved (crash loses state)", "journal.py",
     '        self.save()\n        self.event({"slot": key, **fields})', '        self.event({"slot": key, **fields})'),
    ("trade window includes the exit minute", "gotobi_calendar.py",
     "                if s.entry <= now < s.exit:", "                if s.entry <= now <= s.exit:"),
    ("spread limit ignored", "engine.py",
     'if spread > cfg.max_spread_pips:\n            self.say(f"wait-spread-{key}", logging.INFO, "gotobi %s: spread %.1f pips '
     'is above %.1f, waiting"',
     'if spread > cfg.max_spread_pips * 100:\n            self.say(f"wait-spread-{key}", logging.INFO, "gotobi %s: spread '
     '%.1f pips is above %.1f, waiting"'),
    ("may open right before the exit", "engine.py",
     "if now >= s.exit - timedelta(minutes=cfg.min_hold_min):", "if now >= s.exit:"),
    ("feed outage stretches the weekday delay limit", "engine.py",
     "start = anchor if s.entry.weekday() >= 5 else s.entry", "start = anchor"),
    ("stop-outs labelled as time exits", "engine.py",
     "        if last.reason == m.DEAL_REASON_SL:", "        if last.reason == m.DEAL_REASON_EXPERT:"),
    ("unknown positions not adopted", "engine.py", "                self._adopt(now, p)", "                pass"),
    ("broker clock offset never measured", "engine.py",
     "            if abs(lag - guess * 3600) < 120 and abs(guess) <= 14 and guess != self.offset_h:",
     "            if False:"),
    ("offset measured across a long poll gap", "engine.py",
     "close_polls = self._prev_poll is not None and (now - self._prev_poll).total_seconds() <= 120",
     "close_polls = True"),
    ("Algo Trading switch ignored", "engine.py",
     '        if term is not None and (not term.trade_allowed or term.tradeapi_disabled):\n            self.say(f"algo-off',
     '        if False:\n            self.say(f"algo-off'),
    ("Christmas not skipped", "gotobi_calendar.py",
     '        return f"{d:%m-%d}" not in self.fx_closed', "        return True"),
    # --- the take-profit
    ("take-profit not sent with the buy", "engine.py",
     "sl_dist=cfg.stop_pips * self.pip, tp_dist=tp_dist,", "sl_dist=cfg.stop_pips * self.pip, tp_dist=0.0,"),
    ("take-profit exits labelled as something else", "engine.py",
     "        elif last.reason == m.DEAL_REASON_TP:", "        elif last.reason == -999:"),
    ("take-profit 10x too far", "engine.py",
     "        tp_dist = cfg.take_profit_pips * self.pip if cfg.take_profit_pips else 0.0",
     "        tp_dist = cfg.take_profit_pips * self.pip * 10 if cfg.take_profit_pips else 0.0"),
    ("stop placed from the stale sizing quote", "engine.py",
     "sl_dist=cfg.stop_pips * self.pip, tp_dist=tp_dist,", "sl=sl, tp_dist=tp_dist,"),
    # --- the post-fix short
    ("short sends a buy", "engine.py",
     "        r = self.broker.market_order(self.symbol, -1, size.lots, sl_dist=cfg.short_stop_pips * self.pip,",
     "        r = self.broker.market_order(self.symbol, +1, size.lots, sl_dist=cfg.short_stop_pips * self.pip,"),
    ("short sold however late", "engine.py", "        if now > s.short_late:", "        if False:"),
    ("short sold while the long is still open (hedge)", "engine.py",
     "        tick, fresh = self._prices(now)\n        if positions:\n            self._manage(now, positions)",
     "        tick, fresh = self._prices(now)\n        self._maybe_short(now, tick, fresh)\n        if positions:\n"
     "            self._manage(now, positions)"),
    ("short closed with a sell", "engine.py",
     "            side = -1 if p.type == m.POSITION_TYPE_BUY else +1", "            side = -1"),
    ("short sold 3 s late", "gotobi_calendar.py",
     "fix - self.exit_before, fix + self.short_send,",
     "fix - self.exit_before, fix + self.short_send + timedelta(seconds=3),"),
    ("short history guard disabled", "engine.py",
     "            recovered = self._recover_from_history(now, key, s, side=-1)", "            recovered = False"),
    ("short stop 10x too tight", "engine.py",
     "sl_dist=cfg.short_stop_pips * self.pip,", "sl_dist=cfg.short_stop_pips * self.pip * 0.1,"),
    ("kill switch R rule counts the shorts", "engine.py",
     ' and rec.get("side") != "short"\n              and (since is None', "\n              and (since is None"),
    ("unknown short adopted as a long", "engine.py",
     "        short = p.type == self.broker.mt5.POSITION_TYPE_SELL\n        found = re.search",
     "        short = False\n        found = re.search"),
    # --- the clock
    ("clock correction applied backwards", "clock.py",
     "        return datetime.fromtimestamp(wall + self.offset, timezone.utc)",
     "        return datetime.fromtimestamp(wall - self.offset, timezone.utc)"),
    ("clock trusts time servers that disagree", "clock.py",
     "        if len(offsets) >= 2 and max(offsets) - min(offsets) < 0.25:", "        if len(offsets) >= 1:"),
    # --- found by the independent review (codex_audit/bot_review) and the 24/7 soak test
    ("terminal switched to another account not noticed", "engine.py",
     "        if self.account_id is not None and (acct.login, acct.server) != self.account_id:", "        if False:"),
    ("terminal switched to a real account not refused", "engine.py",
     "        if acct.trade_mode != self.broker.mt5.ACCOUNT_TRADE_MODE_DEMO and not (",
     "        if False and not ("),
    ("someone else's position ignored", "engine.py",
     "        if everything:          # someone else's trade", "        if False:          # someone else's trade"),
    ("an order with no answer taken as definitely rejected (resent)", "broker.py",
     '                return OrderResult(False, "transient" if check_only else "unknown", None,',
     '                return OrderResult(False, "transient", None,'),
    ("order not written to the journal before sending", "engine.py",
     "        if not self.dry_run:     # written BEFORE sending: whatever happens next, this slot is never sent twice\n"
     "            self._intent(now, key, comment, size, risk_amount, acct, s.exit, spread)",
     "        if False:\n            self._intent(now, key, comment, size, risk_amount, acct, s.exit, spread)"),
    ("an unresolved order does not block new trades", "engine.py",
     "        if live or self.journal.pending() or any(k in self._unresolved for k, _ in self.journal.open_slots()):",
     "        if live:"),
    ("a live queued order does not block new trades", "engine.py",
     "        if live or self.journal.pending() or any(k in self._unresolved for k, _ in self.journal.open_slots()):",
     "        if self.journal.pending() or any(k in self._unresolved for k, _ in self.journal.open_slots()):"),
    ("leftover live orders not cancelled", "engine.py",
     "            r = self.broker.cancel(o.ticket)\n            if r.ok:", "            continue\n            if r.ok:"),
    ("a pending trade released while its order is still live", "engine.py",
     "            if any(o.comment == rec.get(\"comment\") or (rec.get(\"order\") and o.ticket == rec[\"order\"]) for o in live):\n"
     "                continue",
     "            if False:\n                continue"),
    ("a closed trade written off when its closing deal is missing", "engine.py",
     "            if n >= 12:\n                self._unresolved[key] = n",
     "            if n >= 12:\n                self.journal.update(key, status=\"closed\", reason=\"unknown\", pnl=None, r=None,\n"
     "                                    closed=iso(now))\n                return"),
    ("a recovered fill loses its risk (R not counted)", "engine.py",
     'risk_amount=known.get("risk_amount"),', "risk_amount=None,"),
    ("unchecked clock trusted before enough price samples", "engine.py",
     "        if not self.clock_ok() and len(self._lags) < 5:", "        if False:"),
    ("kill switch kept only in state.json (no HALTED file)", "journal.py",
     "        self._write(self.marker, reason)        # first: even if state.json is lost later, the halt stays",
     "        pass"),
    ("--clear-halt keeps the old losing R window", "journal.py",
     '        self.r_reset_at = datetime.now(timezone.utc).isoformat(timespec="seconds")', "        pass"),
    ("nested state fields not checked", "journal.py",
     '        if rec["status"] == "open":                     # what the engine reads',
     '        if False:                     # what the engine reads'),
    ("short sent on a clock no time server confirmed", "engine.py",
     "        if not self.clock_ok():     # the sell has to land", "        if False:     # the sell has to land"),
    ("PC clock far off the broker's prices not noticed", "engine.py",
     "        return gap if abs(gap) > 30 else None", "        return None"),
    ("all state lost, yet new trades still open", "engine.py",
     '            if self.journal.recovered_from == "nothing" and not self.journal.halted:', "            if False:"),
    ("backup not refreshed on save (can lose the kill switch)", "journal.py",
     "            self._write(self.backup, payload)          # the backup is never older than the last save",
     "            pass"),
    ("valid JSON of the wrong shape accepted as a journal", "journal.py",
     "            check_state(data)\n        except (ValueError, UnicodeDecodeError) as e:",
     "            pass\n        except (ValueError, UnicodeDecodeError) as e:"),
    ("an order only placed taken as a fill", "broker.py",
     "        self.done = {m.TRADE_RETCODE_DONE, m.TRADE_RETCODE_DONE_PARTIAL}",
     "        self.done = {m.TRADE_RETCODE_DONE, m.TRADE_RETCODE_DONE_PARTIAL, m.TRADE_RETCODE_PLACED}"),
    ("short deadline judged on the poll's stale time", "engine.py",
     "        sent = self.fresh_now(now)", "        sent = now"),
    ("drawdown not checked before an entry", "engine.py",
     '        self._kill_switch(now, acct.balance, acct.equity)\n        if self.journal.halted:\n'
     '            self._mark(now, key, "skipped", "kill switch is on")\n            return\n'
     '        info = self.broker.symbol(self.symbol)\n        sl = round(tick.ask',
     "        info = self.broker.symbol(self.symbol)\n        sl = round(tick.ask"),
    ("exactly 50% drawdown allowed", "engine.py",
     "level <= self.journal.peak_balance * (1 - self.cfg.kill_max_drawdown)",
     "level < self.journal.peak_balance * (1 - self.cfg.kill_max_drawdown)"),
    ("a damaged state file stops the bot", "journal.py",
     "        except (ValueError, UnicodeDecodeError) as e:\n            bad =",
     "        except ZeroDivisionError as e:\n            bad ="),
    ("main loop dies on an error outside the trading step", "main.py",
     "        return min(60.0, max(0.001, float(engine.poll_interval(now_fn()))))\n    except Exception:",
     "        return min(60.0, max(0.001, float(engine.poll_interval(now_fn()))))\n    except ZeroDivisionError:"),
    ("Windows clock reset not followed", "clock.py", "        if abs(jump) > JUMP_SEC:", "        if False:"),
    ("unchecked PC clock trusted to measure the broker offset", "engine.py",
     "                self._measure_offset(now, tick, apply=self.clock_ok())",
     "                self._measure_offset(now, tick, apply=True)"),
]


def main(only: str = "") -> int:
    mutations = [m for m in MUTATIONS if only.lower() in m[0].lower()]
    survived = []
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        shutil.copytree(ROOT / "bot", work / "bot", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / "tests", work / "tests", ignore=shutil.ignore_patterns("__pycache__"))
        (work / "src").mkdir()
        shutil.copy(ROOT / "src" / "gotobi.py", work / "src" / "gotobi.py")
        shutil.copy(ROOT / "pytest.ini", work / "pytest.ini")
        for name, file, old, new in mutations:
            path = work / "bot" / file
            original = path.read_text(encoding="utf-8")
            if original.count(old) != 1:
                print(f"  ??  {name}: pattern not found exactly once in {file}")
                survived.append(name)
                continue
            path.write_text(original.replace(old, new), encoding="utf-8")
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-m", "not slow", "-p", "no:cacheprovider"],
                               cwd=work, capture_output=True, text=True)
            path.write_text(original, encoding="utf-8")
            caught = r.returncode != 0
            failing = next((ln.split("::")[1].split(" ")[0] for ln in r.stdout.splitlines() if ln.startswith("FAILED")), "")
            print(f"  {'caught  ' if caught else 'SURVIVED'}  {name}" + (f"   <- {failing}" if failing else ""))
            if not caught:
                survived.append(name)
    print(f"\n{len(mutations) - len(survived)}/{len(mutations)} planted bugs caught")
    return 1 if survived else 0


if __name__ == "__main__":
    raise SystemExit(main(" ".join(sys.argv[1:])))
