import json
import os
import tempfile
import unittest
from datetime import date, datetime, timezone

from scripts.state import (closed_week_end, is_done, is_published, load, record,
                           save, today_jst, week_end_for)


class WeekTest(unittest.TestCase):
    def test_week_end_is_last_friday_strictly_before_today(self):
        self.assertEqual(week_end_for(date(2026, 11, 14)), date(2026, 11, 13))  # Sat
        self.assertEqual(week_end_for(date(2026, 11, 13)), date(2026, 11, 6))   # Friday itself -> previous week
        self.assertEqual(week_end_for(date(2026, 11, 16)), date(2026, 11, 13))  # Mon

    def test_today_jst_crosses_midnight(self):
        self.assertEqual(today_jst(datetime(2026, 11, 13, 23, 0, tzinfo=timezone.utc)), date(2026, 11, 14))


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


class ClosedWeekTest(unittest.TestCase):
    """A week counts only after Friday 22:00 UTC, when futures and FX have closed."""

    def test_scheduled_run_friday_2300_utc_takes_this_week(self):
        self.assertEqual(closed_week_end(utc(2026, 11, 13, 23, 0)), date(2026, 11, 13))

    def test_exactly_at_close_takes_this_week(self):
        self.assertEqual(closed_week_end(utc(2026, 11, 13, 22, 0)), date(2026, 11, 13))

    def test_us_market_still_open_takes_previous_week(self):
        self.assertEqual(closed_week_end(utc(2026, 11, 13, 21, 30)), date(2026, 11, 6))

    def test_saturday_midnight_jst_takes_previous_week(self):
        # 2026-11-14 00:00 JST: Saturday in Japan, but New York is still trading Friday
        self.assertEqual(closed_week_end(utc(2026, 11, 13, 15, 0)), date(2026, 11, 6))

    def test_later_in_the_weekend_and_midweek(self):
        self.assertEqual(closed_week_end(utc(2026, 11, 14, 10, 0)), date(2026, 11, 13))
        self.assertEqual(closed_week_end(utc(2026, 11, 16, 1, 0)), date(2026, 11, 13))
        self.assertEqual(closed_week_end(utc(2026, 11, 12, 23, 0)), date(2026, 11, 6))


class StatusCliTest(unittest.TestCase):
    def run_status(self, entries, now):
        import contextlib
        import io
        from unittest import mock
        from scripts import state
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "issues.json")
            save(path, entries)
            out = io.StringIO()
            with mock.patch.object(state, "now_utc", lambda: now), contextlib.redirect_stdout(out):
                state.main(["status", "--file", path])
        return json.loads(out.getvalue())

    def test_status_reports_closed_week_and_flags(self):
        s = self.run_status([], utc(2026, 11, 13, 23, 0))
        self.assertEqual(s, {"today": "2026-11-14", "week_end": "2026-11-13",
                             "already_done": False, "published": False})

    def test_status_sees_published_but_unsent_week(self):
        e = record([], week_end="2026-11-13", status="published", headline="h", url="u")
        s = self.run_status(e, utc(2026, 11, 14, 1, 0))
        self.assertEqual((s["already_done"], s["published"]), (False, True))

    def test_record_cli_accepts_published(self):
        from scripts import state
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "issues.json")
            import contextlib
            import io
            with contextlib.redirect_stdout(io.StringIO()):
                state.main(["record", "--file", path, "--week-end", "2026-11-13", "--status", "published",
                            "--headline", "h", "--url", "u"])
            self.assertEqual(load(path), [{"week_end": "2026-11-13", "status": "published",
                                           "headline": "h", "url": "u"}])


class HistoryTest(unittest.TestCase):
    def test_published_is_not_done_but_is_published(self):
        e = record([], week_end="2026-11-13", status="published", headline="h", url="u")
        self.assertFalse(is_done(e, "2026-11-13"))
        self.assertTrue(is_published(e, "2026-11-13"))
        self.assertFalse(is_published(e, "2026-11-06"))
        sent = record(e, week_end="2026-11-13", status="sent", headline="h", url="u")
        self.assertTrue(is_done(sent, "2026-11-13"))
        self.assertTrue(is_published(sent, "2026-11-13"))

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
