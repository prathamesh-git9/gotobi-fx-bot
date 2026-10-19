# Round 2 of the edge hunt (research only, the gotobi bot is untouched)

`lab.py` (my list, every rule fixed before running) and `codex_audit/explore2/` (Codex's list, its own code).
Pass = positive in both halves, beats the same trade at ordinary times, t > 2. Data: Exness bid/ask minutes
(`fetch.py`, saved in `data/`, not committed); 2006-2015 HistData bid with a modelled ask for the yen cross.

| Idea | Result |
|---|---|
| Gotobi on EUR/JPY, long | **passes**: +3.00 pips (t 3.2), ordinary days -1.43; 2006-15 unseen +3.11 (t 2.75); correlation with USD/JPY 0.53 (`cross_overlap.py`, `cross_oos.py`) |
| Gotobi on EUR/JPY, short | passes 2016-26 (+1.07) but fails 2006-15 (+0.04) |
| Gotobi on AUD/JPY | beats control, but +1.0 pip after spread: too thin |
| GBP/USD into the month-end fix | see `strategies/month_end_fix/`; Codex's independent check (`codex_audit/gbp_fix_check`): REAL EDGE in historical bars, permutation 0/10,000 |
| Same trade on AUD/USD, EUR/USD, USD/JPY, EUR/JPY, gold | all fail: the month-end fix effect is sterling-only |
| China: USDCNH month-end, PBoC fix | fail (spread ~30 pips) |
| Shanghai gold auctions | fail, every window |
| London silver price | fail, 0/11 years |
| Bitcoin: CME weekend gap, funding times, ETF 4 pm NAV, monthly expiry | all fail |
| DAX / FTSE / US500 expiry auctions | all fail |
| Codex: pre-FOMC drift, pre-holiday, toshin, JP half-year end, weekend gaps, BoJ days | all fail its Bonferroni gate (closest: BoJ-day USD/JPY long, p 0.018) |

## Round 3 (`lab3.py`, `codex_audit/explore3`)

| Idea | Result |
|---|---|
| Japanese importers paying ahead of long Tokyo closures (gotobi-style long) | 2006-15 +11.7 (17 trades) but 2016-26 -4.8: fail |
| US corporate tax days, buy USD | fail |
| Friday 4 pm fix / mid-month fix (GBPUSD, EURUSD) | fail |
| GBPUSD month-end fix, quarter-ends vs other month-ends | +4.66 vs +2.93 pips (fits a rebalancing story) |
| Sterling through crosses at the month-end fix | EURGBP sell +0.52 (weak), GBPJPY buy +3.51 (t 1.4, both halves up) |
| Gotobi long on GBPJPY / CADJPY / CHFJPY | +0.27 / +0.48 / -0.36: fail (only EURJPY carries the flow) |
| Codex: holiday reopenings (US, DE, UK, JP), FX futures expiry, US tax settlement, UK fiscal year | all fail Bonferroni |
