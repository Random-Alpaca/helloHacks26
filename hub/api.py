"""Experimental UI direction: a static page + a tiny JSON API, instead of
Streamlit's server-rendered rerun-everything model (see app.py on `terrace`).
Stdlib only (http.server, json) - no new dependency, so nothing to ask the
team about per AGENTS.md.

Read-only, localhost-only demo server. Try it:  uv run python -m hub.api
"""
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from hub import db

UI_DIR = Path(__file__).parent.parent / "ui"


def _row_to_dict(row):
    code, category, kind, title, due, url, done = row
    return {"course": code, "category": category, "kind": kind, "title": title, "due": due, "url": url, "done": bool(done) if done is not None else None}


class Handler(BaseHTTPRequestHandler):
    def _json(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/upcoming":
            conn = db.connect()
            self._json([_row_to_dict(r) for r in db.upcoming(conn)])
        elif path == "/api/courses":
            conn = db.connect()
            self._json([{"code": c, "term": t, "title": ti, "grade": g} for c, t, ti, g in db.courses(conn)])
        elif path in ("/", "/index.html"):
            self._serve_file(UI_DIR / "index.html", "text/html")
        else:
            self._json({"error": "not found"}, status=404)

    def _serve_file(self, path, content_type):
        if not path.exists():
            return self._json({"error": "not found"}, status=404)
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # ponytail: quiet by default; flip this back on if you need to debug requests


def serve(port=8000):
    print(f"http://localhost:{port}  (Ctrl+C to stop)")
    ThreadingHTTPServer(("localhost", port), Handler).serve_forever()


if __name__ == "__main__":
    serve()
