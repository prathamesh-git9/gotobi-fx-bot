# Round 4: something different (not calendar flows)

Ideas came from three places on 19–20 Oct 2026:
- Gemini 3.1 Pro, 5 ideas, asked in Brave (answers in [ideas.md](ideas.md)).
- Qwen, 5 ideas, asked in Brave (answers in [ideas.md](ideas.md)).
- Codex, 6 ideas of its own ([codex_audit/different](../../codex_audit/different/REPORT.md)).

All of them were tested on real Exness bid/ask minute bars. Each rule was written before any result was seen (see the [lab4.py](lab4.py) docstring). Where a model left a gap, I filled it once, up front, and marked it "my choice".

**To pass, a rule had to:**
- make money in both 2016–21 and 2022–26,
- beat the same entries taken in a random direction,
- reach t > 2.8 over 10 years (Bonferroni across 13 tests).

**Result: nothing passes.** Not one idea is profitable over the 10 years after the spread.

## Results

EUR 1,000 compounded at 2% risk per trade. R is profit per trade in units of the amount risked.

| Idea (source) | 10 yrs: trades | pips | R | t | EUR 1,000 → | 2 yrs: trades | R | EUR 1,000 → |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Q1 EURGBP H1 z-score fade (Qwen) | 2717 | −0.70 | −0.20 | −7.4 | 0 | 506 | −0.14 | 189 |
| G4 AUDNZD H1 z-score fade (Gemini) | 1077 | −1.32 | −0.16 | −4.0 | 24 | 233 | −0.14 | 486 |
| Q2 USDCNH extreme → AUDUSD (Qwen) | 2486 | −1.52 | −0.14 | −7.3 | 0 | 521 | −0.07 | 454 |
| Q3 GBPUSD London-morning fade (Qwen) | 438 | +0.03 | −0.00 | −0.0 | 838 | 46 | −0.05 | 944 |
| Q4 USDJPY breakout, gold holds → buy gold (Qwen) | 706 | −5.15 | −0.13 | −3.5 | 140 | 170 | −0.09 | 702 |
| Q5 US30/USTEC ratio, buy the laggard (Qwen)* | 106 | −17.2 | −0.17 | −0.9 | 876 | 57 | +0.05 | 1,035 |
| G3 US500 RSI(2) dip in an uptrend (Gemini)* | 1804 | −13.7 | −0.09 | −6.5 | 30 | 564 | −0.02 | 735 |
| G2 USDJPY carry while VIX < 20 (Gemini) | 101 | +12.2 | +0.02 | 0.2 | 1,022 | 27 | −0.01 | 995 |
| G5 GBPUSD volume-climax fade (Gemini) | 2112 | −1.73 | −0.08 | −5.4 | 29 | 304 | −0.08 | 598 |
| G5 XAUUSD volume-climax fade (Gemini) | 1366 | −8.89 | −0.06 | −3.5 | 154 | 476 | −0.08 | 432 |
| G1 EURUSD NFP drift (Gemini) | 103 | +0.49 | −0.06 | −0.5 | 862 | 16 | −0.03 | 989 |
| G1 USDJPY NFP drift (Gemini) | 107 | −1.18 | −0.03 | −0.2 | 902 | 17 | −0.21 | 927 |

\* Index data start in Aug 2019, so their "10 years" is really 7.

**Codex's own six ideas** (holdout 2022–26):

| Idea | Holdout pips/trade | t |
|---|---:|---:|
| US500 leads USDJPY | +0.32 | 0.3 |
| Gold leads AUDUSD | −2.70 | −2.9 |
| US close leads the DAX open | −4.10 | −1.1 |
| EURJPY triangle mispricing | 0 trades | – |
| USDJPY shock reversal | −7.08 | −2.0 |
| Quiet-day EURUSD continuation | −0.92 | −0.8 |

## What it says

**Mean reversion is real but smaller than the spread.** The two z-score fades (Q1, G4) beat random entries clearly:
- Q1: −0.20R against −0.28R for random entries.
- G4: −0.16R against −0.38R for random entries.

They still lose, because a 20-hour standard deviation of EURGBP or AUDNZD is only a few pips, and 1–2 pips of spread eats it. Widening the thresholds now, after seeing this, would be fitting to the test.

**The "famous" retail edges fail on minute data with real costs:**
- RSI(2) dip-buying wins 57% of the time but loses money.
- Volume-climax fades also lose.
- NFP drift loses too, though the NFP test only covers about 105 releases.

**The VIX-gated carry trade is flat over 10 years.** It is +0.16R in 2022–26, when the dollar–yen interest gap was wide, and negative before that. Waiting for VIX < 20 did worse than taking every trade above the 100-day average, which made +0.09R. I estimated the carry from T-bill minus BoJ rate minus 1% broker markup; that is an assumption, not Exness's actual swap.

**The keepers are still the three calendar-flow trades:**
- USDJPY gotobi (the live demo bot).
- The gotobi long on EURJPY.
- Buying GBPUSD 15:45–16:00 London into the month-end fix.

```
python strategies/explore/fetch.py AUDNZDm 2016   # data (VIX is in strategies/explore/data/vix.csv)
python strategies/different/lab4.py               # all ideas, ~40 min; or name some: Q1 G4 ...
```
