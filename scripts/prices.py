"""Daily closing prices from Yahoo Finance's chart API (free, unofficial).

Usage: python scripts/prices.py check    # fetch every watchlist symbol and print its latest close
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WATCHLIST = os.path.join(ROOT, "config", "watchlist.json")
CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1y&interval=1d"


# Yahoo gives one UTC offset (today's) for the whole year, so bars stamped at local midnight on
# the other side of a daylight-saving change sit at 23:00 the previous day. Bars are stamped at
# the session open (midnight or morning), so nudging by a few hours restores the right date.
DST_SLACK = 3 * 3600


class PriceError(Exception):
    pass


def parse_chart(payload):
    """Return [(exchange-local ISO date, close)] sorted by date; null closes dropped."""
    try:
        result = payload["chart"]["result"][0]
        offset = result["meta"].get("gmtoffset") or 0
        stamps = list(result["timestamp"])
        closes = list(result["indicators"]["quote"][0]["close"])
    except (KeyError, IndexError, TypeError, AttributeError):
        raise PriceError("unexpected chart payload") from None
    by_date = {}
    for ts, close in zip(stamps, closes):
        if close is None or ts is None:
            continue
        day = datetime.fromtimestamp(ts + offset + DST_SLACK, timezone.utc).date().isoformat()
        by_date[day] = float(close)
    return sorted(by_date.items())


def fetch_series(symbol, opener=urllib.request.urlopen):
    url = CHART_URL.format(symbol=urllib.parse.quote(symbol, safe=""))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with opener(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise PriceError(f"HTTP {e.code}") from None
    except urllib.error.URLError as e:
        raise PriceError(f"unreachable: {e.reason}") from None
    except OSError as e:
        raise PriceError(f"connection failed: {e}") from None
    except ValueError:
        raise PriceError("response is not JSON") from None
    rows = parse_chart(payload)
    if not rows:
        raise PriceError("no closing prices")
    return rows


def load_watchlist(path=WATCHLIST):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:] if argv is None else argv
    if argv != ["check"]:
        print(__doc__, file=sys.stderr)
        return 2
    bad = 0
    for item in load_watchlist():
        try:
            day, close = fetch_series(item["symbol"])[-1]
            print(f"{item['id']:10} {item['symbol']:10} {day} {close:.4f}")
        except PriceError as e:
            bad += 1
            print(f"{item['id']:10} NG {e}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
