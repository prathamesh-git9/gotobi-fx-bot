# Independent review: is this MT5 trading bot really ready to run 24/7?

You are an independent reviewer with no stake in the answer. The owner will leave a Windows 11 PC on 24/7 running
this Python bot against a MetaTrader 5 terminal (Exness demo account first, small EUR account). They want a
BRUTAL, unbiased verdict on whether the bot:
1. implements the trading rules below correctly;
2. will keep running 24/7 without crashing or getting stuck;
3. handles real-world failures safely: never a duplicate trade, never long and short at once, never a position
   left open past its exit, never trading on a real-money account by accident.

Find the bugs. Do not assume it works because it has tests or because comments or docs say it was verified:
treat every claim in code comments, BOT_README.md and test names as unverified until you check it yourself.

## Ground rules
- Read whatever you need under `bot/`, `tests/`, `run_bot.bat`, `bot_config.example.toml`,
  `requirements-bot.txt` and `BOT_README.md`.
- Ignore README.md, `results/`, `src/` and `codex_audit/` outside your own folder: they are research, not the
  bot.
- Do NOT modify anything outside `codex_audit/bot_review/`. Write your own tests and scripts there. Do not edit
  `bot/` or `tests/`; report the fixes instead. Do not commit to git. Do not install packages globally.
- This laptop has limited free RAM (about 5 GB, shared with other apps):
  - run at most ONE heavy process at a time;
  - no multiprocessing or parallel pytest;
  - keep peak memory under about 3 GB.
  The slow replay tests (`python -m pytest -m slow`) take about 15 minutes. Run them only if you need them, and
  never alongside another heavy job.
- `python` has pandas, numpy, pyarrow, holidays, pytest and the official MetaTrader5 package (5.0.6231)
  installed.
  - There is NO MetaTrader 5 terminal on this PC, so real terminal calls cannot be made.
  - `bot/fake_mt5.py` is the simulator the tests use; judge whether it is faithful enough.
  - Real Exness minute bid/ask data is in `data/USDJPYm_2016_m1.parquet`, `data/USDJPYm_m1.parquet` and
    `data/USDJPYm_2026_10_m1.parquet` (naive-UTC minute index; columns bopen/bhigh/blow/bclose,
    aopen/ahigh/alow/aclose).

## The rules the bot must implement (all times UTC; 1 pip = 0.01 JPY)
Gotobi days:
- The 5th, 10th, 15th, 20th, 25th and 30th of each month (February has no 30th; there is no 31st rule).
- A day that is not a business day moves to the business day before (repeat until it is one). Not a business
  day = Saturday, Sunday, a Japanese public holiday, 31 Dec, or 1-3 Jan. Moved days can coincide: trade each
  date once.
- Skip a day that lands on 25 Dec or 1 Jan.
- The Tokyo fix is 00:55 UTC (09:55 JST) on the gotobi day.

The long:
- Buy at 15:55 UTC on the calendar day before the gotobi day.
- If that is inside the weekend closure (Sunday, for a Monday gotobi day), buy 15 minutes after prices resume.
- Wait while the spread is above 5 pips. Give up 120 minutes after the scheduled (or reopen-adjusted) time, and
  never buy with less than 30 minutes left before the exit.
- Server-side stop 55 pips below the entry and take-profit 30 pips above.
- Otherwise close at 00:54 UTC on the gotobi day.

The post-fix short:
- Only if no position is open, sell at the fix: the bot sends at 00:54:59 UTC. Skip it if it cannot be sent by
  00:55:05 or if the spread is above 5 pips.
- Server-side stop 55 pips above the entry. Buy back at 01:25 UTC.

Sizing:
- Risk `risk_pct` (6 in the example config) of current equity per trade, measured at the 55-pip stop.
- Round down to the lot step. Skip the trade if even the minimum lot risks more.

Kill switch: no new trades after the last 60 longs sum to less than -6R, or after a 50% drawdown from the peak.

Safety:
- Refuse real-money accounts unless BOTH `allow_live = true` in the config AND the `--allow-live` flag are given.
- One instance only.
- Recover correctly after a crash or restart, using the journal, open positions and the broker's deal history.
- Correct the PC clock against SNTP time servers, for the second-sensitive sell.

## What to do
1. Review the code against the rules, line by line where it matters: calendar, entry/exit timing, the short's
   seconds, sizing, kill switch, restart recovery, the main loop.
2. Run the existing tests. Look for tests that would pass even if the code were wrong.
3. Write your own adversarial tests in `codex_audit/bot_review/`. At minimum, a **24/7 soak test of the real
   entry point `bot.main.main()`**:
   - Put the simulator in as the MetaTrader5 module.
   - Use a simulated clock: patch sleep and time so the loop runs many months of simulated time in minutes.
   - Inject faults: terminal disconnects, `positions_get` failures, order rejections or requotes, unexpected
     exceptions, time-server failures, a PC clock that is off, and process restarts in the middle of trades.
   - Check: the loop never dies; every requested sleep is sane; no duplicate, hedged or stranded trades; trades
     match a clean run except where a fault explains the difference; memory does not grow without bound.
   Also check that every MetaTrader5 function and constant the bot uses exists in the installed MetaTrader5
   package, with compatible arguments.
4. Review Windows 24/7 operation:
   - the `run_bot.bat` restart loop and exit codes;
   - auto-start after a reboot or power cut (Task Scheduler, the need for an interactive logged-in session for
     the MT5 terminal);
   - sleep prevention and Windows Update restarts;
   - log rotation and state-file corruption on power loss;
   - MT5 terminal restarts and updates; internet loss; the Algo Trading button; a wrong PC clock.

## Deliver
- `codex_audit/bot_review/REPORT.md`. Put the verdict first: exactly one of READY FOR DEMO / READY AFTER FIXES /
  NOT READY. Then:
  - every issue, ranked CRITICAL / HIGH / MEDIUM / LOW, each with file:line, a concrete failure scenario and the
    fix;
  - what you tested and the results;
  - what can only be verified on a real MT5 terminal with a demo account, and exactly how to check it.
- Your test files in `codex_audit/bot_review/`, runnable with
  `python -m pytest codex_audit/bot_review -q -p no:cacheprovider`.
- Final message: the verdict and the top issues, in at most 40 lines.
