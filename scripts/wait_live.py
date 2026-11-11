"""Wait until a freshly pushed page is actually being served.

Usage: python scripts/wait_live.py <url>     # prints `live` (exit 0) or `timeout` (exit 1)
"""
import sys
import time
import urllib.error
import urllib.request


def wait_until_live(url, *, opener=urllib.request.urlopen, sleep=time.sleep, attempts=30, interval=20):
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "market-weekly", "Cache-Control": "no-cache"})
            with opener(req, timeout=15) as resp:
                if getattr(resp, "status", 200) == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        if attempt < attempts - 1:
            sleep(interval)
    return False


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    live = wait_until_live(argv[0])
    print("live" if live else "timeout")
    return 0 if live else 1


if __name__ == "__main__":
    sys.exit(main())
