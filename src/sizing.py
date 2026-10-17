"""What does risk-per-trade do to a EUR 100 account running Gold Asia Night?

Monte Carlo (trades drawn with replacement from a real trade history) for 1 and 3 years at
~50 trades/year, for several risk levels and three edge scenarios:
  good    last 3 years at real costs              (+0.14R, 74% win)
  typical 2016-2026 at today's spread             (all years, good and bad)
  bad     2022 alone + 2016 (the losing years)
Also: Kelly fraction, broker lot/leverage feasibility for EUR 100, and Irish CGT.
"""
import numpy as np
import pandas as pd

RNG = np.random.default_rng(7)
EUR0, EURUSD = 100.0, 1.17
TRADES_PER_YEAR = 50
RISKS = [0.01, 0.02, 0.05, 0.10, 0.15, 0.20]
CGT, EXEMPT = 0.33, 1270.0

w = pd.read_parquet("../results/asia_night_trades.parquet")
scen = {
    "good (last 3y, real costs)": w[w.day >= "2023-10-01"]["r_actual"].to_numpy(),
    "typical (2016-26, today's spread)": w["r_modern"].to_numpy(),
    "bad (2016 + 2022 only)": w[w.y.isin([2016, 2022])]["r_modern"].to_numpy(),
}


def kelly(r):
    fs = np.linspace(0, 0.6, 601)
    g = [np.mean(np.log1p(f * r)) if np.all(1 + f * r > 0) else -np.inf for f in fs]
    return fs[int(np.argmax(g))]


def sim(r, risk, years, n=20000):
    k = TRADES_PER_YEAR * years
    draws = RNG.choice(r, (n, k))
    paths = EUR0 * np.cumprod(1 + risk * draws, axis=1)
    peak = np.maximum.accumulate(np.concatenate([np.full((n, 1), EUR0), paths], 1), axis=1)[:, 1:]
    dd = (1 - paths / peak).max(1)
    end = paths[:, -1]
    if years >= 1:  # CGT once a year on gains above the exemption (approximation: on the final gain)
        gain = end - EUR0
        end = end - CGT * np.maximum(0, gain / years - EXEMPT) * years
    return end, dd


print("Kelly-optimal risk per trade (maximises long-run growth; real traders use half or less):")
for name, r in scen.items():
    print(f"  {name:36s} n={len(r):4d} avg {r.mean():+.3f}R win {np.mean(r > 0):.0%}  Kelly {kelly(r):.0%}")

for name, r in scen.items():
    print(f"\n=== {name} ===")
    print(f"{'risk':>5} | {'median 1y':>9} {'median 3y':>9} | {'P(3y < 100)':>11} {'P(3y < 50)':>10} {'P(3y < 20)':>10} | {'median maxDD':>12} {'5% worst 3y':>11} {'95% best 3y':>11}")
    for risk in RISKS:
        e1, _ = sim(r, risk, 1)
        e3, dd = sim(r, risk, 3)
        print(f"{risk:>5.0%} | EUR{np.median(e1):>6,.0f} EUR{np.median(e3):>6,.0f} | {np.mean(e3 < 100):>11.0%} "
              f"{np.mean(e3 < 50):>10.0%} {np.mean(e3 < 20):>10.0%} | {np.median(dd):>12.0%} "
              f"EUR{np.percentile(e3, 5):>8,.0f} EUR{np.percentile(e3, 95):>8,.0f}")

# feasibility of the position size with EUR 100
atr_now = w[w.day >= "2026-01-01"].atr.median()
price_now = w[w.day >= "2026-01-01"].entry.median()
stop = 0.3 * atr_now
print(f"\nPosition size today: gold ~${price_now:,.0f}, daily ATR ~${atr_now:.0f}, stop 0.3xATR = ${stop:.1f}/oz")
for risk in (0.02, 0.05, 0.10):
    usd = EUR0 * EURUSD * risk
    oz = usd / stop
    notional = oz * price_now
    print(f"  risk {risk:.0%}: ${usd:.2f} at risk -> {oz:.2f} oz = {oz / 100:.4f} lots; notional ${notional:,.0f} "
          f"= {notional / (EUR0 * EURUSD):.0f}x leverage")
print("  Exness Standard minimum is 0.01 lot = 1 oz (risk ${:.0f} = {:.0%} of EUR 100). The Standard Cent account trades 0.01 oz."
      .format(stop, stop / (EUR0 * EURUSD)))
print("  EU retail leverage cap on gold is 1:20 -> max ~{:.2f} oz with EUR 100 (= {:.1%} risk).".format(
    EUR0 * EURUSD * 20 / price_now, EUR0 * EURUSD * 20 / price_now * stop / (EUR0 * EURUSD)))
