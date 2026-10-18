"""Does a '200 EMA' trend filter improve the Gotobi bot? (Checking a claim made by another AI assistant.)

The claim: with 'enhanced rules' (something like price above the 200 EMA) the strategy made +23% from
January 2026 and is safer. The exact rule is unknown, so the common versions are all tested:
  long only when the last COMPLETED candle closed above its 200-period EMA, on D1 / H4 / H1 / M15 / M5
  (USD/JPY mid prices; D1 candles are UTC days, as on an Exness MT5 chart). No look-ahead.
Trades: the bot's own 2016-2026 replay (results/bot_trades_2016_2026.csv: real fills, 55-pip stop).
Money: $1,000 account, the bot's exact sizing (risk % of equity / loss per lot at the stop, lots rounded down
to 0.01, 1:500 leverage) and P&L formula, so the unfiltered 2026 run must reproduce the replay's $1,035.48.
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA, RES = ROOT / "data", ROOT / "results"
SLIP = 0.2e-4
TFS = {"D1": "1D", "H4": "4h", "H1": "1h", "M15": "15min", "M5": "5min"}
RNG = np.random.default_rng(5)


def mid_closes() -> pd.Series:
    files = ["USDJPYm_2016_m1.parquet", "USDJPYm_m1.parquet", "USDJPYm_2026_10_m1.parquet"]
    df = pd.concat([pd.read_parquet(DATA / f, columns=["bclose", "aclose"]) for f in files]).sort_index()
    df = df[~df.index.duplicated()]
    return (df.bclose + df.aclose) / 2


def above_ema(mid: pd.Series, freq: str, entries: pd.Series) -> np.ndarray:
    closes = mid.resample(freq).last().dropna()
    ema = closes.ewm(span=200, adjust=False).mean()
    end = (closes.index + pd.Timedelta(freq)).values            # a candle is complete at its end time
    i = np.searchsorted(end, entries.values, side="right") - 1   # last candle completed at entry time
    return (closes.to_numpy()[i] > ema.to_numpy()[i])


def account(t: pd.DataFrame, risk: float, start: float = 1000.0, leverage: int = 500):
    bal, peak, dd, n, path = start, start, 0.0, 0, []
    for r in t.itertuples():
        ask = r.entry_price / (1 + SLIP)
        loss_per_lot = round(100_000 * (ask - r.sl) / r.sl, 2)
        equity = round(bal, 2)
        lots = np.floor(equity * risk / loss_per_lot / 0.01 + 1e-9) * 0.01
        lots = min(lots, np.floor(equity * 0.9 / (100_000 / leverage) / 0.01 + 1e-9) * 0.01)
        if lots < 0.01:
            continue
        bal += lots * 100_000 * (r.close_price - r.entry_price) / r.close_price
        n += 1
        peak = max(peak, bal)
        dd = max(dd, 1 - bal / peak)
        path.append(bal)
    return bal, dd, n


if __name__ == "__main__":
    t = pd.read_csv(RES / "bot_trades_2016_2026.csv", parse_dates=["opened", "closed"])
    t["opened"] = t.opened.dt.tz_localize(None)
    t["pips"] = (t.close_price - t.entry_price) * 100
    t["year"] = pd.to_datetime(t.gotobi).dt.year
    mid = mid_closes()
    for name, f in TFS.items():
        t[name] = above_ema(mid, f, t.opened)
    rules = ["none"] + list(TFS)
    lines = []

    def p(s=""):
        print(s)
        lines.append(s)

    y26 = t[t.gotobi >= "2026-01-01"]
    p("=== 1 Jan - 16 Oct 2026, $1,000 start ===")
    p(f"{'rule (long only if above 200 EMA)':34s} {'trades':>6} | {'1% risk':>18} | {'5% risk':>18} | {'10% risk':>18}")
    for rule in rules:
        x = y26 if rule == "none" else y26[y26[rule]]
        cells = []
        for risk in (0.01, 0.05, 0.10):
            b, dd, n = account(x, risk)
            cells.append(f"${b:8,.2f} DD{dd:4.0%}")
        p(f"{('no filter (our bot)' if rule == 'none' else rule + ' 200 EMA'):34s} {len(x):6d} | " + " | ".join(f"{c:>18}" for c in cells))

    p("\n=== 2016 - 2026 (752 trades), is the filter better over 10 years? ===")
    p(f"{'rule':20s} {'trades':>6} {'win':>5} {'avg pips':>9} {'skipped trades avg':>19} | {'$1,000 at 10% risk':>20} {'max DD':>7} | years better than no filter")
    base_year = t.groupby("year").pips.sum()
    for rule in rules:
        x = t if rule == "none" else t[t[rule]]
        skipped = t if rule == "none" else t[~t[rule]]
        b, dd, n = account(x, 0.10)
        yr = x.groupby("year").pips.sum().reindex(base_year.index, fill_value=0)
        better = "-" if rule == "none" else f"{int((yr > base_year).sum())}/{len(base_year)}"
        sk = f"{skipped.pips.mean():+.2f} ({len(skipped)})" if rule != "none" else ""
        p(f"{('no filter (our bot)' if rule == 'none' else rule + ' 200 EMA'):20s} {len(x):6d} {np.mean(x.pips > 0):5.0%} {x.pips.mean():+9.2f} {sk:>19} | "
          f"${b:>18,.0f} {dd:7.0%} | {better}")

    p("\n=== Blow-up risk: 10,000 simulated 3-year runs from the real 2016-2026 trades (no filter) ===")
    r = (t.pips / 55.6).to_numpy()            # result in R (1R = the stop)
    for risk in (0.01, 0.02, 0.05, 0.10, 0.20):
        paths = 1000 * np.cumprod(1 + risk * RNG.choice(r, (10000, 210)), axis=1)
        dd = (1 - paths / np.maximum.accumulate(paths, axis=1)).max(1)
        p(f"  {risk:4.0%} risk: median end ${np.median(paths[:, -1]):>9,.0f} | P(drop > 50%) {np.mean(dd > .5):5.1%} | "
          f"P(lose 80% at some point) {np.mean(dd > .8):5.1%} | P(account below $100) {np.mean(paths.min(1) < 100):5.1%}")
    (RES / "ema_filter_report.txt").write_text("\n".join(lines), encoding="utf-8")
