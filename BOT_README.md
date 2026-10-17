# Gotobi bot

Buys USD/JPY at 15:55 UTC the day before each gotobi day (5th/10th/15th/20th/25th/30th; moved off weekends and
Japanese holidays), with a 55-pip stop held on the broker's server, and sells at 00:54 UTC, one minute before the
09:55 Tokyo fix. It drives a MetaTrader 5 terminal through MetaQuotes' official `MetaTrader5` Python package.

**It refuses real-money accounts** unless `allow_live = true` is in the config **and** `--allow-live` is passed.

## Setup (demo first)
1. Install MetaTrader 5 from your broker and log in to a **demo** account. Turn on **Algo Trading** (toolbar).
2. `pip install -r requirements-bot.txt` (Windows only for `MetaTrader5`).
3. `copy bot_config.example.toml bot_config.toml` and set `risk_pct` and `symbols`.
4. `python -m bot.main --config bot_config.toml --preflight`: checks the terminal (Algo Trading, Python API),
   account, symbol, spread, broker clock, trade size and a broker-side check of the planned order, then prints
   READY or the exact problem. It never trades. `--status` shows the next trade and the journal.
5. `python -m bot.main --config bot_config.toml --dry-run`: runs the schedule but only *checks* orders.
6. `run_bot.bat` (restarts the bot if it stops). For start at log-on, add it to Windows Task Scheduler.

The PC must be on and online across every trade window (about 6 nights a month, 15:55 to 00:55 UTC).
The bot stops Windows from sleeping while it runs; Windows Update restarts and power cuts still stop it.
If the bot is down at 00:54 the server-side stop still protects the trade, and the bot closes it the moment
it is back.

## What it writes (`bot_state/`)
- `bot.log`: everything, in UTC.
- `state.json`: one record per gotobi day: open / closed / skipped / missed / dryrun, with prices, P&L and R.
- `events.jsonl`: every change, for audit.

## Safety behaviour
- Never trades a day twice: journal + open positions + the broker's own deal history.
- Positions-list errors abort the poll; they are never read as "no positions".
- Waits for live prices; after a weekend reopen or a feed outage of 30+ minutes it waits 15 minutes.
- Waits while the spread is above 5 pips; gives up 2 hours after schedule, or 30 minutes before the exit.
- Rejected orders are retried if temporary; a fatal rejection skips that day.
- Kill switch: no new trades after the last 60 trades lose more than 6R, or after a 50% drawdown.
- One instance only (file lock).

## Tests
- `python -m pytest -m "not slow"`: 88 unit and scenario tests on the MT5 simulator (5 s).
- `python -m pytest`: adds the 2016-2026 replays (4 min).
- `python tests/mutation_check.py`: plants 23 known bugs and checks each is caught.
- `python -m bot.replay --start 2026-01-01 --end 2026-10-16 --balance 1000 --risk 10`: the production code on
  real Exness history.

Verified: on 2016-2026 Exness ticks the bot reproduces the research backtest trade for trade (757/757 and
755/755: same entry/exit minutes, prices and exit reasons); 3,998 random crash-restarts change no trade;
forced outages never duplicate or strand a trade; with all future prices deleted at 59 decision moments
every decision is identical (no look-ahead); all 23 planted bugs are caught. Not yet verified: a real
MT5 terminal. That is what the demo period is for.

## Running unattended (PC always on)
- Power: never sleep or hibernate on mains power; laptop lid set to "do nothing". Wired internet if possible.
- Windows Update active hours 15:00-03:00 (covers 15:55-00:55 UTC in Irish summer and winter time), so it does
  not restart the PC during a trade.
- In MT5: Algo Trading button ON, and Tools > Options > Expert Advisors > "Disable algorithmic trading via
  external Python API" UNticked. If either is off the bot waits and logs an error; it trades once switched on.
- Set `terminal_path` in the config so the bot can start MT5 itself, and start `run_bot.bat` at log-on
  (Task Scheduler). After a power cut the PC must boot and log in for that to happen.
- Keep Windows time sync on: exits are timed by the PC clock.
- Once a year: `pip install -U holidays` (new Japanese holidays).

## Using another broker / account
- Any MT5 broker works: put its USD/JPY symbol name first in `symbols` (e.g. "USDJPY", "USDJPY.pro").
- The server clock offset is measured automatically (`auto_server_offset`); filling mode and lot rules are
  read from the broker.
- The backtest costs are Exness's (about 1.5-2.4 pips per trade in spread). Check the broker's USD/JPY spread
  (+ commission) at 15:55 and 00:54 UTC: much above 2 pips per round trip eats most of the edge.
- Swap-free (Islamic) accounts: check for a daily holding fee. Every trade is held over the 17:00 New York
  rollover.
- Demo on that broker first (`--dry-run`, then demo trading).
