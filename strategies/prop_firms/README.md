# Bot-friendly instant-funding accounts for the gotobi bot

Rules were read from each firm's own pages on 21 Oct 2026. Simulation: [prop_multi.py](prop_multi.py), using the
bot's real trades re-priced minute by minute on Exness bid/ask.

## Firms checked

| Firm / account | Price ($5K) | Bots | Loss limit | Daily limit | Risk cap | Split |
|---|---:|---|---|---|---|---:|
| [FundedNext Stellar Instant](https://fundednext.com/cfds/stellar-instant) | $149.99 + paid EA add-on (price not published) | yes, MT4/MT5, with the add-on | 6% trailing from the highest balance, stops at the start; withdrawals do not reset it | none | 3% of start at any time (breaking it: warning + profit deducted) | 70% (80% from tier 3) |
| [Instant Funding PRO](https://instantfunding.com/help/instant-funding-program/) | $239 (live page) | own EAs yes; public third-party EAs restricted; holds ≤ 60 s count as HFT | 10% of start, fixed at −5% once +5% | none | 3% per trade idea (hard breach) | 80% |
| [Funded Friday Instant](https://fundedfriday.com/trading-rules) | $10K = $159 | **no EAs** | 5% trailing equity + 1% floating limit | 3% trailing | – | 80% |
| The5ers Hyper Growth | – | own EA only with written approval | 6% / daily 3% | | | 75% |
| FundingPips Zero | site refused automated reading | | | | | |

- The5ers Hyper Growth is a one-step challenge (10% target), not instant funding.
- All of these firms say their accounts are simulated and payouts are at their discretion.

**For your plan:**
- 10% of EUR 2,000 is about $230 a trade, which breaks both 3% caps, so it is **not allowed**.
- 6% of EUR 2,000 is about $140, which fits under the cap.
- Other edge cases:
  - **News:** FundedNext counts profits made within ±5 minutes of high-impact news at 40%; Instant Funding
    restricts trades within ±4 minutes without its "Swing" add-on. The bot's times are 15:55 and 00:54–01:25 UTC.
  - **Weekends:** the bot never holds over the weekend.
  - **Commission:** the firms' commission or spread is not modelled. $5/lot would cost about 0.015R a trade,
    roughly a third of the gotobi edge.

## Results, $5K account, fixed risk per trade (no compounding inside a prop account)

| Risk per trade | 2026 so far: NET after fees (payouts) | Last 2 yrs NET (accounts lost) | Last 10 yrs NET (accounts lost) | Chance of losing the account within a year |
|---|---:|---:|---:|---:|
| **Instant Funding PRO** | | | | |
| $50 (= 6% of EUR 720) | −$71 ($168; $223 still in account) | +$569 (0) | +$2,224 (0) | 0% |
| $75 (= 6% of EUR 1,080) | +$113 ($352) | +$1,031 (1) | +$3,514 (1) | 8% |
| **$100 (= 6% of EUR 1,440)** | **+$323** ($562) | +$1,533 (1) | **+$4,845 (1)** | **10%** |
| $140 (= 6% of EUR 2,000) | +$628 ($867) | +$2,398 (2) | +$6,721 (6) | 35% |
| $150 (cap) | +$704 ($943) | +$2,598 (2) | +$7,191 (6) | 38% |
| **FundedNext Stellar Instant** (before the EA add-on fee) | | | | |
| $25 (= 6% of EUR 360) | −$150 (no payout yet) | +$72 (0) | +$737 (0) | 0% |
| $50 (= 6% of EUR 720) | −$68 ($82) | +$341 (1) | +$1,902 (0) | 8% |
| $100 (= 6% of EUR 1,440) | +$285 ($435) | +$1,158 (3) | +$3,431 (7) | 50% |
| $140 (= 6% of EUR 2,000) | +$394 ($694; lost 1 account) | +$1,943 (4) | +$4,128 (17) | 82% |

The "chance of losing the account" column comes from a fresh account started at the beginning of each month,
Nov 2016 – Oct 2025, and kept for 12 months.

**Verdict:**
- **Instant Funding PRO suits this bot better than FundedNext**: a 10% static floor instead of 6% trailing, 80% split,
  own EAs allowed, no EA add-on.
- **About $100 a trade** (= 6% of a EUR 1,440 "virtual" account) is the balance point. It would have lost one account
  in 10 years and has a ~10% chance of losing one in a given year.
- At 6% of EUR 2,000 ($140), 2026 would have paid +$628, but in a typical year the account is lost about a third of
  the time.
- For comparison, your own EUR 2,000 at 6% on Exness made EUR 3,253 (+63%) in 2026, with your own money at risk.
