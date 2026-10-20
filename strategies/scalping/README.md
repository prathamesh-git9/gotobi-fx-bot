# Round 8: scalping (1–60 minute trades)

There were three sources of ideas, all fixed before running and tested on real Exness bid/ask minute bars:
- **mine** ([lab8.py](lab8.py)): minute-scale reactions to scheduled US news, never tested here before;
- **Gemini Pro and Qwen 3.7-Plus** ([lab8_ai.py](lab8_ai.py), their answers in [ai_answers.md](ai_answers.md)):
  five rules each, coded exactly as written;
- **Codex** earlier tested five pure-technical 1–15 minute scalps on four symbols at today's spreads
  ([codex_audit/edge_hunt](../../codex_audit/edge_hunt/REPORT.md), section C). All 20 lost.

**Result: none of the 30 new scalps pass.**

| Rule (source) | 2016–26* avg R | t | Last 2 yrs avg R |
|---|---:|---:|---:|
| 08:30 data shock, momentum (me), EURUSD / USDJPY / gold / US500 | −0.13 / −0.11 / +0.02 / −0.20 | | −0.10 / −0.16 / +0.28 / −0.08 |
| 08:30 data shock, faded (me) | −0.33 / −0.14 / −0.18 / −0.46 | | |
| 10:00 data shock, momentum (me) | −0.02 / +0.00 / +0.02 / −0.20 | | |
| FOMC statement, momentum (me) | −0.06 / +0.03 / −0.17 / −0.14 | | |
| FOMC statement, faded (me) | −0.39 / −0.51 / −0.50 / −0.44 | | |
| 10:00 NY option-cut fade, EURUSD (Gemini) | −0.12 | −5.0 | −0.04 |
| Treasury-auction momentum, USDJPY (Gemini) | −0.07 (11 trades) | | |
| Friday London-close fade, GBPUSD (Gemini) | −0.14 | −1.8 | −0.06 |
| Post-NFP fade, US500 (Gemini) | −0.15 | −1.6 | +0.07 |
| Shanghai 09:30 gold buy (Gemini) | −0.11 | −4.9 | −0.13 |
| Month-end yen repatriation short, USDJPY (Qwen) | −0.07 | −1.2 | +0.16 (24 trades) |
| LBMA gold AM fix fade (Qwen) | −0.24 | −16.4 | −0.15 |
| Friday S&P gamma pin (Qwen) | −0.12 | −0.6 | −0.08 |
| Post-close MOC fade, US500 (Qwen) | −0.40 | −6.7 | −0.29 |
| 17:00 NY rollover wick fade, EURUSD (Qwen) | −0.83 (win 2%) | −69 | −0.87 |

\* US500 from 2019.

## What it says

1. **News moves keep going, but not far enough to pay.**
   - Fading the first two minutes after US data or the Fed is one of the worst things tested (−0.14R to −0.51R).
   - Following them is roughly breakeven before the spread.
   - Only gold after 08:30 data looks good recently (+0.28R), on 53 trades with t 1.1, so it is not proven.
2. **The rollover and the minutes right after the close are where retail spreads are widest.** Qwen's 17:00 New
   York rollover fade wins 2% of the time because the spread at 17:02 is bigger than the wick it tries to fade.
3. **Both chatbots gave the same verdict as our data:** retail scalping can only work on forced, scheduled flows,
   never on chart patterns. The two flow scalps we already have are still the only ones that work:
   - the Tokyo-fix short on gotobi days (09:55 → 10:25 Tokyo);
   - GBPUSD into the month-end London fix (15:45 → 16:00).

## EUR 1,000 from 1 Jan 2026 ([ytd_2026.py](ytd_2026.py), data to 20 Oct for gotobi, 30 Sep otherwise)

| Strategy | 6% risk | 10% risk |
|---|---:|---:|
| gotobi bot (long + Tokyo-fix short), 113 trades | EUR 1,636 (+64%), max drop 13% | EUR 2,204 (+120%), max drop 21% |
| Tokyo-fix short scalp alone, 56 trades | EUR 1,016 (+2%) | EUR 1,020 (+2%) |
| GBPUSD month-end 15-min scalp, 9 trades (3 stops Jan–Mar, then 6 wins) | EUR 1,089 (+9%) | – |
| NASDAQ noise-area momentum (paper sizing), to 29 Sep | EUR 1,047 (+5%) | – |

The real bot replay (lot rounding, EUR conversion) gives EUR 1,618 at 6% and EUR 2,186 at 10% for the same period.
