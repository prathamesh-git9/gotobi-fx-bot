"""20 years of the production bot: Exness bid/ask 2016-2026, and HistData bid + a spread model for 2006-2015.

HistData (src/fetch_histdata.py) has bid prices only. The ask is rebuilt as bid + the median Exness spread of
that minute of the day (2016-2018), optionally plus a stress add-on. The approach is checked on 2016-2018, where
both sources exist: the same bot on HistData+model vs on real Exness bid/ask.

  python src/gotobi_20y.py check     time alignment, price agreement and the spread profile
  python src/gotobi_20y.py run       per-year returns (fresh account each 1 Jan, 6% risk), all variants
"""
import logging
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from bot.config import Config  # noqa: E402
from bot.fake_mt5 import FakeMT5  # noqa: E402
from bot.replay import load_bars, replay, trades_frame  # noqa: E402

UTC = timezone.utc
HD = ROOT / "data" / "histdata" / "USDJPY_hd_bid_m1.parquet"
RES = ROOT / "results"
END_2026 = datetime(2026, 10, 16, 23, 59, tzinfo=UTC)
OLD = {"take_profit_pips": 0.0, "post_fix_short": False}
BID = ["bopen", "bhigh", "blow", "bclose"]
ASK = ["aopen", "ahigh", "alow", "aclose"]


def exness() -> pd.DataFrame:
    return load_bars()


def spread_profile(ex: pd.DataFrame) -> pd.Series:
    """Median Exness spread (pips) for each UTC minute of the day, 2016-2018."""
    e = ex.loc["2016":"2018"]
    sp = (e.aopen - e.bopen) * 100
    return sp.groupby(e.index.hour * 60 + e.index.minute).median()


def synth(bid: pd.DataFrame, prof: pd.Series, extra_pips: float = 0.0) -> pd.DataFrame:
    mod = bid.index.hour * 60 + bid.index.minute
    spread = (prof.reindex(np.arange(1440)).ffill().bfill().to_numpy()[mod] + extra_pips) / 100
    out = bid[BID].copy()
    for b, a in zip(BID, ASK):
        out[a] = out[b] + spread
    return out


def check() -> None:
    ex, hd = exness(), pd.read_parquet(HD)
    a = ex.loc["2016":"2018", "bclose"]
    b = hd.loc["2016":"2018", "bclose"]
    ra, rb = a.diff(), b.diff()
    best = []
    for lag in range(-120, 121, 1):
        j = pd.concat([ra, rb.shift(lag, freq="min")], axis=1, join="inner").dropna()
        best.append((j.corr().iloc[0, 1], lag))
    best.sort(reverse=True)
    print("lag (min) with the highest return correlation, HistData shifted:", best[:3])
    for season, months in (("winter", [1, 2, 12]), ("summer", [6, 7, 8])):
        sa, sb = ra[ra.index.month.isin(months)], rb[rb.index.month.isin(months)]
        cs = {lag: pd.concat([sa, sb.shift(lag, freq="min")], axis=1, join="inner").dropna().corr().iloc[0, 1]
              for lag in (-60, 0, 60)}
        print(f"  {season}: corr at lag -60/0/+60 = {cs[-60]:.3f} / {cs[0]:.3f} / {cs[60]:.3f}")
    j = pd.concat([a, b], axis=1, join="inner").dropna()
    d = (j.iloc[:, 1] - j.iloc[:, 0]) * 100
    print(f"bid close, HistData minus Exness: median {d.median():+.2f} pips, median |diff| {d.abs().median():.2f}, "
          f"95th pct |diff| {d.abs().quantile(.95):.2f}; {len(j):,} common minutes")
    prof = spread_profile(ex)
    for hm in ("15:55", "00:54", "00:55", "01:25", "21:15", "12:00"):
        h, m = map(int, hm.split(":"))
        print(f"Exness median spread {hm} UTC (2016-18): {prof.loc[h * 60 + m]:.2f} pips")
    for y in (2016, 2019, 2022, 2025):
        e = ex.loc[str(y)]
        sp = (e.aopen - e.bopen) * 100
        at = lambda h, m: sp[(e.index.hour == h) & (e.index.minute == m)].median()  # noqa: E731
        print(f"  {y}: 15:55 {at(15, 55):.2f}, 00:54 {at(0, 54):.2f}, 00:55 {at(0, 55):.2f}, 01:25 {at(1, 25):.2f}")
    # every year, not just the overlap: the weekly reopen should sit at the same New York clock time in summer
    # and winter (about 17:00) if the UTC conversion is right
    ny = hd.index.tz_localize("UTC").tz_convert("America/New_York")
    reopen = (hd.index.to_series().diff() > pd.Timedelta(hours=24)).to_numpy()
    first = pd.Series(ny[reopen])
    first = first[first.dt.weekday == 6]                  # Sunday-evening reopens only
    dst = first.map(lambda x: bool(x.dst()))
    clock = first.dt.hour + first.dt.minute / 60
    for y in range(2006, 2019):
        sel = first.dt.year == y
        print(f"HistData {y}: {len(hd.loc[str(y)]):,} bars; first bar of the week, New York clock: "
              f"summer median {clock[sel & dst].median():.2f} h, winter median {clock[sel & ~dst].median():.2f} h")
    # the gotobi windows themselves: bars present at the bot's decision minutes
    from bot.gotobi_calendar import GotobiCalendar
    cal = GotobiCalendar()
    days = cal.trade_days(datetime(2006, 1, 1).date(), datetime(2015, 12, 31).date())
    idx = hd.index
    def has(ts):  # noqa: E301
        return ts in idx
    miss = {k: 0 for k in ("15:55", "00:54", "00:55", "01:25")}
    for d in days:
        s = cal.slot(d)
        for k, ts in (("15:55", s.entry), ("00:54", s.exit), ("00:55", s.fix), ("01:25", s.short_close)):
            miss[k] += not has(pd.Timestamp(ts).tz_localize(None))
    print(f"2006-2015 gotobi days: {len(days)}; minutes with no HistData bar: {miss} "
          f"(15:55 on Sundays is expected: the market is shut)")


def one_year(job: tuple) -> dict:
    """Replay one calendar year on a fresh account. job = (label, source, year, bars, overrides, risk)."""
    label, source, year, bars, overrides, risk = job
    logging.disable(logging.CRITICAL)
    t0 = datetime(year, 1, 1, tzinfo=UTC)
    t1 = END_2026 if year == 2026 else datetime(year, 12, 31, 23, 59, tzinfo=UTC)
    fake = FakeMT5(bars, 1.0, balance=10_000.0, currency="USD", leverage=500)
    cfg = replace(Config(), symbols=("USDJPYm",), risk_pct=risk, **overrides)
    with tempfile.TemporaryDirectory() as tmp:
        journal, _ = replay(cfg, fake, t0, t1, tmp)
        t = trades_frame(journal)
        notes = [v.get("note", v.get("status")) for v in journal.slots.values() if v.get("status") != "closed"]
        halted = journal.halted
    bal = 10_000.0 + (t.pnl.cumsum() if len(t) else pd.Series([0.0]))
    peak = bal.cummax().clip(lower=10_000.0)
    lng, sh = (t[t.trade == "long"], t[t.trade == "short"]) if len(t) else (t, t)
    t = t.assign(label=label, source=source, year=year)
    return {"label": label, "source": source, "year": year, "ret": fake.balance / 10_000.0 - 1,
            "dd": float((1 - bal / peak).max()), "trades": len(t), "long_n": len(lng), "short_n": len(sh),
            "long_pips": float(lng.pips.sum()) if len(lng) else 0.0,
            "short_pips": float(sh.pips.sum()) if len(sh) else 0.0,
            "win": float((t.pnl > 0).mean()) if len(t) else float("nan"),
            "not_traded": len(notes), "halted": bool(halted), "trades_df": t}


def jobs_for(label, source, bars, years, overrides, risk=6.0):
    for y in years:
        lo = pd.Timestamp(y, 1, 1) - pd.Timedelta(days=4)
        hi = pd.Timestamp(y + 1, 1, 2)
        yield (label, source, y, bars[(bars.index >= lo) & (bars.index < hi)], overrides, risk)


def run() -> None:
    ex, hd_bid = exness(), pd.read_parquet(HD)
    prof = spread_profile(ex)
    hd = synth(hd_bid, prof)
    hd_stress = synth(hd_bid, prof, extra_pips=1.0)
    ex = ex[BID + ASK]
    jobs = []
    for name, ov in (("new", {}), ("old", OLD)):
        jobs += jobs_for(name, "exness", ex, range(2016, 2027), ov)
        jobs += jobs_for(name, "histdata", hd, range(2006, 2019), ov)
        jobs += jobs_for(name, "histdata+1pip", hd_stress, range(2006, 2019), ov)
    with ProcessPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(one_year, jobs))
    trades = pd.concat([r.pop("trades_df") for r in rows if len(r["trades_df"])], ignore_index=True)
    trades.to_csv(RES / "gotobi_20y_trades.csv", index=False)
    df = pd.DataFrame(rows).sort_values(["label", "source", "year"])
    df.to_csv(RES / "gotobi_20y_years.csv", index=False)
    pd.set_option("display.width", 200)
    for name in ("new", "old"):
        piv = df[df.label == name].pivot(index="year", columns="source", values="ret").mul(100).round(1)
        print(f"\n{name} strategy, % return per calendar year (fresh account each 1 Jan, 6% risk):")
        print(piv.to_string())
    print("\nfull rows:")
    print(df.drop(columns=[]).round(3).to_string(index=False))


if __name__ == "__main__":
    {"check": check, "run": run}[sys.argv[1]]()
