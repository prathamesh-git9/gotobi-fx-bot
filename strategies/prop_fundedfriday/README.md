# Our strategies on a Funded Friday "Instant Fund" account

## The rules (fundedfriday.com, read 20 Oct 2026)

Sources: the /trading-rules "Instant Funded" tab and the Instant Fund FAQ, rendered in a browser.

**Sizes and fees:** $10K for $159, $25K for $299, $50K for $499. There is **no $5K Instant account**. The site
currently shows a 30%-off code (FESTIVE30). Platform MT5; leverage FX/indices 1:50.

**Breach (the account is closed):**
- equity (balance + floating) more than **5% below its all-time high**. The limit trails the high and never moves
  down;
- equity more than **3% below the day's highest equity**;
- a **floating loss above 1% of the account size** at any moment ($100 on $10K).

**Soft rules:**
- a stop-loss within 1 minute of opening a trade;
- hold every trade at least 60 s;
- at most 5 trades stacked on one pair;
- close everything before the weekend;
- trade at least once every 30 days.

**Bots: "No, you cannot use EA bots in your Instant Fund account."** Orders sent through the MT5 Python API (our
bot) are recorded by MT5 as automated, not manual, so the firm can see them.

**Payout** (weekly on Fridays; the first one at least 7 days after the first trade):
- profit ≥ 5% of the account ($500);
- at least 7 days in the cycle each with ≥ 0.25% profit ($25);
- no single day more than 15% of the cycle's profit;
- at most 20% of the account per cycle;
- you receive 80%.

**The company:** Funded Friday LTD, Saint Lucia, registration number 2026-00063. The site says trading is
simulated and payouts are "discretionary and are not guaranteed". The terms still contain unfilled placeholders
("[Jurisdiction]", "[Arbitration Body]").

## Simulation

Scripts: [prop_sim.py](prop_sim.py) (gotobi) and [prop_nasdaq.py](prop_nasdaq.py) (NASDAQ momentum).

How it works:
- Every minute of every trade is re-priced from real Exness bid/ask bars.
- The trailing highs use the best price; the breach checks use the worst.
- Payouts are checked every Friday with all the rules above.
- A breached account is replaced by a new one, paying another fee.
- Risk per trade is a fixed dollar amount, since a prop account does not compound.
- Assumed where the site is silent:
  - the day resets at 22:00 UTC;
  - after a payout the trailing high resets to the new balance;
  - costs are Exness's. The firm does not publish its spreads; "+1 pip" is a stress test.

### Gotobi bot trades, $10K account

The bot is banned there, so this assumes the same trades placed by hand.

| Risk per trade | Last 10 yrs: accounts (breached), payouts, NET after fees | Last 2 yrs: NET | Every 2-yr window: median NET, % losing the fee |
|---|---|---:|---|
| $25 | 1 (0), **0 payouts**, −$159 | −$159 | −$159, 100% |
| $50 | 1 (0), 6 payouts, +$2,292 | +$698 | +$244, 45% |
| **$65 (≈ 6% of EUR 1,000)** | 1 (0), 8 payouts, **+$3,286** | **+$784** | +$262, 33% |
| $90 | 2 (1), 10 payouts, +$4,525 | +$1,212 | +$282, 12% |
| $65, +1 pip cost | 2 (1), 5 payouts, +$1,818 | +$622 | – |

Edge cases the rules create:
- **$25 a trade is never paid.** No day reaches $25 profit, so the 7-day rule is never met: +$1,635 of profit sits
  unpaid after 10 years.
- At $65 a trade, a take-profit day (+$35) qualifies, and the first payout takes about 6 months.
- The 1% floating limit caps risk below $100 a trade. $90 works, but leaves almost no room for slippage.

For comparison, your own EUR 1,000 at 6%, compounding on Exness, grows to EUR 3,873 in the last 2 years and EUR 37,115
in 10, with a 37% worst drop. That compounding is something a fixed-size prop account cannot do.

### NASDAQ noise-area momentum, $10K account

Every position has a $90 stop. The data starts in Aug 2019, so the long window is 7 years.

| Size (leverage × capital C) | 7 yrs: accounts (breached), NET | Last 2 yrs: NET | Every 2-yr window: median NET, % losing |
|---|---|---:|---|
| C = $1,100 (≈ EUR 1,000) | 1 (0), 1 payout, +$353 | −$159 | −$159, 80% |
| C = $2,500 | 2 (1), +$1,271 | −$318 | +$247, 41% |
| C = $5,000 | 7 (6), +$1,387 | −$636 | +$202, 26% |
| C = $10,000 | 36 (35), −$2,712 | −$2,226 | −$814, 62% |

**Verdict:** NASDAQ momentum does not suit this account. Sized small it is too slow to reach the $500 hurdle; sized
bigger it keeps breaching. It loses in the last 2 years at every size.
