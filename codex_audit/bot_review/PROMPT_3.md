# Third review: re-check the bot after the second round of fixes

You have reviewed this MT5 bot twice. Your reports are `codex_audit/bot_review/REPORT.md` and `REPORT_2.md`, and
your tests are `test_adversarial.py` and `test_recheck.py` in the same folder. Your second verdict was NOT READY,
with new CRITICAL / HIGH / MEDIUM issues:
- a PLACED order resent;
- a fill resent after a position-read error;
- the short a minute early with blocked time servers;
- a backup losing the kill switch;
- valid-but-malformed JSON crashing start-up;
- partial fills;
- history errors erasing risk accounting;
plus partly-fixed items. The code under `bot/`, `tests/`, `BOT_README.md` and `bot_config.example.toml` has been
changed again.

You are still an independent reviewer with no stake in the answer. Verify everything yourself; do not trust
comments, docs or test names.

## Ground rules (same as before)
- Read whatever you need under `bot/`, `tests/`, `run_bot.bat`, `install_autostart.ps1`,
  `bot_config.example.toml`, `requirements-bot.txt` and `BOT_README.md`.
- Write only inside `codex_audit/bot_review/` (e.g. a new `test_recheck3.py`). Do not commit. Do not install
  packages globally.
- Limited RAM:
  - one heavy process at a time;
  - no multiprocessing or parallel pytest;
  - peak memory under about 3 GB.
- Use `--basetemp codex_audit/bot_review/pytest_base` with pytest. There is no MT5 terminal on this PC;
  `bot/fake_mt5.py` is the simulator.

## What to do
1. For each issue in REPORT_2.md (the 17-finding table and the 7 new issues), decide FIXED / PARTLY FIXED /
   NOT FIXED / ACCEPTED LIMIT, with evidence: file:line and a test you ran.
   - Re-run your reproductions from `test_recheck.py`. Where a reproduction now fails because the outcome is
     safe, write and run the inverse test.
2. Look hard for NEW problems introduced by these changes:
   - the order intent written before sending ("sending" / "unknown" journal states);
   - never resending after an unknown outcome;
   - resolving pending orders from positions and history;
   - blocking new entries while an order or a history read is unresolved;
   - stop/target placed from the sending quote (`sl_dist` / `tp_dist`);
   - the backup rewritten on every save, schema validation, and the halt when all state is lost;
   - `--clear-halt`;
   - the short skipped when the clock is unverified;
   - the long blocked when an unverified PC clock sits > 30 s off the tick times.
   In particular, check:
   - Can any of this block trading forever in a normal healthy setup (demo account, Exness UTC+0 server, time
     servers reachable)?
   - Can it strand a position, or lose a trade from the kill-switch accounting?
   - Can it crash the loop?
3. Run the fast suite (`python -m pytest tests -m "not slow" -q -p no:cacheprovider --basetemp ...`) and your
   tests. Run the slow suite only if needed, never alongside another heavy job.

## Deliver
- `codex_audit/bot_review/REPORT_3.md`. Put the verdict first: exactly one of READY FOR DEMO / READY AFTER FIXES /
  NOT READY. Then:
  - the status table;
  - new issues ranked CRITICAL / HIGH / MEDIUM / LOW, each with file:line, a failure scenario and the fix;
  - what you ran, and the results;
  - what only the real demo terminal can show.
  Be explicit about which remaining items are design limits that a demo run, not more code, should settle.
- Final message: the verdict and the top points, in at most 30 lines.
