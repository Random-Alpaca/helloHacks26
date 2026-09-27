"""Vercel Python serverless function: POST /api/feed (#47).

The hosted site's counterpart to hub/api.py's /api/feed - same job (a
student pastes their Canvas calendar-feed URL, this fetches and parses it
server-side, since Canvas sends no CORS headers), different runtime.
Reuses hub/ics.py's fetch_untrusted()/to_dict() rather than reimplementing
the host allowlist, size/time limits or item parsing here (rule 1: one
parser, not two) - this file is only the HTTP glue Vercel's Python runtime
expects.

Vercel's Root Directory is `web/`, so hub/ (one level up, at the actual
repo root) is outside it by default - needs the project's "include files
outside the Root Directory" build setting (or the equivalent vercel.json
`functions.includeFiles`) turned on, or this import fails at deploy time.
"""
import json
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hub import ics  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def _json(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        content_type = self.headers.get("Content-Type", "").split(";")[0].strip()
        if content_type != "application/json":
            return self._json({"error": "expected Content-Type: application/json"}, 400)
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        url = body.get("url", "")
        try:
            items = ics.fetch_untrusted(url, "canvas")
        except ValueError as e:
            return self._json({"error": str(e)}, 400)
        except Exception as e:  # ponytail: same broad catch as hub/api.py's _feed() -
            # a bad/expired/slow feed shouldn't 500 the function.
            return self._json({"error": str(e)}, 502)
        now = datetime.now(timezone.utc)
        self._json([ics.to_dict(i, now) for i in items])
