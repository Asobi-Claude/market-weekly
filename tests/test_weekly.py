import unittest
from datetime import date, timedelta

from scripts.prices import PriceError
from scripts.weekly import (MIN_VALID, build_snapshot, last_close_in,
                            partial_ids, score, snapshot_with_retry,
                            weekly_change)

WEEK_END = date(2026, 11, 13)  # a Friday


def fridays(closes, last=WEEK_END):
    """One close per Friday, ending at `last`."""
    n = len(closes)
    return [((last - timedelta(days=7 * (n - 1 - i))).isoformat(), c) for i, c in enumerate(closes)]


def alternating(weeks, pct=1.0, final_pct=3.0):
    """Past weeks move +/-pct, the final week moves +final_pct."""
    closes = [100.0]
    for i in range(weeks):
        closes.append(closes[-1] * (1 + (pct if i % 2 == 0 else -pct) / 100))
    closes.append(closes[-1] * (1 + final_pct / 100))
    return fridays(closes)


class ChangeTest(unittest.TestCase):
    def test_last_close_in_is_exclusive_after_inclusive_upto(self):
        s = [("2026-11-06", 1.0), ("2026-11-09", 2.0), ("2026-11-13", 3.0)]
        self.assertEqual(last_close_in(s, date(2026, 11, 6), date(2026, 11, 13)), ("2026-11-13", 3.0))
        self.assertEqual(last_close_in(s, date(2026, 10, 30), date(2026, 11, 6)), ("2026-11-06", 1.0))
        self.assertIsNone(last_close_in(s, date(2026, 11, 13), date(2026, 11, 20)))

    def test_price_change_friday_to_friday(self):
        s = [("2026-11-06", 100.0), ("2026-11-09", 101.0), ("2026-11-13", 103.2)]
        c = weekly_change(s, WEEK_END, "price")
        self.assertAlmostEqual(c["change"], 3.2)
        self.assertEqual(c["unit"], "%")
        self.assertEqual((c["start_date"], c["end_date"]), ("2026-11-06", "2026-11-13"))
        self.assertEqual((c["start"], c["end"]), (100.0, 103.2))

    def test_yield_change_is_point_difference(self):
        c = weekly_change([("2026-11-06", 4.25), ("2026-11-13", 4.13)], WEEK_END, "yield")
        self.assertAlmostEqual(c["change"], -0.12)
        self.assertEqual(c["unit"], "pt")

    def test_friday_holiday_uses_last_trading_day(self):
        s = [("2026-11-06", 100.0), ("2026-11-12", 102.0)]
        self.assertEqual(weekly_change(s, WEEK_END, "price")["end_date"], "2026-11-12")

    def test_previous_friday_holiday_uses_last_trading_day_before(self):
        s = [("2026-11-05", 100.0), ("2026-11-13", 102.0)]
        self.assertEqual(weekly_change(s, WEEK_END, "price")["start_date"], "2026-11-05")

    def test_whole_week_closed_returns_none(self):
        self.assertIsNone(weekly_change([("2026-11-06", 100.0)], WEEK_END, "price"))

    def test_previous_week_closed_returns_none(self):
        self.assertIsNone(weekly_change([("2026-10-30", 99.0), ("2026-11-13", 100.0)], WEEK_END, "price"))

    def test_empty_series_returns_none(self):
        self.assertIsNone(weekly_change([], WEEK_END, "price"))

    def test_saturday_bar_is_not_used(self):
        s = [("2026-11-06", 100.0), ("2026-11-07", 150.0), ("2026-11-13", 110.0), ("2026-11-14", 200.0)]
        c = weekly_change(s, WEEK_END, "price")
        self.assertEqual((c["start_date"], c["end_date"]), ("2026-11-06", "2026-11-13"))
        self.assertAlmostEqual(c["change"], 10.0)


class ScoreTest(unittest.TestCase):
    def test_score_is_ratio_to_median_of_past_weeks(self):
        self.assertAlmostEqual(score(alternating(26), WEEK_END, "price"), 3.0, places=6)

    def test_score_uses_absolute_change(self):
        self.assertAlmostEqual(score(alternating(26, final_pct=-3.0), WEEK_END, "price"), 3.0, places=6)

    def test_score_none_when_history_short(self):
        self.assertIsNone(score(alternating(7), WEEK_END, "price"))
        self.assertIsNotNone(score(alternating(8), WEEK_END, "price"))

    def test_score_none_when_median_zero(self):
        self.assertIsNone(score(fridays([100.0] * 20 + [105.0]), WEEK_END, "price"))

    def test_score_none_when_this_week_missing(self):
        self.assertIsNone(score(alternating(26)[:-1], WEEK_END, "price"))


def watch(n):
    return [{"id": f"i{k}", "name": f"商品{k}", "symbol": f"S{k}", "kind": "price", "group": "株"} for k in range(n)]


class SnapshotTest(unittest.TestCase):
    def test_snapshot_ranks_by_score_and_collects_missing(self):
        wl = watch(12)
        def fetch(symbol):
            k = int(symbol[1:])
            if k == 0:
                raise PriceError("HTTP 404")
            if k == 1:
                return [("2026-11-06", 100.0)]          # closed all week
            return alternating(26, final_pct=float(k))  # bigger k, bigger score
        snap = build_snapshot(wl, fetch, WEEK_END)
        self.assertEqual(snap["status"], "ok")
        self.assertEqual(snap["week_end"], "2026-11-13")
        self.assertEqual(snap["week_start"], "2026-11-09")
        ids = [i["id"] for i in snap["instruments"]]
        self.assertEqual(ids, [f"i{k}" for k in range(11, 1, -1)])
        self.assertEqual([i["rank"] for i in snap["instruments"]], list(range(1, 11)))
        self.assertEqual({m["id"] for m in snap["missing"]}, {"i0", "i1"})
        self.assertIn("404", next(m["reason"] for m in snap["missing"] if m["id"] == "i0"))
        top = snap["instruments"][0]
        self.assertEqual((top["name"], top["group"], top["kind"], top["unit"]), ("商品11", "株", "price", "%"))
        self.assertAlmostEqual(top["change"], 11.0)
        self.assertEqual(top["daily"][0][0], "2026-11-06")
        self.assertEqual(top["daily"][-1][0], "2026-11-13")

    def test_snapshot_daily_covers_start_through_end_only(self):
        def fetch(symbol):
            base = alternating(26)
            extra = [("2026-11-10", 111.0), ("2026-11-14", 999.0)]
            return sorted(base + extra)
        snap = build_snapshot(watch(MIN_VALID), fetch, WEEK_END)
        days = [d for d, _ in snap["instruments"][0]["daily"]]
        self.assertEqual(days, ["2026-11-06", "2026-11-10", "2026-11-13"])

    def test_snapshot_insufficient_when_fewer_than_min_valid(self):
        snap = build_snapshot(watch(MIN_VALID - 1), lambda s: alternating(26), WEEK_END)
        self.assertEqual(snap["status"], "insufficient")
        self.assertEqual(build_snapshot(watch(MIN_VALID), lambda s: alternating(26), WEEK_END)["status"], "ok")

    def test_partial_ids_lists_instruments_ending_before_friday(self):
        def fetch(symbol):
            series = alternating(26)
            return series[:-1] + [("2026-11-12", series[-1][1])] if symbol == "S0" else series
        snap = build_snapshot(watch(MIN_VALID), fetch, WEEK_END)
        self.assertEqual(partial_ids(snap), ["i0"])

    def test_retry_refetches_once_when_friday_is_missing(self):
        calls, sleeps = [], []

        def fetch(symbol):
            calls.append(symbol)
            series = alternating(26)
            late = symbol == "S0" and calls.count("S0") == 1     # Friday bar arrives on the 2nd try
            return series[:-1] + [("2026-11-12", series[-1][1])] if late else series
        snap = snapshot_with_retry(watch(MIN_VALID), fetch, WEEK_END, wait=300, sleep=sleeps.append)
        self.assertEqual(sleeps, [300])
        self.assertEqual(partial_ids(snap), [])
        self.assertEqual(calls.count("S0"), 2)

    def test_no_retry_when_every_friday_is_present(self):
        sleeps = []
        snapshot_with_retry(watch(MIN_VALID), lambda s: alternating(26), WEEK_END, wait=300, sleep=sleeps.append)
        self.assertEqual(sleeps, [])

    def test_retry_keeps_partial_when_friday_never_arrives(self):
        def fetch(symbol):
            series = alternating(26)
            return series[:-1] + [("2026-11-12", series[-1][1])] if symbol == "S0" else series
        snap = snapshot_with_retry(watch(MIN_VALID), fetch, WEEK_END, wait=1, sleep=lambda s: None)
        self.assertEqual(partial_ids(snap), ["i0"])

    def test_snapshot_all_fetches_fail(self):
        def fetch(symbol):
            raise PriceError("unreachable")
        snap = build_snapshot(watch(3), fetch, WEEK_END)
        self.assertEqual((snap["status"], snap["instruments"], len(snap["missing"])), ("insufficient", [], 3))


if __name__ == "__main__":
    unittest.main()
