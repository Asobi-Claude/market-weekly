"""Weekly delivery state: which Friday closes the week, and what was sent for it."""
import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_FILE = os.path.join(ROOT, "issues.json")
DONE = ("sent", "skipped")


def today_jst(now=None):
    now = now or datetime.now(timezone.utc)
    return now.astimezone(JST).date()


def week_end_for(today):
    """The last Friday strictly before `today`."""
    back = (today.weekday() - 4) % 7 or 7
    return today - timedelta(days=back)


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return []
    return json.loads(text) if text.strip() else []


def save(path, entries):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
        f.write("\n")


def is_done(entries, week_end):
    return any(e.get("week_end") == week_end and e.get("status") in DONE for e in entries)


def record(entries, *, week_end, status, headline=None, url=None, error=None):
    entry = {"week_end": week_end, "status": status}
    for key, value in (("headline", headline), ("url", url), ("error", error)):
        if value is not None:
            entry[key] = value
    return [*(e for e in entries if e.get("week_end") != week_end), entry]


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status")
    s.add_argument("--file", default=DEFAULT_FILE)
    r = sub.add_parser("record")
    r.add_argument("--file", default=DEFAULT_FILE)
    r.add_argument("--week-end", required=True, type=date.fromisoformat)
    r.add_argument("--status", required=True, choices=["sent", "skipped", "failed"])
    r.add_argument("--headline")
    r.add_argument("--url")
    r.add_argument("--error")
    a = p.parse_args(argv)

    entries = load(a.file)
    if a.cmd == "status":
        today = today_jst()
        week_end = week_end_for(today).isoformat()
        print(json.dumps({"today": today.isoformat(), "week_end": week_end,
                          "already_done": is_done(entries, week_end)}, ensure_ascii=False, indent=2))
    else:
        week_end = a.week_end.isoformat()
        save(a.file, record(entries, week_end=week_end, status=a.status,
                            headline=a.headline, url=a.url, error=a.error))
        print(f"recorded {week_end} ({a.status})")


if __name__ == "__main__":
    main()
