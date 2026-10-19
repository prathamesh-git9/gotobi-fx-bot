# Round 3: invent and test NEW scheduled-flow / calendar edges. Be creative but honest.

Work only in this folder; do not read other code or results in this repository except the data listed here.

Data (read only, UTC 1-minute bid/ask bars, Exness Standard feed, columns bopen bhigh blow bclose aopen ahigh alow
aclose; pip = 0.01 for JPY pairs, 0.0001 for other FX):
- E:/Projects/New folder/liquidity_sweep/data/: EURUSDm_m1, GBPUSDm_m1, USDJPYm_m1, XAUUSDm_m1 (2019-01..2026-09),
  EURUSDm_2016_m1, GBPUSDm_2016_m1, USDJPYm_2016_m1 (2016-2018), XAUUSDm_2015_m1 (2015-08..2018),
  US500m/US30m/USTECm/DE30m/UK100m_m1 (2019-08..2026-09), daily_yahoo.parquet (daily closes: date, sym, close),
  events_calendar.csv (FOMC statement times, BoJ decision dates), histdata/USDJPY_hd_model_2006_2015_m1.parquet.
- E:/Projects/New folder/liquidity_sweep/strategies/explore/data/: EURJPYm, AUDJPYm, AUDUSDm, USDCNHm, XAGUSDm
  (2016-01..2026-09), BTCUSDm (2019-01..2026-09), _m1.parquet.
python 'holidays' package is installed.

ALREADY TESTED, do not repeat: USD/JPY gotobi (5/10/15/20/25/30 Tokyo fix) and gotobi on EUR/JPY and AUD/JPY;
month-end London 4 pm fix in all these pairs and gold; 4 pm fix reversal; gold London and Shanghai auctions; silver
fix; US500/DAX/FTSE month-end and quarter-end closes; index expiry auctions; index quarterly rebalances; pre-FOMC
drift; pre-holiday US500; Japanese toshin early-month; March/September Japan year-end; weekend gaps; BoJ days;
USDCNH fix and month-end; Bitcoin CME gap, funding times, ETF 4 pm NAV, monthly expiry; turn of the month; US open gap.

Do: propose up to 10 NEW ideas, each with an economic reason (a forced, scheduled or mechanical flow). Write the
exact rules in RULES.md BEFORE computing any returns. Then test:
- Real spread (bid/ask), bar opens, stop wins if a bar touches stop and target.
- Choose any free parameter on 2016-2021 (2019-2021 where data starts later), judge ONCE on 2022-2026-09-30.
- Control: the same trade at ordinary days/times. Bonferroni across all your ideas.
- For survivors: per-year pips and EUR 1,000 compounded at 2% risk from 2016 and from 2025-01-01.
Write research.py and REPORT.md (every idea, including failures; honest verdict).
