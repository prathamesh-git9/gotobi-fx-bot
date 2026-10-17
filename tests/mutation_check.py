"""Mutation check: plant known bugs in a scratch copy of the bot and confirm the fast test suite catches each one.

  python tests/mutation_check.py

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
     "        if self.journal.get(key) is not None:\n            return\n        if not self.dry_run and key not in",
     "        if not self.dry_run and key not in"),
    ("broker-history guard disabled", "engine.py",
     "            if recovered:\n                return", "            if False:\n                return"),
    ("positions_get error treated as 'no positions'", "broker.py",
     '        if ps is None:   # an error, NOT "no positions": treating it as empty could open a duplicate trade\n'
     '            raise BrokerUnavailable(f"positions_get failed: {self.mt5.last_error()}")',
     "        if ps is None:\n            return []"),
    ("exit one minute late", "engine.py",
     "            if now < due:\n                continue", "            if now < due + timedelta(minutes=1):\n                continue"),
    ("Japanese holidays ignored", "gotobi_calendar.py",
     "        if self.move_holidays and d in self._jp:", "        if False and d in self._jp:"),
    ("lots rounded to nearest instead of down", "sizing.py",
     "    return round(math.floor(x / step + 1e-9) * step, 8)", "    return round(round(x / step) * step, 8)"),
    ("stop 10x too tight", "engine.py",
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
     "if spread > cfg.max_spread_pips:", "if spread > cfg.max_spread_pips * 100:"),
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
]


def main() -> int:
    survived = []
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        shutil.copytree(ROOT / "bot", work / "bot", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(ROOT / "tests", work / "tests", ignore=shutil.ignore_patterns("__pycache__"))
        (work / "src").mkdir()
        shutil.copy(ROOT / "src" / "gotobi.py", work / "src" / "gotobi.py")
        shutil.copy(ROOT / "pytest.ini", work / "pytest.ini")
        for name, file, old, new in MUTATIONS:
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
    print(f"\n{len(MUTATIONS) - len(survived)}/{len(MUTATIONS)} planted bugs caught")
    return 1 if survived else 0


if __name__ == "__main__":
    raise SystemExit(main())
