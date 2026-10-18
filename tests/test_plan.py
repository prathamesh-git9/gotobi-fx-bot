"""The hosted bot's schedule (ci/plan.py with the cron times in .github/workflows/host.yml): every trade window of
2026-2028 must be covered by the first scheduled start of its day, and by the backup start if the first is
dropped, each running until the window's end."""
from __future__ import annotations

import os
import re
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

ROOT = Path(os.environ.get("GOTOBI_ROOT", Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(ROOT))

from bot.config import load_config  # noqa: E402
from bot.gotobi_calendar import GotobiCalendar  # noqa: E402
from ci.plan import plan, windows  # noqa: E402

UTC = timezone.utc
CFG = load_config(str(ROOT / "bot_config.example.toml"))


def cron_times() -> list[time]:
    text = (ROOT / ".github" / "workflows" / "host.yml").read_text(encoding="utf-8")
    found = re.findall(r'cron:\s*"(\d+) (\d+) \* \* \*"', text)
    assert found, "no daily cron lines in host.yml"
    return sorted(time(int(h), int(m)) for m, h in found)


def test_october_2026():
    run, until, why = plan(CFG, datetime(2026, 10, 19, 14, 13, tzinfo=UTC))
    assert run and until == datetime(2026, 10, 19, 18, 0, tzinfo=UTC) and "2026-10-20" in why
    run, until, why = plan(CFG, datetime(2026, 10, 19, 22, 43, tzinfo=UTC))
    assert run and until == datetime(2026, 10, 20, 1, 30, tzinfo=UTC) and "short" in why
    for quiet in (datetime(2026, 10, 18, 14, 13, tzinfo=UTC), datetime(2026, 10, 18, 22, 43, tzinfo=UTC),
                  datetime(2026, 10, 19, 9, 0, tzinfo=UTC), datetime(2026, 10, 20, 14, 13, tzinfo=UTC)):
        assert not plan(CFG, quiet)[0], quiet


def test_every_window_is_covered_by_the_schedule_and_its_backup():
    cal = GotobiCalendar.from_config(CFG)
    starts = cron_times()
    checked = 0
    for d in cal.trade_days(date(2026, 1, 1), date(2028, 12, 31)):
        for start, end, what in windows(CFG, datetime.combine(d, time(0, 55), UTC)):
            if str(d) not in what:
                continue
            # the scheduled starts in the LEAD hours before the window, each of them possibly an hour late
            runs = [datetime.combine(start.date() + timedelta(days=k), t, UTC) for k in (-1, 0) for t in starts]
            runs = [r for r in runs if start - timedelta(hours=4) <= r <= start]
            assert len(runs) >= 2, f"{what}: only {runs} start before it"
            for r in runs:
                for late in (timedelta(0), timedelta(hours=1)):
                    ok, until, _ = plan(CFG, r + late)
                    assert ok and until == end, f"{what}: a start at {r + late} gives {ok}, {until}"
            checked += 1
    assert checked > 400


def test_preflight_and_smoke_modes_always_run():
    now = datetime(2026, 10, 18, 10, 0, tzinfo=UTC)
    assert plan(CFG, now, "preflight")[0]
    run, until, _ = plan(CFG, now, "smoke")
    assert run and until == now + timedelta(minutes=15)
