# Independent reviews

A second AI agent (OpenAI Codex CLI), run from PowerShell, reviewed this project without access to the author's
conclusions. Each `PROMPT*.md` is exactly what it was asked.

- **The strategy** (`PROMPT.md`, `REPORT.md`, `backtest.py`): it rebuilt the backtest from the rules and the raw
  Exness data alone. Verdict: a real but thin ("weak or fragile") edge: t 6.0 on gotobi days, flat on other days,
  about 3 pips per trade before swap and real fills.
- **The bot's code** (`bot_review/`): three review rounds. Each round's issues were fixed in `bot/` and given
  regression tests in `tests/test_safety.py` and `tests/test_main_soak.py`:
  - round 1 (`REPORT.md`): 17 issues;
  - round 2 (`REPORT_2.md`): re-check, plus 7 new issues;
  - round 3 (`REPORT_3.md`): re-check, plus 9 new issues.
  The fixes after round 3 have not had a fourth review.

`bot_review/test_*.py` are the reviewer's own tests. Several of them *assert the unsafe behaviour the reviewer
reproduced at the time*. Now that it is fixed, those fail by design; the safe outcome is checked in `tests/`.
They are not part of the project's test suite (`pytest.ini` only collects `tests/`).
