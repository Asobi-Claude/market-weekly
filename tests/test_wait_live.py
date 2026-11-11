import io
import unittest
import urllib.error

from scripts.wait_live import wait_until_live

URL = "https://example.github.io/market-weekly/issues/2026-11-13.html"


class Opener:
    """Answers each call with the next outcome: an int status or an exception."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, req, timeout=None):
        self.calls += 1
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        if outcome != 200:
            raise urllib.error.HTTPError(URL, outcome, "err", {}, io.BytesIO(b""))
        resp = io.BytesIO(b"<html>")
        resp.status = 200
        return resp


class WaitLiveTest(unittest.TestCase):
    def setUp(self):
        self.sleeps = []

    def wait(self, opener, **kw):
        return wait_until_live(URL, opener=opener, sleep=self.sleeps.append, **kw)

    def test_returns_true_immediately_when_live(self):
        op = Opener(200)
        self.assertTrue(self.wait(op))
        self.assertEqual((op.calls, self.sleeps), (1, []))

    def test_wait_returns_true_after_404_then_200(self):
        op = Opener(404, 200)
        self.assertTrue(self.wait(op, interval=20))
        self.assertEqual((op.calls, self.sleeps), (2, [20]))

    def test_wait_returns_false_when_never_live(self):
        op = Opener(404)
        self.assertFalse(self.wait(op, attempts=3))
        self.assertEqual(op.calls, 3)
        self.assertLessEqual(len(self.sleeps), 3)

    def test_wait_survives_connection_error(self):
        op = Opener(urllib.error.URLError("dns"), TimeoutError("slow"), 200)
        self.assertTrue(self.wait(op))
        self.assertEqual(op.calls, 3)


if __name__ == "__main__":
    unittest.main()
