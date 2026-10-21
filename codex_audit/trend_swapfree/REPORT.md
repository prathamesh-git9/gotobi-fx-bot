# Time-series momentum on Exness swap-free: EUR 1,000 decision

**Verdict: no reliable, executable edge for this account size.** The pre-declared eight-market trend portfolio earned only **1.35% a year** in the 2016–September 2026 hold-out even with permanent zero swap, with Sharpe **0.18** and maximum drawdown **22.5%**. An unlevered equal-weight long position in the same eight price proxies earned **7.89% a year**. The broader trend variant lost **2.15% a year** in the hold-out. Once swap-free status is lost in the declared 8%-of-gross financing scenario, the main strategy loses **12.47% a year**. On 25 September 2026, **all eight desired positions were smaller than Exness Standard's minimum order**. I would not forward-test this as a proposed EUR 1,000 live portfolio.

The result is a proxy backtest, not a broker-executable historical equity curve. The rules were recorded in [RULES.md](RULES.md) before calculating any returns; sources and account terms are in [RESEARCH.md](RESEARCH.md). Reproduce every figure with `python research.py`; machine-readable full precision results are in [results.json](results.json).

## Design and test

The main **A12** book trades EURUSD, GBPUSD, USDJPY, gold, US500, USTEC, DE30 and UK100. It combines 1-, 3-, and 12-month price-trend signs, scales by trailing 63-day volatility toward 12% standalone portfolio risk, rebalances weekly, caps each instrument at 0.75 times equity and gross leverage at 2 times equity. **B12**, the sole pre-declared variant, adds AUDUSD, NZDUSD, USDCAD, USDCHF and silver. All thirteen are currently listed as swap-free eligible by [Exness](https://get.exness.help/hc/en-us/articles/4402341895570-Swap-free-status), subject to account qualification. The design sample ends 31 December 2015; the 2016–2026 hold-out was judged once with those rules.

Yahoo daily closes provide price returns. Exness minute bid/ask files provide year-specific transaction spreads and an independent signal-direction check. The full eight-market book can start once all eight have a 252-observation history, **7 November 2005**; the thirteen-market book starts **3 May 2007**. The backtest ends **30 September 2026**, despite later rows in some input files. EUR balances below rescale each window's return path to EUR 1,000; positions inherited from the preceding strategy history are treated as established at each window start, so no new opening spread is charged for that rescaling. Geometric annual return uses 252 trading days, Sharpe uses zero cash return, and worst calendar year includes partial endpoint years.

## Main A12: full record, design, hold-out and EUR 1,000 windows

“0” means swap-free remains in force. “8%” charges 8% annualized on the absolute gross notional, including shorts, as an adverse estimate if status is removed. Both cases pay historical Exness spreads on every weekly unit change. “Long” is equal-weight buy-and-hold of the same eight proxies, rebalanced weekly without leverage, with the same spread and financing assumptions. Cash remains EUR 1,000, Sharpe undefined, drawdown zero.

| Period | Portfolio | Final EUR | Annual return | Sharpe | Max drawdown | Worst calendar year |
|---|---|---:|---:|---:|---:|---:|
| Full 2005–2026 | Trend, 0 | 1,752 | 2.63% | 0.28 | -31.4% | 2016: -13.2% |
| Full 2005–2026 | Trend, 8% | 87 | -10.67% | -0.90 | -91.6% | 2016: -24.5% |
| Full 2005–2026 | Long, 0 | 3,711 | 6.25% | 0.67 | -33.7% | 2008: -24.1% |
| Full 2005–2026 | Long, 8% | 658 | -1.92% | -0.15 | -54.4% | 2008: -30.2% |
| Design to 2015 | Trend, 0 | 1,510 | 4.00% | 0.37 | -18.3% | 2011: -10.6% |
| Design to 2015 | Trend, 8% | 383 | -8.72% | -0.64 | -63.0% | 2015: -21.7% |
| Design to 2015 | Long, 0 | 1,594 | 4.54% | 0.45 | -33.7% | 2008: -24.1% |
| Design to 2015 | Long, 8% | 689 | -3.49% | -0.26 | -40.8% | 2008: -30.2% |
| Hold-out 2016–2026 | Trend, 0 | 1,160 | 1.35% | 0.18 | -22.5% | 2016: -13.2% |
| Hold-out 2016–2026 | Trend, 8% | 227 | -12.47% | -1.21 | -78.3% | 2016: -24.5% |
| Hold-out 2016–2026 | Long, 0 | 2,328 | 7.89% | 0.97 | -19.1% | 2022: -8.3% |
| Hold-out 2016–2026 | Long, 8% | 956 | -0.41% | -0.01 | -27.6% | 2022: -15.6% |
| (a) Oct 2016–Sep 2026 | Trend, 0 | 1,288 | 2.48% | 0.29 | -22.5% | 2020: -7.0% |
| (a) Oct 2016–Sep 2026 | Trend, 8% | 279 | -11.59% | -1.13 | -72.3% | 2020: -19.2% |
| (a) Oct 2016–Sep 2026 | Long, 0 | 2,274 | 8.26% | 1.01 | -19.1% | 2022: -8.3% |
| (a) Oct 2016–Sep 2026 | Long, 8% | 994 | -0.06% | 0.03 | -27.6% | 2022: -15.6% |
| (b) Oct 2024–Sep 2026 | Trend, 0 | 1,122 | 5.74% | 0.59 | -8.8% | 2026*: -4.7% |
| (b) Oct 2024–Sep 2026 | Trend, 8% | 822 | -9.03% | -0.85 | -18.8% | 2026*: -14.8% |
| (b) Oct 2024–Sep 2026 | Long, 0 | 1,267 | 12.09% | 1.51 | -7.8% | 2024*: +0.7% |
| (b) Oct 2024–Sep 2026 | Long, 8% | 1,073 | 3.47% | 0.48 | -8.8% | 2026*: -1.8% |
| (c) Jan–Sep 2026 | Trend, 0 | 953 | -6.01% | -0.59 | -8.8% | 2026*: -4.7% |
| (c) Jan–Sep 2026 | Trend, 8% | 852 | -18.67% | -2.08 | -17.0% | 2026*: -14.8% |
| (c) Jan–Sep 2026 | Long, 0 | 1,045 | 5.83% | 0.69 | -6.4% | 2026*: +4.5% |
| (c) Jan–Sep 2026 | Long, 8% | 982 | -2.31% | -0.22 | -7.7% | 2026*: -1.8% |

Cash is **EUR 1,000, 0% annual return and 0% drawdown** in every period. An asterisk marks a partial calendar year; its worst-year figure is the actual partial-year return, whereas the “annual return” column is annualized. For the two-year long/zero case, the smallest of its three calendar slices was still the positive October–December 2024 return.

## Pre-declared broader variant B12

The extra FX majors and silver did not rescue trend following. The table below includes both financing cases; the equal-weight long B12 comparison in the hold-out is **EUR 1,909 / 5.99% annual / Sharpe 0.91 / -15.5% drawdown** under zero swap, and **EUR 784 / -2.17% annual** under 8% financing. Exact figures for every B12 long period and worst year are in [results.json](results.json).

| Period | B12 trend financing | Final EUR | Annual return | Sharpe | Max drawdown | Worst year |
|---|---|---:|---:|---:|---:|---:|
| Full 2007–2026 | 0 | 1,136 | 0.64% | 0.11 | -41.2% | 2016: -16.3% |
| Full 2007–2026 | 8% | 56 | -13.39% | -1.16 | -95.3% | 2016: -28.5% |
| Design to 2015 | 0 | 1,447 | 4.20% | 0.36 | -21.2% | 2011: -8.9% |
| Design to 2015 | 8% | 402 | -9.66% | -0.65 | -66.1% | 2011: -21.2% |
| Hold-out 2016–2026 | 0 | 785 | -2.15% | -0.18 | -36.1% | 2016: -16.3% |
| Hold-out 2016–2026 | 8% | 138 | -16.28% | -1.82 | -86.7% | 2016: -28.5% |
| (a) Oct 2016–Sep 2026 | 0 | 895 | -1.07% | -0.07 | -29.1% | 2023: -9.0% |
| (a) Oct 2016–Sep 2026 | 8% | 177 | -15.39% | -1.72 | -82.3% | 2023: -22.4% |
| (b) Oct 2024–Sep 2026 | 0 | 1,075 | 3.56% | 0.42 | -10.5% | 2026*: -5.1% |
| (b) Oct 2024–Sep 2026 | 8% | 774 | -11.63% | -1.28 | -22.6% | 2026*: -16.0% |
| (c) Jan–Sep 2026 | 0 | 949 | -6.52% | -0.75 | -10.5% | 2026*: -5.1% |
| (c) Jan–Sep 2026 | 8% | 840 | -20.21% | -2.60 | -19.4% | 2026*: -16.0% |

## Spread measurements and price cross-check

Each entry is the **median full bid/ask spread in basis points of midpoint** from Exness Standard minute bars between 12:00 and 16:00 UTC in that calendar year. The simulation conservatively pays that full spread on each one-way rebalance trade. Exact precision and quote counts are in [results.json](results.json).

| Year | EURUSD | GBPUSD | USDJPY | XAUUSD | US500 | USTEC | DE30 | UK100 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2015 | — | — | — | 4.14 | — | — | — | — |
| 2016 | 1.05 | 1.07 | 1.07 | 3.79 | — | — | — | — |
| 2017 | 1.10 | 1.01 | 1.15 | 1.99 | — | — | — | — |
| 2018 | 0.98 | 1.00 | 1.10 | 1.75 | — | — | — | — |
| 2019 | 0.91 | 1.17 | 1.01 | 1.77 | 4.54 | 4.38 | 4.72 | 4.26 |
| 2020 | 0.88 | 1.16 | 1.03 | 1.66 | 4.13 | 4.32 | 4.81 | 10.75 |
| 2021 | 0.84 | 0.87 | 0.99 | 1.55 | 3.67 | 3.26 | 3.55 | 7.95 |
| 2022 | 0.93 | 0.88 | 0.80 | 1.11 | 3.75 | 3.57 | 4.05 | 7.82 |
| 2023 | 0.92 | 0.93 | 0.77 | 1.03 | 3.50 | 3.18 | 3.61 | 7.88 |
| 2024 | 0.92 | 0.94 | 0.70 | 0.84 | 3.21 | 2.91 | 3.27 | 7.51 |
| 2025 | 0.78 | 0.79 | 0.67 | 0.48 | 0.95 | 0.86 | 3.30 | 7.41 |
| 2026 to Sep | 0.69 | 0.74 | 0.63 | 0.59 | 1.03 | 0.83 | 0.64 | 1.36 |

Earlier years use the **first available** Exness spread year per market, especially 2019 for indices; these are assumptions, not measured old quotes. Five B12 instruments lack supplied minute files, so their fixed spread proxies are stated in [research.py](research.py). At Friday decisions where both Yahoo and Exness midpoint histories had 252 observations, the resulting aggregate trend sign matched **95.5% EURUSD, 91.8% GBPUSD, 92.6% USDJPY, 97.7% gold, 98.1% US500, 96.6% USTEC, 99.1% DE30 and 99.1% UK100** of weeks. This supports signal comparability; it does not validate Yahoo's exact CFD P&L, dividends, or 16:00 execution price.

## EUR 1,000 lot-size gate

For the last *executed* weekly rebalance, 25 September 2026, desired notionals below use EUR 1,000 equity. Minimum notionals use [Exness's published contract sizes and minimum lots](https://get.exness.help/hc/en-us/articles/17854383867548-Indices), [FX lot size](https://get.exness.help/hc/en-us/articles/360014740179-Common-trading-terms), [gold terms](https://get.exness.help/hc/en-us/articles/17854173039388-Commodities), Exness minute mids, and EURUSD conversion at about 1.14. Figures are indicative EUR equivalents.

| Instrument | Desired direction / EUR notional | Standard minimum lot | Approx. minimum EUR notional |
|---|---:|---:|---:|
| EURUSD | Short 579 | 0.01 | 1,000 |
| GBPUSD | Short 579 | 0.01 | 1,162 |
| USDJPY | Short 121 | 0.01 | 877 |
| XAUUSD | Long 47 | 0.01 | 3,764 |
| US500 | Long 301 | 0.14 | 950 |
| USTEC | Long 168 | 0.05 | 1,343 |
| DE30 | Long 86 | 0.07 | 1,784 |
| UK100 | Long 119 | 0.05 | 623 |

Opening minimum tickets with leverage would replace the planned risk weights with much larger bets. [Standard Cent](https://get.exness.help/hc/en-us/articles/17537782786588-Standard-Cent-account) can make FX and gold small enough, but it does **not** list DE30/UK100. The newer [Exness index specification](https://get.exness.help/hc/en-us/articles/17854383867548-Indices) says US500/USTEC are available on Cent through MT5/Exness platforms, while its generic text and the Cent account list disagree; the live terminal must confirm those contract details. The account-by-instrument minima are collected in [RESEARCH.md](RESEARCH.md). Cent cannot replicate the declared eight-market book regardless because DE30 and UK100 are absent. Residence can also affect Exness availability.

## Interpretation and limitations

The swap-free proposition is conditional: [Exness says](https://get.exness.help/hc/en-us/articles/4402341895570-Swap-free-status) sustained large overnight holdings can lose status, without a public numeric threshold, and swaps then apply to existing as well as future positions. The 8% case is a **scenario**, not an Exness historical swap reconstruction; actual directional rates may be lower or higher, and the published current rates for four requested symbols cannot fill past decades. The zero-swap case remains an optimistic upper bound for a months-long trend book.

The Yahoo proxies also omit CFD index dividend adjustments, non-USD index translation, live order slippage, changing margin requirements, stop-out mechanics, and any payment or account-specific costs. Spreads measured at 12:00–16:00 UTC can differ from spreads at a later Yahoo closing signal, especially near a market break. GLD and QQQ are ETFs rather than spot gold or the Nasdaq index; [the `^GDAXI` DAX series is a performance index that includes dividends](https://stoxx.com/index/DAX/?d=2026-07&factsheet=true). The long comparison uses unlevered equal weights, so it does not have the same risk budget as the trend strategy. The return analysis assumes continuous position sizes and therefore **cannot establish executable EUR 1,000 performance**. Neither the modest zero-swap gain nor the academic futures evidence overcomes these gaps and the Standard-lot failure. No exact demo portfolio is proposed because the tested idea did not pass the hold-out and sizing gates.
