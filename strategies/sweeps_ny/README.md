# Round 5: liquidity sweeps at the New York open (NASDAQ, S&P, Dow, gold)

The repo's first study tested 192 sweep variants on gold and FX at prior-day highs/lows. This round covers the
session setups SMC traders use most. There are four rules, fixed before running and not tuned; see the
[lab5.py](lab5.py) docstring for the exact rules.

They were tested on real Exness bid/ask minute bars:
- indices from Aug 2019,
- gold from 2016.

**Result: 0 of 13 pass.** Every setup loses over the full period:

| Setup | NASDAQ | S&P 500 | Dow | Gold |
|---|---:|---:|---:|---:|
| S1 overnight-range sweep at the NY open | −0.11R | −0.15R | −0.12R | −0.10R |
| S2 previous-day high/low sweep | −0.05R | −0.20R | −0.09R | −0.06R |
| S3 opening-range "Judas swing" | −0.06R | −0.12R | −0.10R | – |
| S4 Asia-range sweep at the London open | −0.18R | – | – | −0.17R |

**Win rates:** 27–35% at a 2R target. That is below the 34% needed to break even, before costs.

**Last two years (Oct 2024–Sep 2026):** a few look positive, but none is significant (t ≤ 1.2), and all of them
were negative over the full period:
- S1 Dow +0.07R
- S2 Dow +0.14R
- S2 NASDAQ +0.06R

[sweep_examples.png](sweep_examples.png) shows the same S1 pattern twice on NASDAQ:
- 6 Aug 2026, which worked (+2R),
- 17 Jul 2026, which was stopped out.

`python strategies/sweeps_ny/lab5.py` (~30 min) writes lab5_output.txt and lab5_results.json.
