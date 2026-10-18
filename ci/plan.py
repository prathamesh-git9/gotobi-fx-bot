"""When the hosted bot (.github/workflows/host.yml) should run, and until when.

The bot only has work around each trade. Stops and take-profits sit at the broker, so in between it can be off:
  - the buy at entry_utc (15:55 UTC) the day before a gotobi day; it may wait up to max_entry_delay_min for a
    usable price;
  - the close at 00:54 UTC, then the post-fix short until 01:25 UTC.
A scheduled start up to LEAD before a window still covers it (GitHub's timers start late, never early).

  python ci/plan.py [--mode auto|preflight|smoke] [--now 2026-10-19T14:13Z] [--config bot_config.example.toml]

prints run=true|false, until=<UTC time> and why=<text>, for $GITHUB_OUTPUT.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot.config import load_config  # noqa: E402
from bot.gotobi_calendar import GotobiCalendar  # noqa: E402
from bot.main import parse_until  # noqa: E402

UTC = timezone.utc
LEAD = timedelta(hours=4)          # a run may start this long before its window
TAIL = timedelta(minutes=5)        # the bot keeps going this long after the last action of a window


def windows(cfg, now: datetime) -> list[tuple[datetime, datetime, str]]:
    """(start, end, what) of the trade windows of the gotobi days around now."""
    cal = GotobiCalendar.from_config(cfg)
    out = []
    for k in range(-1, 3):
        d = (now + timedelta(days=k)).date()
        if not cal.is_trade_day(d):
            continue
        s = cal.slot(d)
        out.append((s.entry - timedelta(minutes=2), s.entry + timedelta(minutes=cfg.max_entry_delay_min) + TAIL,
                    f"buy for gotobi day {d}"))
        last = s.short_close if cfg.post_fix_short else s.exit
        out.append((s.exit - TAIL, last + TAIL,
                    f"close{' and post-fix short' if cfg.post_fix_short else ''} for gotobi day {d}"))
    return sorted(out)


def plan(cfg, now: datetime, mode: str = "auto") -> tuple[bool, datetime, str]:
    if mode == "preflight":
        return True, now, "preflight only: check everything, trade nothing"
    if mode == "smoke":
        return True, now + timedelta(minutes=15), "smoke test: run the bot loop for about 10 minutes"
    for start, end, what in windows(cfg, now):
        if start - LEAD <= now < end - TAIL:
            return True, end, what
    return False, now, "no trade window in the next 4 hours"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mode", default="auto", choices=["auto", "preflight", "smoke"])
    ap.add_argument("--now", help="pretend it is this UTC time (for checking the schedule)")
    ap.add_argument("--config", default=str(ROOT / "bot_config.example.toml"))
    args = ap.parse_args(argv)
    now = parse_until(args.now) if args.now else datetime.now(UTC)
    run, until, why = plan(load_config(args.config), now, args.mode or "auto")
    print(f"run={'true' if run else 'false'}")
    print(f"until={until.astimezone(UTC):%Y-%m-%dT%H:%M:%SZ}")
    print(f"why={why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
