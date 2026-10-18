# Second review: re-check the bot after the fixes

You reviewed this MT5 bot earlier (your report: `codex_audit/bot_review/REPORT.md`; your tests:
`codex_audit/bot_review/test_adversarial.py`). Your verdict was NOT READY. The code under `bot/`, `tests/`,
`run_bot.bat`, `install_autostart.ps1` and `BOT_README.md` has since been changed in response.

You are still an independent reviewer with no stake in the answer. Do not assume the changes are correct or
complete, and do not trust comments, docs or test names: verify everything yourself.

## Ground rules (same as before)
- Read whatever you need under `bot/`, `tests/`, `run_bot.bat`, `install_autostart.ps1`,
  `bot_config.example.toml`, `requirements-bot.txt` and `BOT_README.md`.
- Do NOT modify anything outside `codex_audit/bot_review/`. Write new tests there, e.g. `test_recheck.py`. Do not
  commit. Do not install packages globally.
- Limited RAM:
  - one heavy process at a time;
  - no multiprocessing or parallel pytest;
  - peak memory under about 3 GB.
- Use `--basetemp codex_audit/bot_review/pytest_base` with pytest: the default temp folder is not writable for
  you.
- There is no MT5 terminal on this PC. `bot/fake_mt5.py` is the simulator.

## What to do
1. For EACH of your 17 findings, decide FIXED / PARTLY FIXED / NOT FIXED / ACCEPTED LIMIT (documented, not
   fixable in code), with evidence: the code (file:line) and a test you ran.
   - Your characterization tests in `test_adversarial.py` asserted the old unsafe behaviour. Where an outcome is
     now safe, those tests should fail. Write the inverse tests that assert the safe outcome, and run them.
2. Look hard for NEW problems introduced by the changes:
   - the account-identity pause;
   - the "unknown order outcome" hold-off and history re-check;
   - blocking entries on other positions;
   - the kill switch checked before entries;
   - journal backup/corrupt-file recovery and the account field;
   - the clock jump-following and verified() gating of the broker-offset measurement;
   - the main-loop error handling and retry delays;
   - the per-account lock;
   - run_bot.bat exit codes;
   - install_autostart.ps1.
   In particular, check:
   - Can any change block trading forever in a normal, healthy setup (e.g. a demo account, Exness UTC+0 server,
     time servers reachable, or time servers blocked)?
   - Can it create a duplicate trade, a hedge or a stranded position?
   - Can it crash the loop?
3. Run the fast suite (`python -m pytest tests -m "not slow" -q -p no:cacheprovider --basetemp ...`), your old
   tests and your new tests. Run the slow suite only if you need it, and never alongside another heavy job.
4. Re-check the 24/7 Windows setup: `run_bot.bat`, `install_autostart.ps1` (read it; do NOT register a scheduled
   task) and the setup steps in BOT_README.md.

## Deliver
- `codex_audit/bot_review/REPORT_2.md`. Put the verdict first: exactly one of READY FOR DEMO / READY AFTER FIXES /
  NOT READY. Then:
  - the 17-finding table;
  - any new issues ranked CRITICAL / HIGH / MEDIUM / LOW, each with file:line, a failure scenario and the fix;
  - what you ran, and the results;
  - what still needs the real demo terminal.
- Final message: the verdict and the top points, in at most 30 lines.
