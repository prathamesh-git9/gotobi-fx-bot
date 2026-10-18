"""Scheduled central-bank events 2016-2027 from the official calendars, for the 'news day' tests.

  FOMC statements: federalreserve.gov meeting calendars (scheduled meetings at 14:00 New York; the two
                   unscheduled 2020 cuts at their real times). Minutes: release date printed on the calendar,
                   otherwise three weeks after the statement (the Fed's fixed rule), 14:00 New York.
  BOJ decisions:   boj.or.jp meeting tables; the decision day is the last day of each meeting. The release has no
                   fixed time (usually 11:30-13:00 JST), so only the date is used.

Pages are cached in data/calendars/; output: data/events_calendar.csv (event, date, time_utc).
"""
import html
import re
from pathlib import Path

import pandas as pd
import requests

DATA = Path(__file__).resolve().parent.parent / "data"
CACHE = DATA / "calendars"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140 Safari/537.36"}
PAGES = {"fed_cur": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
         "boj_cur": "https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm",
         "boj_past": "https://www.boj.or.jp/en/mopo/mpmsche_minu/past.htm",
         **{f"fed_{y}": f"https://www.federalreserve.gov/monetarypolicy/fomchistorical{y}.htm" for y in range(2016, 2021)}}
UNSCHEDULED_NY = {"2020-03-03": "10:00", "2020-03-15": "17:00"}   # emergency cuts: real release times
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def page(name: str) -> str:
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{name}.html"
    if not f.exists():
        r = requests.get(PAGES[name], headers=UA, timeout=30)
        r.raise_for_status()
        f.write_text(r.text, encoding="utf-8")
    return f.read_text(encoding="utf-8")


def text(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def ny(date: str, hhmm: str) -> pd.Timestamp:
    return (pd.Timestamp(f"{date} {hhmm}").tz_localize("America/New_York").tz_convert("UTC").tz_localize(None))


def released(block: str) -> str | None:
    rel = re.search(r"Released (\w+ \d{1,2}, \d{4})", text(block))
    return str(pd.Timestamp(rel.group(1)).date()) if rel else None


def fomc() -> list[dict]:
    rows, seen = [], set()

    def add(stmt: str, minutes: str | None):
        if stmt in seen:
            return
        seen.add(stmt)
        rows.append(dict(event="fomc", date=stmt, time_utc=ny(stmt, UNSCHEDULED_NY.get(stmt, "14:00"))))
        if stmt in UNSCHEDULED_NY:
            return      # emergency meetings are covered by the next regular minutes
        m = minutes or str((pd.Timestamp(stmt) + pd.Timedelta(days=21)).date())
        rows.append(dict(event="fomc_minutes", date=m, time_utc=ny(m, "14:00")))

    cur = page("fed_cur")
    for block in re.split(r'class="[^"]*row fomc-meeting"', cur)[1:]:
        link = re.search(r"monetary(\d{8})a\.htm", block)
        date_div = re.search(r'fomc-meeting__date[^>]*>(.*?)</div>', block, re.S)
        if not link or (date_div and "notation" in date_div.group(1)):
            continue    # cancelled meeting, or a notation vote (e.g. the Aug 2025 strategy statement): no decision
        add(str(pd.Timestamp(link.group(1)).date()), released(block))
    for y in range(2016, 2021):
        h = page(f"fed_{y}")
        parts = re.split(r"<h5[^>]*>", h)[1:]
        for part in parts:
            head = text(part.split("</h5>")[0])
            if "Meeting" not in head or "cancelled" in head:
                continue
            link = re.search(r"monetary(\d{8})a\.htm", part)
            if link:
                add(str(pd.Timestamp(link.group(1)).date()), released(part))
    return rows


def boj() -> list[dict]:
    rows = []
    for name in ("boj_past", "boj_cur"):
        h = page(name)
        for tab in re.split(r"<table", h)[1:]:
            cap = re.search(r"Table\s*:\s*(\d{4})", text(tab[:400]))
            if not cap:
                continue
            year = int(cap.group(1))
            for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", tab, re.S):
                cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
                if not cells:
                    continue
                first = text(cells[0])
                dates = re.findall(r"(?:([A-Z][a-z]{2,4})\.?\s+)?(\d{1,2})\s*\(", first)
                if not dates:
                    continue
                month = None
                last = None
                for mon, day in dates:
                    if mon:
                        month = MONTHS[mon[:3].lower()]
                    last = (month, int(day))
                rows.append(dict(event="boj", date=f"{year}-{last[0]:02d}-{last[1]:02d}", time_utc=pd.NaT))
    return rows


if __name__ == "__main__":
    ev = pd.DataFrame(fomc() + boj())
    ev["date"] = pd.to_datetime(ev.date)
    ev = ev.drop_duplicates(["event", "date"]).sort_values(["date", "event"]).reset_index(drop=True)
    ev = ev[(ev.date >= "2015-06-01") & (ev.date <= "2027-12-31")]
    ev.to_csv(DATA / "events_calendar.csv", index=False)
    for e, g in ev.groupby("event"):
        per = g.groupby(g.date.dt.year).size()
        print(f"{e:13s} {len(g):3d}  per year: " + " ".join(f"{y % 100:02d}:{n}" for y, n in per.items()))
    print(ev[ev.date.dt.year == 2020].to_string())
