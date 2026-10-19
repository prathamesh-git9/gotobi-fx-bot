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
