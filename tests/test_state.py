import json
import os
import tempfile
import unittest
from datetime import date, datetime, timezone

from scripts.state import is_done, load, record, save, today_jst, week_end_for


class WeekTest(unittest.TestCase):
    def test_week_end_is_last_friday_strictly_before_today(self):
        self.assertEqual(week_end_for(date(2026, 11, 14)), date(2026, 11, 13))  # Sat
        self.assertEqual(week_end_for(date(2026, 11, 13)), date(2026, 11, 6))   # Friday itself -> previous week
        self.assertEqual(week_end_for(date(2026, 11, 16)), date(2026, 11, 13))  # Mon

    def test_today_jst_crosses_midnight(self):
        self.assertEqual(today_jst(datetime(2026, 11, 13, 23, 0, tzinfo=timezone.utc)), date(2026, 11, 14))


class HistoryTest(unittest.TestCase):
    def test_is_done_for_sent_and_skipped_but_not_failed(self):
        e = record([], week_end="2026-11-13", status="failed", error="x")
        self.assertFalse(is_done(e, "2026-11-13"))
        sent = record(e, week_end="2026-11-13", status="sent", headline="h", url="u")
        self.assertTrue(is_done(sent, "2026-11-13"))
        self.assertTrue(is_done(record([], week_end="2026-11-13", status="skipped"), "2026-11-13"))

    def test_is_done_ignores_other_weeks(self):
        e = record([], week_end="2026-11-06", status="sent", headline="h", url="u")
        self.assertFalse(is_done(e, "2026-11-13"))

    def test_record_replaces_same_week(self):
        e = record([], week_end="2026-11-13", status="failed", error="x")
        e = record(e, week_end="2026-11-13", status="sent", headline="h", url="u")
        self.assertEqual(len(e), 1)
        self.assertNotIn("error", e[0])
        self.assertEqual(e[0], {"week_end": "2026-11-13", "status": "sent", "headline": "h", "url": "u"})

    def test_load_missing_or_empty_file_is_empty_list(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(load(os.path.join(d, "none.json")), [])
            p = os.path.join(d, "empty.json")
            open(p, "w").close()
            self.assertEqual(load(p), [])

    def test_save_then_load_round_trips_japanese(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "issues.json")
            entries = record([], week_end="2026-11-13", status="sent", headline="金が上昇", url="u")
            save(p, entries)
            self.assertEqual(load(p), entries)
            with open(p, encoding="utf-8") as f:
                text = f.read()
            self.assertIn("金が上昇", text)
            self.assertTrue(text.endswith("\n"))
            json.loads(text)


if __name__ == "__main__":
    unittest.main()
