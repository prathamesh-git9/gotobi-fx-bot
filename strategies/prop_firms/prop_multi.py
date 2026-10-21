"""Bot-friendly instant-funding accounts: the gotobi bot's real trades run through each firm's published rules,
minute by minute, at several fixed risks per trade - to find the largest risk that would not have breached.

Rules read from the firms' own pages on 21 Oct 2026 (see README.md):
 FundedNext Stellar Instant $5K - fee $149.99 (+ a paid EA add-on, price not published); EAs allowed on MT5;
   6% trailing maximum loss from the highest balance, which stops at the starting balance; no daily limit;
   at most 3% of the starting balance at risk at any time; 70% profit split (80% from tier 3); withdrawals on demand
   once growth >= 5%; withdrawals do NOT reset the loss limit.
 Instant Funding PRO $5K - fee $239 (live page); own EAs allowed (public third-party EAs restricted);
   loss limit 10% of the start, fixed at -5% once the balance is +5%; no daily limit; max 3% risk per trade idea
   (hard breach); 80% split; first payout 14 days after the first trade, then weekly; must be flat and locked.
Assumptions where the pages are silent or conflict (all conservative): breaches are checked on equity at the worst
price of every minute; my payout policy keeps a cushion equal to the original loss buffer (FundedNext: withdraw
above start + $300; Instant Funding: withdraw above start + $250, which keeps the $500 buffer to the locked floor);
a breached account is replaced by a new one (another fee); costs are Exness's (the firms' own feeds may differ).

  python strategies/prop_firms/prop_multi.py
"""
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "strategies" / "prop_fundedfriday"))
from prop_sim import server_day, trade_paths, usdjpy  # noqa: E402

SIZE = 5000.0


@dataclass
class Firm:
    name: str
    fee: float
    split: float
    risk_cap: float                    # max risk per trade (USD)


FN = Firm("FundedNext Stellar Instant $5K", 149.99, 0.70, 0.03 * SIZE)
IF = Firm("Instant Funding PRO $5K", 239.0, 0.80, 0.03 * SIZE)


def floor_of(firm, hb, locked):
    if firm is FN:
        return min(hb - 0.06 * SIZE, SIZE)                       # trails the highest balance, stops at the start
    return SIZE * 0.95 if locked else SIZE * 0.90                # Instant Funding Smart Drawdown


def simulate(paths, firm, risk, start, end):
    paths = [p for p in paths if start <= p[5] < end]
    fees = paid = 0.0
    accounts = breaches = payouts = 0
    acc = None
    log = []
    for ts, worst, best, close, r_final, closed in paths:
        t0 = pd.Timestamp(ts[0])
        if acc is None:
            acc = dict(bal=SIZE, hb=SIZE, locked=False, first=t0, next_pay=t0 + pd.Timedelta(days=14))
            accounts += 1
            fees += firm.fee
        # payouts that fall before this trade (we are flat between trades)
        if firm is FN:
            if acc["bal"] - SIZE >= 0.05 * SIZE and acc["bal"] > SIZE + 0.06 * SIZE + 100:
                w = acc["bal"] - (SIZE + 0.06 * SIZE)
                acc["bal"] -= w
                paid += firm.split * w
                payouts += 1
                log.append((t0, "payout", round(firm.split * w, 2)))
        else:
            while acc["next_pay"] <= t0:
                if acc["locked"] and acc["bal"] - (SIZE + 0.05 * SIZE) >= 25:
                    w = acc["bal"] - (SIZE + 0.05 * SIZE)
                    acc["bal"] -= w
                    paid += firm.split * w
                    payouts += 1
                    log.append((acc["next_pay"], "payout", round(firm.split * w, 2)))
                acc["next_pay"] += pd.Timedelta(days=7)
        fl = floor_of(firm, acc["hb"], acc["locked"])
        lo = acc["bal"] + worst * risk
        if (lo < fl).any():
            breaches += 1
            log.append((t0, "BREACH", round(acc["bal"] - SIZE, 2)))
            acc = None
            continue
        acc["bal"] += r_final * risk
        acc["hb"] = max(acc["hb"], acc["bal"])
        if acc["bal"] >= SIZE * 1.05:
            acc["locked"] = True
    open_profit = (acc["bal"] - SIZE) if acc else 0.0
    return dict(firm=firm.name, risk=risk, accounts=accounts, breaches=breaches, payouts=payouts, fees=round(fees),
                paid=round(paid), net=round(paid - fees), unpaid=round(open_profit)), log


def main():
    trades = pd.read_csv(ROOT / "strategies" / "edge7" / "gotobi_bot_trades_2016_2026.csv")
    trades["closed_ts"] = pd.to_datetime(trades.closed, utc=True).dt.tz_convert(None)
    trades = trades.sort_values("closed_ts").reset_index(drop=True)
    paths = trade_paths(trades, usdjpy())
    eur_usd = 1.16
    windows = {"2026 (1 Jan - 20 Oct)": ("2026-01-01", "2026-10-21"), "last 2 years": ("2024-10-20", "2026-10-21"),
               "last 10 years": ("2016-10-20", "2026-10-21")}
    rows = []
    for firm in (FN, IF):
        print(f"\n######## {firm.name}: fee ${firm.fee}, split {firm.split:.0%}, max risk per trade ${firm.risk_cap:.0f}")
        for risk in (25, 50, 75, 100, 140, 150):
            label = f"${risk}/trade (= 6% of EUR {risk / 0.06 / eur_usd:,.0f})"
            for wn, (a, b) in windows.items():
                s, log = simulate(paths, firm, risk, pd.Timestamp(a), pd.Timestamp(b))
                s.update(window=wn)
                rows.append(s)
                print(f"  {label:34} {wn:22}: accounts {s['accounts']:2} (breached {s['breaches']:2}), payouts {s['payouts']:3} = "
                      f"${s['paid']:>7,}  fees ${s['fees']:>6,}  NET ${s['net']:>+8,}  | still in account ${s['unpaid']:>+6,}")
    # survival: every 12-month window starting each month 2016-11 .. 2025-10
    print("\n######## Survival check: a fresh account started at the beginning of each month, kept for 12 months")
    starts = pd.date_range("2016-11-01", "2025-10-01", freq="MS")
    for firm in (FN, IF):
        for risk in (25, 50, 75, 100, 140, 150):
            res = [simulate(paths, firm, risk, st, st + pd.DateOffset(years=1))[0] for st in starts]
            br = np.mean([r["breaches"] > 0 for r in res])
            net = np.array([r["net"] for r in res])
            rows.append(dict(firm=firm.name, risk=risk, window="every 12-month start", p_breach=float(br),
                             median_net=float(np.median(net)), worst_net=float(net.min())))
            print(f"  {firm.name:32} ${risk:3}/trade: breached within the year in {br:4.0%} of {len(res)} starts, "
                  f"median NET ${np.median(net):>+6,.0f}, worst ${net.min():>+6,.0f}, best ${net.max():>+6,.0f}")
    pd.DataFrame(rows).to_csv(HERE / "prop_multi_results.csv", index=False)


if __name__ == "__main__":
    main()
