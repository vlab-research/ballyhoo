"""The review server: one run's review page on 127.0.0.1, saving verdicts.yaml when the page posts.

The shell for review.py and verdicts.py, through runs.py. GET / serves the page
built from the run as it is on disk; GET of any other path serves that file from
the run and nothing outside it; POST /verdicts validates the posted verdicts and
writes verdicts.yaml whole, or writes nothing and answers 400 with every problem.
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

        def do_GET(self):
            if not self.from_this_host():
                return
            if urlsplit(self.path).path in ("/", f"/{review.PAGE}"):
                r, errors = runs.read_review(run, providers)
                if errors:
                    return self.send(500, "\n".join(errors).encode(), "text/plain; charset=utf-8")
                return self.send(200, runs.review_page(r, editable=True).encode(), "text/html; charset=utf-8")
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
            if urlsplit(self.path).path != "/verdicts":
                return self.send_json(404, {"errors": ["verdicts are posted to /verdicts"]})
            # Another site's form can post text/plain to this server without the browser asking first, but not JSON.
            if self.headers.get_content_type() != "application/json":
                return self.send_json(415, {"errors": ["verdicts must be sent as application/json"]})
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                return self.send_json(411, {"errors": ["a save needs a Content-Length"]})
            if length > MAX_BODY:
                return self.send_json(413, {"errors": [f"a save is at most {MAX_BODY} bytes"]})
            try:
                data = json.loads(self.rfile.read(length))
            except ValueError as e:
                return self.send_json(400, {"errors": [f"not JSON: {e}"]})
            reply, errors = runs.save_verdicts(run, providers, data)
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
