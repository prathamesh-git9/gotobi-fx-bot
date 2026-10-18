# Gotobi bot

Trades USD/JPY around the 09:55 JST Tokyo fix on gotobi days (the 5th, 10th, 15th, 20th, 25th and 30th, moved off
weekends and Japanese holidays). Two trades per gotobi day, never open at the same time:

1. **The long.** Buys at 15:55 UTC the day before, with a 55-pip stop and a +30-pip take-profit held on the
   broker's server. If neither is hit, it sells at 00:54 UTC, one minute before the fix.
2. **The post-fix short.** Sells at 00:54:59 UTC (one second before 09:55:00 JST) with a 55-pip server-side stop,
   and buys back 30 minutes later. It is skipped if:
   - the sell cannot go out by 5 seconds after the fix;
   - the spread is above 5 pips;
   - any position is open.

It drives a MetaTrader 5 terminal through MetaQuotes' official `MetaTrader5` Python package.

**It refuses real-money accounts** unless `allow_live = true` is in the config **and** `--allow-live` is passed. It
checks this at start-up and again on every poll, in case the terminal is switched to another account while it
runs.

## Why these two add-ons
108 variants were tested on 2016-2026 Exness bid/ask data (`src/gotobi_lab.py`): EMA filters, skipping Fed/BoJ
news days, ATR and trailing stops, ATR sizing, take-profits, extra trades, day types, regime filters, and other
entry and exit times. Each was chosen on 2016-2021 only and judged once on 2022-2026, with walk-forward
re-selection and a comparison against random filters. Only two improved both periods:
- **Take-profit at +30 pips**: about the same average profit with smaller swings. It works on a plateau
  (+20 to +60 pips all help), not a single lucky value.
- **The post-fix short**: on gotobi days USD/JPY falls after the fix (about -3.5 pips over 30 minutes, t about -8
  on raw ticks). On the other 1,860 fix days it does not, so the short loses there. That points to the gotobi
  flow (importers' dollar buying stops at the fix), not a general Tokyo-morning effect. The sell must land between
  about 10 s before and 1 s after 09:55:00 JST (`src/fix_seconds.py`). The bot therefore corrects the PC clock
  against internet time servers.

Everything else failed the honest test. That includes every EMA filter: the trades they skip were better than
the ones they keep. Skipping news days lowered the result.

An independent re-implementation from the rules and the raw data (`codex_audit/REPORT.md`) found the same trades.
It rated the edge "weak or fragile": real on gotobi days (t 6.0; the same trades on other days are flat), but
only about 3 pips per trade. Overnight swap and real fills at the fix are not in any backtest. The demo shows both.

## Connect your account and run it automatically (Windows)

Do every step on a **demo** account first.

**1. Open an MT5 account.**
- Exness: Personal Area > Open new account > **Demo**, MetaTrader 5, Standard or Standard Cent.
- Note the login number, the password and the server name.
- Any other MT5 broker works too: see "Using another broker" below.

**2. Install MetaTrader 5 and log in.**
- Install MT5 from your broker's Personal Area.
- File > Login to Trade Account: enter your login, password and server, and tick **Save password**. That lets
  the terminal log back in by itself after a restart.
- Tools > Options > Expert Advisors:
  - tick **Allow algorithmic trading**;
  - untick **Disable algorithmic trading via external Python API**;
  - untick both **Disable algorithmic trading when the account / the profile has been changed**.
- The **Algo Trading** button on the toolbar must be green.
- Use this terminal and account for the bot only. While a position the bot did not open is on USD/JPY, the bot
  opens nothing (a manual trade on the same account would otherwise sit next to the bot's).

**3. Install the bot.**
- Install Python 3.12 or newer from python.org and tick "Add python.exe to PATH". The bot is tested on 3.14.
- Get the code: `git clone https://github.com/prathamesh-git9/gotobi-fx-bot`, or Code > Download ZIP.
- In that folder, run `pip install -r requirements-bot.txt`.

**4. Configure it.**
- `copy bot_config.example.toml bot_config.toml`
- In `bot_config.toml`:
  - `risk_pct = 6.0` is already set.
  - Leave `symbols` as it is: it picks USDJPYc (Cent), USDJPYm (Standard) or USDJPY, whichever your account
    has.
  - Uncomment `terminal_path` and point it at your MT5 (e.g.
    `"C:/Program Files/MetaTrader 5 EXNESS/terminal64.exe"`), so the bot can start MT5 itself after a reboot.
- Never put your password in the file: the bot uses the terminal's saved login.

**5. Check it, then start it.**
- `python -m bot.main --config bot_config.toml --preflight` must end with **READY**. It never trades. It checks:
  - the terminal, the account and the symbol;
  - the spread, both clocks and other positions;
  - the trade size;
  - the broker's own check of the planned buy and sell.
- Optional: run one gotobi day with `--dry-run`. It checks every order and sends none.
- Double-click `run_bot.bat` and leave the window open; closing it stops the bot.
  - It restarts the bot 30 s after a crash or a lost terminal.
  - It does not restart it after Ctrl+C, or after a refusal (real account, bad config).

**6. Make it start by itself.**
- **Start at log-on.** Run `powershell -ExecutionPolicy Bypass -File install_autostart.ps1`. It creates a Task
  Scheduler task, "Gotobi bot", that opens `run_bot.bat` one minute after you log on.
  - It sets **no time limit**. Tasks made with the wizard, schtasks or PowerShell defaults are stopped after 3
    days.
  - `-DryRun` shows what it would create; `-Remove` deletes it.
- **Sign in automatically after a reboot** (Windows Update, power cut):
  - Settings > Accounts > Sign-in options: turn off "only allow Windows Hello sign-in".
  - Win+R > `netplwiz`: untick "Users must enter a user name and password".
  - Anyone with access to the PC can then use it.
- **Power.** Plugged in, never sleep. Lid closed: do nothing. If the BIOS has "restore on AC power loss", turn it
  on. The bot stops idle sleep while it runs; it cannot stop a closed lid or the power button.
- **Windows Update.** Set Active hours to 15:00-03:00. That keeps restarts out of every trade window (15:55-01:25
  UTC, which is 16:55-02:25 Irish summer time).
- **Network.** Wired internet if possible. Outbound UDP port 123 must be open, for the time check.

**7. Check on it.**
- `bot_state/bot.log` records everything, in UTC. MT5's History tab shows the trades with the comments
  `gotobi YYYY-MM-DD` and `gotobi-s YYYY-MM-DD`.
- `--status` prints the next trade and the journal. It takes the same lock as the bot, so run it while the bot is
  stopped.
- During the demo, compare each fill with the price at the scheduled time.
  - Each short's `sent_vs_fix_sec` and `filled_vs_fix_sec` in `bot_state/state.json` should sit between about
    -2 and +1.
  - Look at the overnight swap charged on each long, which the backtest leaves out.

**8. Real money: your decision, and only after the demo matches the backtest.**
- Log the terminal in to the real account.
- Set `allow_live = true` in `bot_config.toml`.
- Start with `run_bot.bat --allow-live`. For the auto-start task, add `--allow-live` to its arguments in Task
  Scheduler.
- Exness may not open real accounts for EU residents. With an EU MT5 broker:
  - Check its USD/JPY spread at 15:55, 00:54 and 00:55 UTC: the edge is only about 3 pips a trade.
  - 1:30 leverage is enough.

## What it writes (`bot_state/`)
- `bot.log`: everything, in UTC (rotated at 5 MB, 5 old files kept).
- `state.json`: one record per trade, open / closed / skipped / missed / dryrun, with prices, P&L and R. It also
  holds the account it belongs to, the balance peak and the kill switch.
  - `YYYY-MM-DD` is the long; `YYYY-MM-DD/short` is the post-fix short.
  - Each short records `sent_vs_fix_sec` (when the sell went out, read from the clock just before sending),
    `answered_vs_fix_sec` (when the terminal confirmed it) and `filled_vs_fix_sec` (the broker's deal time). All
    are seconds from 09:55:00 JST.
  - It is written atomically, so a power cut leaves the old or the new file, never half of one.
- `state.json.bak`: a second copy, rewritten after every save, so it includes the kill switch.
  - If `state.json` cannot be read or has the wrong structure (a disk fault, a bad hand edit), the bot starts from
    the backup. The bad file is kept as `state.corrupt-<time>.json`.
  - With no usable backup either, it rebuilds open trades from the broker's positions and deal history. It then
    halts new trades until `--clear-halt`, because nothing is known about the kill switch.
  - To start completely fresh, delete the whole `bot_state` folder.
- `HALTED`: present while the kill switch is on (its reason inside). `--clear-halt` removes it.
- `events.jsonl`: every change, for audit (rotated to `events.1.jsonl` at 20 MB).

## Safety behaviour
**Never trades twice, never hedges**
- Each trade is guarded by the journal, the open positions and the broker's own deal history.
- **At most one order per trade.** Each order is written to the journal *before* it is sent.
  - If no definite answer comes back (no reply, a timeout, a lost connection, "placed" but not filled, or the bot
    stops right after sending), that trade is never sent again.
  - The bot watches the broker instead: a fill is adopted as an open position, or recorded from the deal history
    if it has already closed. If nothing shows up, the trade is marked missed. Meanwhile nothing new opens.
  - Definite rejections (requote, price changed, market closed) are simply retried.
- **No queued leftovers.** The bot only ever sends market orders, so a live (queued) order carrying its magic
  number can only be a leftover: a request answered with "placed", or the unfilled rest of a partial fill.
  - It is cancelled on sight, and nothing new opens while one exists.
  - So a late fill can never land on top of the next trade.
  - A fill that beats the cancel is adopted and closed on time.
- The stop and target are placed from the same quote the order is sent at.
- The short is sent only when no position is open.
- No entry while any position on the symbol is open, including ones the bot did not open.
- Errors reading positions or orders abort the poll; they are never read as "nothing open". (MT5's reply of None
  together with its success code does mean "none".)
- A trade whose result is not in the history yet (the history cannot be read, or the closing deal is missing) is
  never written off. It stays unresolved, so its R still counts for the kill switch, and nothing new opens until
  it is accounted for.

**Right account only**
- Every poll checks that the terminal is still on the account the bot started with, and that a real-money account
  has both keys. If not, the bot pauses completely until the account is back.
- A state folder holding another account's open trades is refused at start-up.
- One copy per state folder and one per trading account (file locks).

**Prices, spread and orders**
- Waits for live prices; after a weekend reopen or a feed outage of 30+ minutes it waits 15 minutes.
- Spreads above 5 pips:
  - the long waits, and gives up 2 hours after schedule or 30 minutes before the exit;
  - the short is skipped (some fixes in late 2022 had 7-12 pip spreads).
- The short's 5-second limit is checked again against a fresh clock reading right before the order goes out (a
  busy terminal can use up the window).
- Rejected orders are retried if temporary; a fatal rejection skips that trade.

**Kill switch**
- No new trades after the last 60 longs lose more than 6R.
- No new trades once equity is 50% or more below its peak. This is checked after every trade and before every
  entry, so a fall while flat counts too (note: a withdrawal counts as a fall).
- Open trades are still closed on time.
- It is kept twice: in `state.json` and as a `HALTED` file, so losing or restoring an old `state.json` cannot
  switch it off.
- To resume, run `python -m bot.main --config bot_config.toml --clear-halt` with the bot stopped. It restarts both
  rules from that moment (the balance peak and the window of the last 60 longs), so an old losing run cannot trip
  it again at once. There is no need to edit `state.json` by hand.

**Clock**
- The time check (SNTP, hourly, never within 5 minutes of a trade) needs at least two time servers that agree.
- When Windows resets its own clock, the correction follows, so the bot's time never jumps.
- **The short needs a clock confirmed by the time servers within the last 12 hours.** Otherwise it is skipped,
  since it has to land within seconds of the fix. If UDP port 123 is blocked, Windows cannot sync its own clock
  either, and it drifts.
- With the clock unconfirmed, the long first compares the PC clock with at least five live prices (a new tick is
  at most a few seconds old). It trades only if the two agree within 30 s, so the 00:54 exit stays before the fix.
- The broker's clock offset is only measured from prices while the clock is confirmed. A PC clock an hour out
  therefore makes prices look stale and the bot waits (with an error in the log); it cannot pass for a broker in
  another time zone.

**The main loop**
- Nothing in the loop can end it except Ctrl+C.
- Errors are logged and retried: every 5 s, backing off to 60 s, but every second when a trade action is due
  within 5 minutes.

## Known limits
- **A timed exit needs the PC, MT5 and the internet.** If any of them is down at 00:54 UTC, the long stays open
  until the bot is back, protected only by its server-side 55-pip stop and 30-pip target (MT5 has no server-side
  time stop). The same applies to the short's 01:25 buy-back. The bot closes an overdue trade the moment it can.
- **The risk is a target, not a cap.** The stop sits 55 pips from the quote the order is sent at. Slippage on
  the fill (up to the 3-pip deviation) and a gap through the stop can lose more than `risk_pct`.
- **The short's 5-second limit applies to sending.** A terminal that takes long to answer can fill it later. The
  real fill time is recorded (`filled_vs_fix_sec`).
- **Partial fills.** The bot tries fill-or-kill, then immediate-or-cancel, so an unfilled rest is cancelled by the
  broker. A rest left queued (a broker that accepts neither) is cancelled by the bot. The trade is managed at the
  size that filled.
- **No alerts.** The bot writes problems to `bot.log` but does not message you. During the demo, read the log.
- **The simulator fills at minute prices.** It has no partial fills, queueing or network delay. Real fill timing
  at the fix is what the demo is for.

## Tests
- `python -m pytest -m "not slow"`: 157 unit, scenario and safety tests on the MT5 simulator (about 15 s). They
  include:
  - a regression test for every safety finding of the independent review;
  - quick runs of the real entry point, `bot.main.main()`.
- `python -m pytest`: adds the 2016-2026 replays and the 24/7 soak test (about 16 minutes). The soak test runs
  `bot.main.main()` through 5.5 months of real prices while injecting:
  - terminal disconnects (some at the exact entry, exit and fix second);
  - failed position reads, requotes and timeouts;
  - exceptions;
  - dead time servers;
  - 12 kill-and-restarts.
- `python tests/mutation_check.py`: a check of the tests themselves.
  - It copies the bot to a throwaway folder, makes one deliberate one-line mistake in the copy (68 in turn), and
    confirms a test fails each time.
  - The real files are never touched.
- `python -m bot.replay --start 2026-01-01 --end 2026-10-16 --balance 1000 --risk 6 --leverage 500` runs the
  production code on real Exness history (USD account).

Verified on 2016-2026 Exness data:
- **Matches the research backtest, trade for trade.** The plain long reproduces it exactly (757/757 and 755/755).
  With the take-profit and the short, all 752 longs match the lab. 737 of the 739 shorts match; the other 2 had no
  price in the buy-back minute, so the close went a minute later.
- **Skipped shorts are all explained by the data.** 16 shorts were skipped, all for a spread above 5 pips or no
  price at the fix.
- **Robust to crashes and outages.** Random crash-restarts change no trade. Forced outages never duplicate or
  strand a trade.
- **No look-ahead.** With all future prices deleted at decision moments (including the fix second), every
  decision is identical.
- **The tests notice mistakes.** Each of the 68 deliberate mistakes made in a throwaway copy fails a test.

Not yet verified: a real MT5 terminal, real fill timing at the fix, and the broker's swap. That is what the demo
period is for. `codex_audit/bot_review/REPORT.md` lists the checks to make on the demo.

## Using another broker / account
- Any MT5 broker works: put its USD/JPY symbol name first in `symbols` (e.g. "USDJPY", "USDJPY.pro").
- The server clock offset is measured automatically (`auto_server_offset`, which needs the time check to work).
  Filling mode and lot rules are read from the broker.
- The backtest costs are Exness's, about 1.5-2.4 pips per trade in spread. Check the broker's USD/JPY spread
  (+ commission) at 15:55, 00:54 and 00:55 UTC. Much above 2 pips per round trip eats most of the edge, and the
  short is the most cost-sensitive part.
- Swap-free (Islamic) accounts: check for a daily holding fee. The long is held over the 17:00 New York
  rollover; the short is not.
- Demo on that broker first (`--dry-run`, then demo trading). To run without the short, set
  `post_fix_short = false`.
