"""Funded Friday "Instant Fund" rules applied to our strategies, minute by minute.

Rules as published on fundedfriday.com (read 20 Oct 2026: /trading-rules "Instant Funded" tab and the Instant Fund FAQ):
  sizes $10K / $25K / $50K (no 5K), fee $159 / $299 / $499; profit split 80%; MT5; leverage FX/indices 1:50.
  Breach (account closed):  equity more than 5% below its all-time high (balance + floating, trailing, never moves
                            down); equity more than 3% below the day's highest equity; a floating loss above 1% of the
                            account size at any moment.
  Soft rules: stop-loss within 1 minute, hold >= 60 s, <= 5 trades stacked per pair. "No, you cannot use EA bots in your
  Instant Fund account." Weekend: close by Friday 23:00 UTC.
  Payout (weekly, Fridays; first one >= 7 days after the first trade): profit >= 5% of the account size; >= 7 trading
  days in the cycle each with >= 0.25% profit; best day <= 15% of the cycle's profit; at most 20% of the account size
  per cycle; you receive 80%.
Assumptions where the site is silent: the trading day resets at 22:00 UTC (MT5 server midnight); after a payout the
withdrawn profit leaves the account and the trailing high resets to the new balance; a breached account is replaced
by a new one (another fee) at the next trade; spreads/costs as on Exness (the firm's own costs are not published).

Gotobi: the bot's own replay trade list (strategies/edge7/gotobi_bot_trades_2016_2026.csv: entry/exit times and
prices, R per trade against the 55-pip stop), with every minute of each trade re-priced from USDJPY bid/ask bars so
that floating losses, the trailing high (on the best price) and the breach checks (on the worst price) are exact.
Risk per trade is a FIXED dollar amount (the account does not compound).

  python strategies/prop_fundedfriday/prop_sim.py
"""
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = ROOT / "data"
STOP = 0.55                       # the bot's 55-pip stop, in yen
TP_R = 30 / 55

SIZE, FEE = 10_000.0, 159.0
MAX_DD, DAY_DD, FLOAT = 0.05 * SIZE, 0.03 * SIZE, 0.01 * SIZE
MIN_PROFIT, DAY_MIN, MIN_DAYS, CONSIST, CAP, SPLIT = 0.05 * SIZE, 0.0025 * SIZE, 7, 0.15, 0.20 * SIZE, 0.80


def usdjpy():
    parts = [pd.read_parquet(DATA / f"{f}_m1.parquet", columns=["bhigh", "blow", "bclose", "ahigh", "alow", "aclose"])
             for f in ("USDJPYm_2016", "USDJPYm", "USDJPYm_2026_10")]
    df = pd.concat(parts).sort_index()
    return df[~df.index.duplicated()]


def trade_paths(trades, px):
    """For each trade: minute timestamps, worst / best / closing floating R in each minute, final R, close time."""
    t_idx = px.index.values
    out = []
    for r in trades.itertuples():
        o = np.datetime64(pd.Timestamp(r.opened).tz_convert(None))
        c = np.datetime64(pd.Timestamp(r.closed).tz_convert(None))
        i, j = np.searchsorted(t_idx, o), np.searchsorted(t_idx, c)
        if j - i < 1:                                   # no minute data (the last days): use the result only
            ts = np.array([c])
            worst = np.array([min(r.r, 0.0)])
            best = np.array([max(r.r, 0.0)])
            close = np.array([r.r])
        else:
            ts = t_idx[i:j]
            if r.trade == "long":
                worst = (px.blow.values[i:j] - r.entry) / STOP
                best = np.minimum((px.bhigh.values[i:j] - r.entry) / STOP, TP_R)
                close = (px.bclose.values[i:j] - r.entry) / STOP
            else:
                worst = (r.entry - px.ahigh.values[i:j]) / STOP
                best = (r.entry - px.alow.values[i:j]) / STOP
                close = (r.entry - px.aclose.values[i:j]) / STOP
            worst = np.maximum(worst, min(r.r, -1.0))     # the stop closes the trade
        out.append((ts, worst, best, close, r.r, pd.Timestamp(r.closed).tz_convert(None)))
    return out


def server_day(ts):
    return (pd.Timestamp(ts) + pd.Timedelta(hours=2)).normalize()   # day starts 22:00 UTC


@dataclass
class Account:
    start: pd.Timestamp
    balance: float = SIZE
    hwm: float = SIZE
    day: pd.Timestamp = None
    day_hwm: float = SIZE
    first_trade: pd.Timestamp = None
    daily: dict = field(default_factory=dict)       # server day -> realised profit this cycle
    payouts: int = 0


def simulate(paths, risk, start, end, extra_r=0.0, label=""):
    """Run the rules over [start, end). Returns a summary dict and the event log."""
    paths = [p for p in paths if start <= p[5] < end]
    fees, paid, accounts, breaches, npay = 0.0, 0.0, 0, 0, 0
    first_payout_days, log = [], []
    acc = None
    next_friday = None

    def try_payout(now):
        nonlocal paid, npay, acc
        if acc is None or acc.first_trade is None or (now - acc.first_trade).days < 7:
            return
        profit = acc.balance - SIZE
        if profit < MIN_PROFIT:
            return
        good = [v for v in acc.daily.values() if v >= DAY_MIN]
        if len(good) < MIN_DAYS or max(acc.daily.values()) > CONSIST * profit:
            return
        w = min(profit, CAP)
        paid += SPLIT * w
        npay += 1
        if acc.payouts == 0:
            first_payout_days.append((now - acc.start).days)
        acc.payouts += 1
        acc.balance -= w
        acc.hwm = acc.day_hwm = acc.balance
        acc.daily = {}
        log.append((now, "payout", round(SPLIT * w, 2)))

    for ts, worst, best, close, r_final, closed in paths:
        t0 = pd.Timestamp(ts[0])
        # Fridays (noon UTC) before this trade: payout checks
        while next_friday is not None and next_friday < t0:
            try_payout(next_friday)
            next_friday += pd.Timedelta(days=7)
        if acc is None:
            acc = Account(start=t0)
            accounts += 1
            fees += FEE
            log.append((t0, "buy account", -FEE))
            if next_friday is None:
                d = t0.normalize() + pd.Timedelta(hours=12)
                next_friday = d + pd.Timedelta(days=(4 - d.weekday()) % 7)
                if next_friday <= t0:
                    next_friday += pd.Timedelta(days=7)
        if acc.first_trade is None:
            acc.first_trade = t0
        breached = None
        for k in range(len(ts)):
            day = server_day(ts[k])
            if day != acc.day:                       # new trading day: its high starts at the equity right now
                acc.day = day
                acc.day_hwm = acc.balance + (close[k - 1] * risk if k else 0.0)
            hi = acc.balance + best[k] * risk
            lo = acc.balance + worst[k] * risk
            acc.hwm, acc.day_hwm = max(acc.hwm, hi), max(acc.day_hwm, hi)
            if worst[k] * risk < -FLOAT:
                breached = "floating loss > 1%"
            elif lo < acc.hwm - MAX_DD:
                breached = "5% trailing drawdown"
            elif lo < acc.day_hwm - DAY_DD:
                breached = "3% daily drawdown"
            if breached:
                break
        if breached:
            breaches += 1
            log.append((pd.Timestamp(ts[k]), f"BREACH: {breached}", round(acc.balance - SIZE, 2)))
            acc = None
            continue
        pnl = (r_final - extra_r) * risk
        acc.balance += pnl
        acc.hwm = max(acc.hwm, acc.balance)
        d = server_day(closed)
        acc.daily[d] = acc.daily.get(d, 0.0) + pnl
    if next_friday is not None:
        while next_friday < end:
            try_payout(next_friday)
            next_friday += pd.Timedelta(days=7)
    left = (acc.balance - SIZE) if acc else 0.0
    return dict(label=label, risk=risk, accounts=accounts, breaches=breaches, payouts=npay, fees=round(fees),
                paid=round(paid), net=round(paid - fees), open_profit_not_paid=round(left),
                first_payout_days=int(np.median(first_payout_days)) if first_payout_days else None), log


def own_account(trades, start, end, risk=0.06, cash=1000.0):
    x = trades[(trades.closed_ts >= start) & (trades.closed_ts < end)].r
    eq = cash * np.cumprod(1 + risk * x.to_numpy())
    peak = np.maximum.accumulate(np.r_[cash, eq])
    return round(eq[-1]), round(float((1 - np.r_[cash, eq] / peak).max()) * 100, 1)


def main():
    trades = pd.read_csv(ROOT / "strategies" / "edge7" / "gotobi_bot_trades_2016_2026.csv")
    trades["closed_ts"] = pd.to_datetime(trades.closed, utc=True).dt.tz_convert(None)
    trades = trades.sort_values("closed_ts").reset_index(drop=True)
    px = usdjpy()
    paths = trade_paths(trades, px)
    del px
    windows = {"last 10 years": (pd.Timestamp("2016-10-20"), pd.Timestamp("2026-10-21")),
               "last 2 years": (pd.Timestamp("2024-10-20"), pd.Timestamp("2026-10-21"))}
    rows = []
    print("Gotobi bot trades on a Funded Friday $10K Instant account (fee $159, 80% split), fixed risk per trade")
    for wname, (a, b) in windows.items():
        own, own_dd = own_account(trades, a, b)
        print(f"\n== {wname} ==   (for comparison: your own EUR 1,000 at 6% risk, compounding -> EUR {own:,}, "
              f"max drop {own_dd}%)")
        for extra, cost_name in ((0.0, "Exness costs"), (1 / 55, "+1 pip per trade")):
            for risk in (25, 50, 65, 90):
                s, log = simulate(paths, risk, a, b, extra_r=extra, label=f"{wname}, {cost_name}")
                rows.append(s)
                print(f"  {cost_name:16} risk ${risk:3}/trade: accounts bought {s['accounts']:2} (breached {s['breaches']:2}),"
                      f" payouts {s['payouts']:2} = ${s['paid']:>6,}  fees ${s['fees']:>5,}  NET ${s['net']:>+7,}"
                      f"  | unpaid profit at the end ${s['open_profit_not_paid']:>+5,}"
                      f"  | days to 1st payout {s['first_payout_days']}")
    # rolling 2-year windows: how often does the plan lose money?
    print("\n== every 2-year window starting each month, Nov 2016 .. Oct 2024 (Exness costs) ==")
    starts = pd.date_range("2016-11-01", "2024-10-01", freq="MS")
    for risk in (25, 50, 65, 90):
        nets, breached_first = [], 0
        for st in starts:
            s, log = simulate(paths, risk, st, st + pd.DateOffset(years=2))
            nets.append(s["net"])
            breached_first += bool(log) and any(e[1].startswith("BREACH") for e in log) and \
                next(e for e in log if e[1] != "buy account")[1].startswith("BREACH")
        nets = np.array(nets)
        rows.append(dict(label="rolling 2-year windows", risk=risk, windows=len(nets), median_net=float(np.median(nets)),
                         p_loss=float((nets < 0).mean()), worst=float(nets.min()), best=float(nets.max()),
                         breached_before_first_payout=breached_first))
        print(f"  risk ${risk:3}/trade: median NET ${np.median(nets):>+7,.0f} | lose money in {(nets < 0).mean():4.0%} of "
              f"{len(nets)} windows | worst ${nets.min():>+7,.0f} best ${nets.max():>+7,.0f} | first account breached before "
              f"any payout in {breached_first}/{len(nets)}")
    pd.DataFrame(rows).to_csv(HERE / "prop_results.csv", index=False)


if __name__ == "__main__":
    main()
