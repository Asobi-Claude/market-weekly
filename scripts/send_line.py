"""Push a UTF-8 text file to one LINE user via the Messaging API.

Usage: python scripts/send_line.py [--key KEY] <message_file>
  --key KEY  attach a retry key derived from KEY (use the week's closing date) so LINE
             delivers at most one push for that key
Env:   LINE_CHANNEL_ACCESS_TOKEN, LINE_USER_ID
"""
import json
import os
import sys
import urllib.error
import urllib.request
import uuid

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
MAX_CHARS = 5000
MAX_MESSAGES = 5
SEP = "\n\n"


class SendError(Exception):
    pass


def split_text(text, limit=MAX_CHARS):
    text = text.strip()
    if not text:
        raise ValueError("message is empty")
    pieces = []
    for para in text.split(SEP):
        while len(para) > limit:
            pieces.append(para[:limit])
            para = para[limit:]
        pieces.append(para)
    chunks = []
    for piece in pieces:
        if chunks and len(chunks[-1]) + len(SEP) + len(piece) <= limit:
            chunks[-1] += SEP + piece
        else:
            chunks.append(piece)
    if len(chunks) > MAX_MESSAGES:
        raise ValueError(f"message too long: needs {len(chunks)} messages, max {MAX_MESSAGES}")
    return chunks


def retry_key_for(key):
    """Deterministic UUID per key, so LINE drops a second push for the same week."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"market-weekly/{key}"))


def build_payload(user_id, chunks):
    return {"to": user_id, "messages": [{"type": "text", "text": c} for c in chunks]}


def send(text, token, user_id, opener=urllib.request.urlopen, retry_key=None):
    """retry_key: any stable string (the week's closing date); sent as LINE's X-Line-Retry-Key UUID."""
    body = json.dumps(build_payload(user_id, split_text(text)), ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(LINE_PUSH_URL, data=body, method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    if retry_key:
        req.add_header("X-Line-Retry-Key", retry_key_for(retry_key))
    try:
        with opener(req, timeout=15):
            pass
    except urllib.error.HTTPError as e:
        if e.code == 409 and retry_key:
            return  # this retry key was already accepted: the notice was delivered
        detail = e.read().decode("utf-8", "replace")
        if token:
            detail = detail.replace(token, "***")
        raise SendError(f"LINE {e.code}: {detail}") from None
    except urllib.error.URLError as e:
        raise SendError(f"LINE unreachable: {e.reason}") from None
    except OSError as e:
        raise SendError(f"LINE response timed out or connection dropped; delivery unknown: {e}") from None


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    key = None
    if "--key" in argv:
        at = argv.index("--key")
        if at + 1 >= len(argv):
            print(__doc__, file=sys.stderr)
            return 2
        key = argv[at + 1]
        del argv[at:at + 2]
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    user_id = os.environ.get("LINE_USER_ID")
    if not token or not user_id:
        print("error: set LINE_CHANNEL_ACCESS_TOKEN and LINE_USER_ID", file=sys.stderr)
        return 2
    with open(argv[0], encoding="utf-8") as f:
        text = f.read()
    try:
        send(text, token, user_id, retry_key=key)
    except (SendError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print("sent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
