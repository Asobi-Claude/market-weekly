import io
import json
import unittest
import urllib.error
from datetime import datetime, timezone

from scripts.prices import PriceError, fetch_series, parse_chart

DAY = 86400
T0 = 1794268800  # some day, 00:00 UTC


def payload(timestamps, closes, gmtoffset=0):
    return {"chart": {"result": [{"meta": {"gmtoffset": gmtoffset}, "timestamp": timestamps,
                                  "indicators": {"quote": [{"close": closes}]}}], "error": None}}


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).date().isoformat()


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener_returning(obj, seen=None):
    def opener(req, timeout=None):
        if seen is not None:
            seen.append(req)
        return FakeResponse(json.dumps(obj).encode("utf-8"))
    return opener


def opener_raising(exc):
    def opener(req, timeout=None):
        raise exc
    return opener


class ParseTest(unittest.TestCase):
    def test_parse_uses_exchange_local_date_and_skips_null(self):
        p = payload([T0, T0 + DAY, T0 + 2 * DAY], [100.0, None, 103.5], gmtoffset=32400)
        rows = parse_chart(p)
        self.assertEqual([c for _, c in rows], [100.0, 103.5])
        self.assertEqual(rows[0][0], iso(T0 + 32400))

    def test_local_date_shifts_across_midnight(self):
        # 23:00 UTC is already the next day in Tokyo (+9h)
        rows = parse_chart(payload([T0 + 23 * 3600], [1.0], gmtoffset=32400))
        self.assertEqual(rows[0][0], iso(T0 + DAY))

    def test_midnight_bar_stamped_before_dst_change_keeps_its_date(self):
        # Futures bars are stamped at local midnight. Yahoo reports only today's UTC offset
        # (-5h in winter), so a summer bar (midnight EDT = 04:00 UTC) lands at 23:00 the day before.
        rows = parse_chart(payload([T0 + 4 * 3600], [1.0], gmtoffset=-18000))
        self.assertEqual(rows[0][0], iso(T0))

    def test_midnight_bar_stamped_after_dst_start_keeps_its_date(self):
        # London FX: winter bar at 00:00 UTC read with the summer offset (+1h) stays the same day.
        rows = parse_chart(payload([T0], [1.0], gmtoffset=3600))
        self.assertEqual(rows[0][0], iso(T0))

    def test_parse_dedupes_same_date_keeping_last(self):
        rows = parse_chart(payload([T0, T0 + 3600, T0 + DAY], [1.0, 2.0, 3.0]))
        self.assertEqual(rows, [(iso(T0), 2.0), (iso(T0 + DAY), 3.0)])

    def test_parse_sorts_by_date(self):
        rows = parse_chart(payload([T0 + DAY, T0], [2.0, 1.0]))
        self.assertEqual([c for _, c in rows], [1.0, 2.0])

    def test_parse_raises_on_missing_result(self):
        with self.assertRaises(PriceError):
            parse_chart({"chart": {"result": None, "error": {"code": "Not Found"}}})

    def test_parse_raises_on_unexpected_shape(self):
        for bad in ({}, {"chart": {"result": [{}]}}, [], None,
                    {"chart": {"result": [{"meta": {}, "timestamp": None, "indicators": {}}]}}):
            with self.assertRaises(PriceError):
                parse_chart(bad)


class FetchTest(unittest.TestCase):
    def test_fetch_returns_parsed_rows(self):
        rows = fetch_series("GC=F", opener=opener_returning(payload([T0], [4000.5])))
        self.assertEqual(rows, [(iso(T0), 4000.5)])

    def test_fetch_raises_price_error_on_http_error(self):
        err = urllib.error.HTTPError("u", 404, "Not Found", {}, io.BytesIO(b""))
        with self.assertRaises(PriceError):
            fetch_series("X", opener=opener_raising(err))

    def test_fetch_raises_price_error_on_timeout(self):
        with self.assertRaises(PriceError):
            fetch_series("X", opener=opener_raising(TimeoutError("timed out")))

    def test_fetch_raises_price_error_on_unreachable(self):
        with self.assertRaises(PriceError):
            fetch_series("X", opener=opener_raising(urllib.error.URLError("dns")))

    def test_fetch_raises_on_bad_json(self):
        def opener(req, timeout=None):
            return FakeResponse(b"<html>blocked</html>")
        with self.assertRaises(PriceError):
            fetch_series("X", opener=opener)

    def test_fetch_raises_on_empty_series(self):
        with self.assertRaises(PriceError):
            fetch_series("X", opener=opener_returning(payload([T0, T0 + DAY], [None, None])))

    def test_fetch_quotes_symbol_in_url(self):
        seen = []
        fetch_series("^GSPC", opener=opener_returning(payload([T0], [1.0]), seen))
        self.assertIn("/chart/%5EGSPC?range=1y&interval=1d", seen[0].full_url)
        self.assertEqual(seen[0].get_header("User-agent"), "Mozilla/5.0")


if __name__ == "__main__":
    unittest.main()
