"""Instant Funding IF Micro PRO (rules read 21 Oct 2026 from instantfunding.com/help/if-micro/ and linked pages):
6% static max loss from the starting balance; 4% daily loss of the higher of balance/equity at the 17:00 New York
rollover; at most 1% of the starting balance at risk per trade idea (hard breach); own EAs allowed; news, overnight and
weekend holding allowed; payouts on demand once net profit >= 5% and the best day <= 15% of the cycle's profit; 80%
split. Prices on the live page: $5K $53, $10K $109, $25K $234, $50K $439, $100K $813.

The gotobi bot's real trades, re-priced minute by minute (worst price checked for breaches), risk a fixed share of the
starting balance per trade. Payout policy: whenever eligible, withdraw all profit (the static floor makes the account
exactly as safe as on day one again). Mode 'hold': no withdrawal until the end of the window.

  python strategies/prop_firms/prop_micro.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "strategies" / "prop_fundedfriday"))
from prop_sim import server_day, trade_paths, usdjpy  # noqa: E402

PRICES = {5000: 53, 10000: 109, 25000: 234, 50000: 439, 100000: 813}


def eligible(profit, days, size):
    return profit >= 0.05 * size and days and max(days.values()) <= 0.15 * profit


def simulate(paths, size, risk_pct, start, end, hold=False):
    fee = PRICES[size]
    risk = risk_pct * size
    floor = 0.94 * size
    fees = paid = 0.0
    accounts = breaches = payouts = 0
    acc = None
    for ts, worst, best, close, r, closed in paths:
        if not (start <= closed < end):
            continue
        if acc is None:
            acc = dict(bal=size, days={}, day=None, day_base=size)
            accounts += 1
            fees += fee
        if not hold and eligible(acc["bal"] - size, acc["days"], size):
            w = acc["bal"] - size
            paid += 0.8 * w
            payouts += 1
            acc["bal"], acc["days"] = size, {}
        breached = False
        for k in range(len(ts)):
            d = server_day(ts[k])
            if d != acc["day"]:
                acc["day"] = d
                acc["day_base"] = max(acc["bal"], acc["bal"] + (close[k - 1] * risk if k else 0.0))
            eq_lo = acc["bal"] + worst[k] * risk
            if eq_lo < floor or eq_lo < acc["day_base"] * 0.96:
                breached = True
                break
        if breached:
            breaches += 1
            acc = None
            continue
        pnl = r * risk
        acc["bal"] += pnl
        dd = server_day(closed)
        acc["days"][dd] = acc["days"].get(dd, 0.0) + pnl
    end_profit = (acc["bal"] - size) if acc else 0.0
    can_take = bool(acc) and eligible(end_profit, acc["days"], size)
    return dict(size=size, fee=fee, risk=risk, accounts=accounts, breaches=breaches, payouts=payouts, fees=fees,
                paid=paid, end_profit=end_profit, can_take=can_take,
                best_day=max(acc["days"].values()) if acc and acc["days"] else 0.0)


def main():
    t = pd.read_csv(ROOT / "strategies" / "edge7" / "gotobi_bot_trades_2016_2026.csv")
    t["closed_ts"] = pd.to_datetime(t.closed, utc=True).dt.tz_convert(None)
    paths = trade_paths(t.sort_values("closed_ts"), usdjpy())
    eur = 1.16
    a26, b26 = pd.Timestamp("2026-01-01"), pd.Timestamp("2026-10-21")
    starts = pd.date_range("2016-11-01", "2025-10-01", freq="MS")
    for rp in (0.0098, 0.0075):
        print(f"\n######## IF Micro PRO, risk {rp:.2%} of the starting balance per trade")
        for size in PRICES:
            h = simulate(paths, size, rp, a26, b26, hold=True)
            take = 0.8 * h["end_profit"]
            note = "eligible to withdraw now" if h["can_take"] else f"NOT yet eligible (best day ${h['best_day']:,.0f} > 15% of profit)"
            two = simulate(paths, size, rp, pd.Timestamp("2024-10-20"), b26)
            ten = simulate(paths, size, rp, pd.Timestamp("2016-10-20"), b26)
            yr = [simulate(paths, size, rp, st, st + pd.DateOffset(years=1), hold=True) for st in starts]
            pb = np.mean([y["breaches"] > 0 for y in yr])
            print(f"  ${size:>7,} (fee ${h['fee']:>3}, ${h['risk']:,.0f}/trade) | 2026 no withdrawals: "
                  + (f"profit ${h['end_profit']:>6,.0f} -> your 80% ${take:>6,.0f} = EUR {take / eur:>5,.0f}, after fee EUR {(take - h['fee']) / eur:>5,.0f} ({note})"
                     if h["breaches"] == 0 else "ACCOUNT LOST in 2026")
                  + f" | 2 yrs net ${two['paid'] - two['fees']:>+7,.0f} ({two['breaches']} lost) | 10 yrs net ${ten['paid'] - ten['fees']:>+8,.0f} ({ten['breaches']} lost)"
                  + f" | lost within a year in {pb:.0%} of 108 starts")


if __name__ == "__main__":
    main()
