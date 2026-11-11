"""Weekly moves for the watchlist, ranked by how unusual each move is.

Usage: python scripts/weekly.py snapshot [--week-end YYYY-MM-DD] [--out work/snapshot.json]
"""
import argparse
import json
import os
import statistics
import sys
from datetime import date, timedelta

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import prices, state  # noqa: E402

MIN_VALID = 10
LOOKBACK_WEEKS = 26
MIN_HISTORY_WEEKS = 8
WEEK = timedelta(days=7)


def last_close_in(series, after, upto):
    """Last (date, close) with after < date <= upto, or None."""
    lo, hi = after.isoformat(), upto.isoformat()
    hit = None
    for day, close in series:
        if lo < day <= hi:
            hit = (day, close)
    return hit


def weekly_change(series, week_end, kind):
    end = last_close_in(series, week_end - WEEK, week_end)
    start = last_close_in(series, week_end - 2 * WEEK, week_end - WEEK)
    if end is None or start is None:
        return None
    if kind == "yield":
        change, unit = end[1] - start[1], "pt"
    else:
        if not start[1]:
            return None
        change, unit = (end[1] / start[1] - 1) * 100, "%"
    return {"start_date": start[0], "start": start[1], "end_date": end[0], "end": end[1],
            "change": change, "unit": unit}


def score(series, week_end, kind):
    """|this week's change| relative to the median |weekly change| of the past 26 weeks."""
    now = weekly_change(series, week_end, kind)
    if now is None:
        return None
    past = [weekly_change(series, week_end - k * WEEK, kind) for k in range(1, LOOKBACK_WEEKS + 1)]
    sizes = [abs(c["change"]) for c in past if c is not None]
    if len(sizes) < MIN_HISTORY_WEEKS:
        return None
    typical = statistics.median(sizes)
    if typical <= 0:
        return None
    return abs(now["change"]) / typical


def build_snapshot(watchlist, fetch, week_end):
    instruments, missing = [], []
    for item in watchlist:
        try:
            series = fetch(item["symbol"])
        except prices.PriceError as e:
            missing.append({"id": item["id"], "reason": f"fetch failed: {e}"})
            continue
        change = weekly_change(series, week_end, item["kind"])
        if change is None:
            missing.append({"id": item["id"], "reason": "no trading day in week"})
            continue
        s = score(series, week_end, item["kind"])
        if s is None:
            missing.append({"id": item["id"], "reason": "not enough history to judge the move"})
            continue
        daily = [[d, c] for d, c in series if change["start_date"] <= d <= change["end_date"]]
        instruments.append({"id": item["id"], "name": item["name"], "group": item["group"],
                            "kind": item["kind"], "score": s, **change, "daily": daily})
    instruments.sort(key=lambda i: i["score"], reverse=True)
    for rank, inst in enumerate(instruments, 1):
        inst["rank"] = rank
    return {"week_end": week_end.isoformat(),
            "week_start": (week_end - timedelta(days=4)).isoformat(),
            "status": "ok" if len(instruments) >= MIN_VALID else "insufficient",
            "instruments": instruments, "missing": missing}


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("--week-end", type=date.fromisoformat)
    s.add_argument("--out", default=os.path.join(state.ROOT, "work", "snapshot.json"))
    a = p.parse_args(argv)

    week_end = a.week_end or state.week_end_for(state.today_jst())
    snap = build_snapshot(prices.load_watchlist(), prices.fetch_series, week_end)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"week_end: {snap['week_end']}  status: {snap['status']}  "
          f"valid: {len(snap['instruments'])}  missing: {len(snap['missing'])}")
    for i in snap["instruments"][:10]:
        sign = "+" if i["change"] >= 0 else ""
        print(f"{i['rank']:2} {i['id']:9} {sign}{i['change']:.2f}{i['unit']:2} score {i['score']:.2f}  "
              f"{i['start_date']} {i['start']:.2f} -> {i['end_date']} {i['end']:.2f}")
    for m in snap["missing"]:
        print(f" - {m['id']}: {m['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
