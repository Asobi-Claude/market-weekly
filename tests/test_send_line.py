import io
import json
import unittest
import urllib.error

from scripts import send_line as s


class FakeOpener:
    def __init__(self, error=None):
        self.error = error
        self.req = None

    def __call__(self, req, timeout=None):
        self.req = req
        if self.error:
            raise self.error
        return io.BytesIO(b"{}")


def http_error(code, body):
    return urllib.error.HTTPError(s.LINE_PUSH_URL, code, "err", {}, io.BytesIO(body.encode()))


class SendLineTest(unittest.TestCase):
    def test_split_short_text(self):
        self.assertEqual(s.split_text("a\n\nb"), ["a\n\nb"])

    def test_split_long_text(self):
        paras = ["x" * 3000, "y" * 3000, "z" * 3000]
        text = "\n\n".join(paras)
        chunks = s.split_text(text)
        self.assertEqual(len(chunks), 3)
        self.assertTrue(all(len(c) <= 5000 for c in chunks))
        self.assertEqual("\n\n".join(chunks), text)

    def test_split_too_long_raises(self):
        with self.assertRaises(ValueError):
            s.split_text("x" * (5000 * 5 + 1))

    def test_split_empty_raises(self):
        with self.assertRaises(ValueError):
            s.split_text("  \n ")

    def test_build_payload(self):
        self.assertEqual(s.build_payload("U1", ["hi"]),
                         {"to": "U1", "messages": [{"type": "text", "text": "hi"}]})

    def test_send_posts_expected_request(self):
        op = FakeOpener()
        s.send("こんにちは", "T", "U1", opener=op)
        self.assertEqual(op.req.full_url, s.LINE_PUSH_URL)
        self.assertEqual(op.req.get_method(), "POST")
        self.assertEqual(op.req.get_header("Authorization"), "Bearer T")
        self.assertEqual(json.loads(op.req.data.decode("utf-8"))["to"], "U1")

    def test_send_raises_on_http_error(self):
        op = FakeOpener(http_error(401, '{"message":"Authentication failed"}'))
        with self.assertRaises(s.SendError) as cm:
            s.send("hi", "T", "U1", opener=op)
        self.assertIn("401", str(cm.exception))
        self.assertIn("Authentication failed", str(cm.exception))

    def test_error_message_hides_token(self):
        op = FakeOpener(http_error(401, '{"message":"bad token SECRET123"}'))
        with self.assertRaises(s.SendError) as cm:
            s.send("hi", "SECRET123", "U1", opener=op)
        self.assertNotIn("SECRET123", str(cm.exception))

    def test_send_sets_retry_key(self):
        op = FakeOpener()
        s.send("hi", "T", "U1", opener=op, retry_key="2026-11-07")
        key = op.req.get_header("X-line-retry-key")
        self.assertEqual(key, s.retry_key_for("2026-11-07"))
        self.assertNotEqual(key, s.retry_key_for("2026-11-08"))
        import uuid
        uuid.UUID(key)  # LINE requires UUID format

    def test_send_treats_409_retry_conflict_as_delivered(self):
        op = FakeOpener(http_error(409, '{"message":"The retry key is already accepted"}'))
        s.send("hi", "T", "U1", opener=op, retry_key="2026-11-07")  # no raise

    def test_send_timeout_raises_send_error(self):
        op = FakeOpener(TimeoutError("timed out"))
        with self.assertRaises(s.SendError) as cm:
            s.send("hi", "T", "U1", opener=op)
        self.assertIn("unknown", str(cm.exception))

    def test_retry_key_is_namespaced_for_this_app(self):
        import uuid
        self.assertEqual(s.retry_key_for("2026-11-13"),
                         str(uuid.uuid5(uuid.NAMESPACE_URL, "market-weekly/2026-11-13")))

    def test_409_without_key_is_an_error(self):
        op = FakeOpener(http_error(409, '{"message":"conflict"}'))
        with self.assertRaises(s.SendError):
            s.send("hi", "T", "U1", opener=op)

    def test_cli_sends_file_with_key(self):
        import os
        import tempfile
        from unittest import mock
        calls = []

        def fake_send(text, token, user_id, retry_key=None):
            calls.append((text, token, user_id, retry_key))

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "notice.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("今週号\nhttps://example.com/x\n")
            env = {"LINE_CHANNEL_ACCESS_TOKEN": "T", "LINE_USER_ID": "U1"}
            with mock.patch.dict(os.environ, env), mock.patch.object(s, "send", fake_send):
                self.assertEqual(s.main(["--key", "2026-11-13", path]), 0)
                self.assertEqual(s.main([path]), 0)
        self.assertEqual(calls[0][1:], ("T", "U1", "2026-11-13"))
        self.assertIn("https://example.com/x", calls[0][0])
        self.assertIsNone(calls[1][3])

    def test_cli_requires_credentials_and_one_file(self):
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(s.main(["x.txt"]), 2)
        self.assertEqual(s.main([]), 2)
        self.assertEqual(s.main(["--key"]), 2)


if __name__ == "__main__":
    unittest.main()
