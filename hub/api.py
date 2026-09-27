"""Experimental UI direction: a static page + a tiny JSON API, instead of
Streamlit's server-rendered rerun-everything model (see app.py on `terrace`).
Stdlib only (http.server, json) - no new dependency, so nothing to ask the
team about per AGENTS.md.

Rows are ranked and annotated with status/urgency here (hub.logic/hub.models),
never recomputed in web/ - see web/lib/hub.js's normaliseApiItem().

Read-mostly, localhost-only demo server (POST /api/connect/* opens a
Playwright login window on THIS machine - never expose this past 127.0.0.1).
Try it:  uv run python -m hub.api
"""
import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from hub import brightspace, canvas, db, ics, prairielearn, webwork
from hub.logic import sort_items
from hub.models import Course, Item, classify_urgency, status_of

UI_DIR = Path(__file__).parent.parent / "ui"

# web/'s dev server (npm run dev). Reflected back only for this exact origin,
# never "*" - the connect endpoints trigger a real browser login, so a
# wildcard would let any page on the internet read the response.
ALLOWED_ORIGIN = "http://localhost:3000"


def _item_of(row):
    code, category, kind, title, due, url, done, source = row
    return Item(course=code, category=category, kind=kind, title=title,
                due=datetime.fromisoformat(due) if due else None, url=url, source=source,
                done=bool(done) if done is not None else None)


def _row_to_dict(row, now):
    code, category, kind, title, due, url, done, source = row
    item = _item_of(row)
    return {
        "course": code, "category": category, "kind": kind, "title": title, "due": due, "url": url,
        "source": source,
        "done": bool(done) if done is not None else None,
        "status": status_of(item, now),
        "urgency": classify_urgency(title, item.due, now),
    }


def _upcoming(conn):
    """Ranked rows, never-done (matches app.py's df2e178 rule - hide_overdue
    is a client-side toggle in web/, applied against each row's `status`)."""
    now = datetime.now(timezone.utc)
    rows = [r for r in db.upcoming(conn) if status_of(_item_of(r), now) != "done"]
    rows = sort_items(rows, now)
    return [_row_to_dict(r, now) for r in rows]


def _announcements(conn):
    """Real announcements only - already most-recent-first from db.undated().
    No urgency ranking here, unlike _upcoming(): sort_items() needs a due date
    to rank by, and announcements don't have one.

    db.undated() is every item with no due date, not just announcements - an
    undated Canvas assignment (hub/canvas.py's to_undated_item, #43) or an
    unopened PrairieLearn assessment has no due date either, and used to leak
    into this feed looking like an announcement. Filter to kind="announcement"
    here rather than in db.undated() itself, which other undated items may
    still want to read from later.
    # ponytail: an undated task/deadline has nowhere to surface at all right
    # now (it's excluded here, and _upcoming() requires a due date) - fine
    # until something asks for an "undated tasks" list of its own.
    """
    now = datetime.now(timezone.utc)
    return [_row_to_dict(r, now) for r in db.undated(conn) if r[2] == "announcement"]


def _schedule(conn):
    """Every recurring class meeting, JSON-ready. No status/urgency here -
    those are Item concepts (due-date-relative); a meeting recurs all term,
    so "overdue"/"soon" doesn't apply to it."""
    return [
        {"course": code, "kind": kind, "days": days.split(","), "start_time": start_time,
         "end_time": end_time, "location": location, "term_start": term_start,
         "term_end": term_end, "source": source}
        for code, kind, days, start_time, end_time, location, term_start, term_end, source in db.schedule(conn)
    ]


class Handler(BaseHTTPRequestHandler):
    def _cors_origin(self):
        origin = self.headers.get("Origin")
        return origin if origin == ALLOWED_ORIGIN else None

    def _cors_headers(self):
        origin = self._cors_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def _json(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        """CORS preflight for the connect POSTs (and belt-and-suspenders for
        the GETs) - web/ runs on a different origin (:3000 vs :8000/:8099)."""
        self.send_response(204)
        origin = self._cors_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Vary", "Origin")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/upcoming":
            self._json(_upcoming(db.connect()))
        elif path == "/api/announcements":
            self._json(_announcements(db.connect()))
        elif path == "/api/courses":
            conn = db.connect()
            self._json([{"code": c, "term": t, "title": ti, "grade": g} for c, t, ti, g in db.courses(conn)])
        elif path == "/api/schedule":
            self._json(_schedule(db.connect()))
        elif path in ("/", "/index.html"):
            self._serve_file(UI_DIR / "index.html", "text/html")
        else:
            self._json({"error": "not found"}, status=404)

    def _check_origin(self):
        """Hard-reject a cross-origin POST. A page on an attacker domain that
        resolves to 127.0.0.1 (DNS rebinding) could otherwise trigger a real
        Canvas login or feed fetch - _cors_headers() alone only controls
        whether the *response* is readable, it never stops the request from
        running. A request with no Origin header at all (curl, a non-browser
        client) is let through - only a browser always sends one."""
        origin = self.headers.get("Origin")
        if origin is not None and origin != ALLOWED_ORIGIN:
            self._json({"error": "forbidden origin"}, status=403)
            return False
        return True

    def do_POST(self):
        if not self._check_origin():
            return
        path = urlparse(self.path).path
        if path == "/api/connect/canvas":
            self._connect(canvas.fetch)
        elif path == "/api/connect/prairielearn":
            self._connect(prairielearn.fetch)
        elif path == "/api/connect/brightspace":
            self._connect_brightspace()
        elif path == "/api/connect/webwork":
            self._connect_webwork()
        elif path == "/api/feed":
            self._feed()
        else:
            self._json({"error": "not found"}, status=404)

    def _read_json_body(self):
        """Same guard on both /api/feed implementations (this one and the
        Vercel function, #47): a POST carrying a feed URL - someone's secret
        - must say so explicitly, not be guessed at from an empty/absent
        Content-Type."""
        content_type = self.headers.get("Content-Type", "").split(";")[0].strip()
        if content_type != "application/json":
            raise ValueError("expected Content-Type: application/json")
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            raise ValueError("bad Content-Length")
        if length == 0:
            return {}
        try:
            body = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError("malformed JSON body")
        if not isinstance(body, dict):
            raise ValueError("expected a JSON object body")
        return body

    def _feed(self):
        """POST /api/feed: {url} -> that feed's items, parsed fresh, nothing
        saved. url is never logged - see hub/ics.py's fetch_untrusted() for
        the host allowlist and size/time limits shared with the Vercel
        function (rule 1: one function, not two)."""
        try:
            url = self._read_json_body().get("url", "")
        except ValueError as e:
            return self._json({"error": str(e)}, status=400)
        try:
            items = ics.fetch_untrusted(url, "canvas")
        except ValueError as e:
            return self._json({"error": str(e)}, status=400)
        except Exception as e:  # ponytail: same broad catch as _connect() - a bad/expired/
            # slow feed shouldn't take the server down.
            return self._json({"error": str(e)}, status=502)
        now = datetime.now(timezone.utc)
        self._json([ics.to_dict(i, now) for i in items])

    def _require_https_base(self, base):
        """Brightspace and WeBWorK are both multi-tenant - the student pastes
        their own institution's URL, and this opens a real login browser
        window at whatever comes back. Same trust model as
        hub/prairielearn.py's resolve_campus(): reject anything that isn't a
        real https:// URL outright, rather than let a typo or a non-URL
        string reach Playwright.
        # ponytail: this is the minimal check (https + non-empty host), not
        # resolve_campus()'s full userinfo/IP-literal/localhost hardening -
        # worth porting here too before this leaves local-only demo use."""
        parsed = urlparse(base)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError(f"not a valid https:// URL: {base!r}")

    def _connect_brightspace(self):
        try:
            base = self._read_json_body().get("base", "")
            self._require_https_base(base)
        except ValueError as e:
            return self._json({"ok": False, "error": str(e)}, status=400)
        self._connect(lambda: brightspace.fetch(base))

    def _connect_webwork(self):
        try:
            body = self._read_json_body()
            base, course_code = body.get("base", ""), body.get("course_code", "")
            self._require_https_base(base)
        except ValueError as e:
            return self._json({"ok": False, "error": str(e)}, status=400)
        if not course_code:
            return self._json({"ok": False, "error": "a course code is required"}, status=400)
        # hub/webwork.py's fetch() returns items only (no catalogue join key
        # on its own page) - build the Course record here ourselves, same as
        # its own __main__ block does.
        self._connect(lambda: ([Course(code=course_code, section="", term="", title=course_code)], webwork.fetch(base, course_code)))

    def _connect(self, fetch_fn):
        """Opens a browser window for the student to sign in themselves
        (same flow as app.py's Connect buttons), then saves and returns
        counts. web/ refetches /api/upcoming afterward for the ranked rows."""
        try:
            courses, items = fetch_fn()
        except Exception as e:  # ponytail: one broad catch at the API boundary - a failed
            # login/scrape shouldn't take the server down; the specific adapters already
            # handle their own retries/backoff (hub/site.py). Surface the message as-is.
            return self._json({"ok": False, "error": str(e)}, status=502)
        db.save(db.connect(), courses, items)
        self._json({"ok": True, "courses": len(courses), "items": len(items)})

    def _serve_file(self, path, content_type):
        if not path.exists():
            return self._json({"error": "not found"}, status=404)
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # ponytail: quiet by default; flip this back on if you need to debug requests


def serve(port=8000):
    # 127.0.0.1, not "localhost": binds the literal loopback address, not
    # whatever a machine's /etc/hosts or IPv6 resolution makes "localhost" mean.
    print(f"http://127.0.0.1:{port}  (Ctrl+C to stop)")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    serve()
