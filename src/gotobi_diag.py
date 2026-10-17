"""Where does the Gotobi edge come from, and is it an artefact?

  1. Split window A (15:55 -> 00:55 UTC) into three parts: NY afternoon / rollover hours / Tokyo pre-fix.
  2. Weekday mix: weekend gotobis move to Friday, so compare gotobi vs control within the same weekday.
  3. Monday gotobis (entry 15 min after the Sunday reopen, when spreads are wide) in or out.
  4. Each gotobi date (5, 10, 15, 20, 25, 30) separately: a real settlement flow should show on most of them.
"""
import numpy as np
import pandas as pd

import gotobi as G

G.WINDOWS.update({
    "A1 NY afternoon 15:55-20:55 UTC": (-pd.Timedelta(hours=9), -pd.Timedelta(hours=4), 1),
    "A2 rollover/early Asia 20:55-22:55": (-pd.Timedelta(hours=4), -pd.Timedelta(hours=2), 1),
    "A3 Tokyo pre-fix 22:55-00:55": (-pd.Timedelta(hours=2), pd.Timedelta(0), 1),
})

if __name__ == "__main__":
    df = G.load()
    start, end = df.index[0].normalize() + pd.Timedelta(days=2), df.index[-1].normalize() - pd.Timedelta(days=1)
    diff = G.rate_series(start - pd.Timedelta(days=5), end + pd.Timedelta(days=5)).to_dict()
    bdays = pd.bdate_range(start, end)
    for jp in (False, True):
        g_days = G.gotobi_dates(start, end, jp)
        c_days = bdays[~bdays.isin(g_days)]
        print(f"\n######## {'with Japanese holidays moved' if jp else 'pasted rule'}  ({df.index[0].date()} -> {df.index[-1].date()})")
        print("1) Window A split (gross pips, mid to mid):")
        for w in [k for k in G.WINDOWS if k.startswith("A")]:
            g, c = G.trades(df, g_days, w, diff), G.trades(df, c_days, w, diff)
            print(f"   {w:40s} gotobi {g.gross.mean():+.2f} (t {g.gross.mean() / g.gross.std() * np.sqrt(len(g)):+.2f}) | "
                  f"control {c.gross.mean():+.2f} | diff {g.gross.mean() - c.gross.mean():+.2f} (t {G.welch(g.gross, c.gross):+.2f})")
        g, c = G.trades(df, g_days, "A", diff), G.trades(df, c_days, "A", diff)
        print("2) Same weekday comparison, window A (gross pips): gotobi vs control, n")
        for wd, name in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri"]):
            gg, cc = g[g.wd == wd], c[c.wd == wd]
            print(f"   {name}: gotobi {gg.gross.mean():+6.2f} (n {len(gg):3d}) | control {cc.gross.mean():+6.2f} (n {len(cc):3d}) | "
                  f"diff {gg.gross.mean() - cc.gross.mean():+.2f} (t {G.welch(gg.gross, cc.gross):+.2f})")
        # weekday-matched control: reweight control to the gotobi weekday mix
        w = g.wd.value_counts(normalize=True)
        matched = sum(w.get(d, 0) * c[c.wd == d].gross.mean() for d in range(5))
        print(f"   weekday-matched control {matched:+.2f} vs gotobi {g.gross.mean():+.2f} -> excess {g.gross.mean() - matched:+.2f} pips")
        nm = g[g.wd != 0]
        print(f"3) Without Monday gotobis: n {len(nm)} gross {nm.gross.mean():+.2f}, net {nm.net.mean():+.2f} pips "
              f"(t {nm.net.mean() / nm.net.std() * np.sqrt(len(nm)):+.2f}, PF {nm.net[nm.net > 0].sum() / -nm.net[nm.net < 0].sum():.2f}); "
              f"Mondays alone n {len(g) - len(nm)} net {g[g.wd == 0].net.mean():+.2f}")
        print("4) By gotobi date (nominal day before the weekend/holiday move), window A net pips:")
        nominal = []
        for d in g.day:
            k = d
            while k.day % 5 != 0:
                k += pd.Timedelta(days=1)
            nominal.append(min(k.day, 30))
        g = g.assign(nom=nominal)
        print("   " + "  ".join(f"{n:2d}th: {x.net.mean():+.2f} (n {len(x)}, t {x.net.mean() / x.net.std() * np.sqrt(len(x)):+.2f})"
                             for n, x in g.groupby("nom")))
