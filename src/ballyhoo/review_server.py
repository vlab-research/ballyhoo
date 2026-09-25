"""The review server: one run's review pages on 127.0.0.1, saving what a page posts.

The shell for review.py, verdicts.py and comparisons.py, through runs.py. GET /
serves the review page and GET /pairs the pairwise page, both built from the run
as it is on disk; GET of any other path serves that file from the run and
nothing outside it. A POST is validated before anything is written, and a save
that is refused writes nothing and answers 400 with every problem.
"""
import json
import mimetypes
import shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from . import review, runs

HOST = "127.0.0.1"  # never every interface: the server writes into the run and serves its files
MAX_BODY = 10 * 1024 * 1024
PAIRS = "/pairs"
SAVES = {"/verdicts": runs.save_verdicts, "/comparisons": runs.save_comparison,
         "/comparisons/undo": runs.undo_comparison}


def run_file(run, request_path):
    """The file in `run` a request path names, or None when it names no file or one outside the run."""
    relative = unquote(urlsplit(request_path).path).lstrip("/")
    if "\x00" in relative:
        return None
    path = (run / relative).resolve()
    return path if path.is_relative_to(run) and path.is_file() else None


def handler(run, providers):
    run = Path(run).resolve()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass  # a request line for every thumbnail buries the URL the command prints

        def send(self, status, body, content_type):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def send_json(self, status, data):
            self.send(status, json.dumps(data, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def from_this_host(self):
            # A page on another site that rebinds its own host name to 127.0.0.1 still sends that name.
            port = self.server.server_address[1]
            if self.headers.get("Host") in (f"{HOST}:{port}", f"localhost:{port}"):
                return True
            self.send(403, b"requests must be addressed to 127.0.0.1 or localhost", "text/plain; charset=utf-8")
            return False

        def json_body(self):
            """(True, the posted JSON), or (False, None) when it has already answered the request."""
            # Another site's form can post text/plain to this server without the browser asking first, but not JSON.
            if self.headers.get_content_type() != "application/json":
                self.send_json(415, {"errors": ["a save must be sent as application/json"]})
                return False, None
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                self.send_json(411, {"errors": ["a save needs a Content-Length"]})
                return False, None
            if length > MAX_BODY:
                self.send_json(413, {"errors": [f"a save is at most {MAX_BODY} bytes"]})
                return False, None
            try:
                return True, json.loads(self.rfile.read(length))
            except ValueError as e:
                self.send_json(400, {"errors": [f"not JSON: {e}"]})
                return False, None

        def do_GET(self):
            if not self.from_this_host():
                return
            request = urlsplit(self.path).path
            if request in ("/", f"/{review.PAGE}", PAIRS):
                r, errors = runs.read_review(run, providers)
                if errors:
                    return self.send(500, "\n".join(errors).encode(), "text/plain; charset=utf-8")
                page = runs.pairs_page(r) if request == PAIRS else runs.review_page(r, editable=True)
                return self.send(200, page.encode(), "text/html; charset=utf-8")
            path = run_file(run, self.path)
            if path is None:
                return self.send(404, b"no such file in this run", "text/plain; charset=utf-8")
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(path.stat().st_size))
            self.end_headers()
            with path.open("rb") as f:
                shutil.copyfileobj(f, self.wfile)

        def do_POST(self):
            if not self.from_this_host():
                return
            request = urlsplit(self.path).path
            if request not in SAVES:
                return self.send_json(404, {"errors": [f"nothing is posted to {request} "
                                                       f"(saves: {', '.join(sorted(SAVES))})"]})
            ok, data = self.json_body()
            if not ok:
                return
            reply, errors = SAVES[request](run, providers, data)
            if errors:
                return self.send_json(400, {"errors": errors})
            self.send_json(200, reply)

    return Handler


def make_server(run, providers, port=0):
    """A server for one run's review page on 127.0.0.1; port 0 takes any free port. Call serve_forever to serve."""
    return ThreadingHTTPServer((HOST, port), handler(run, providers))


def url(server):
    host, port = server.server_address[:2]
    return f"http://{host}:{port}/"
