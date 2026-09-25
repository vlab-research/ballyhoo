"""The review server: the review page for a run, or every run of a brief, on 127.0.0.1.

The shell for review.py and verdicts.py, through runs.py. It holds no state:
GET / serves the page built from the runs as they are on disk, so a run made
while it is up appears on the next load; GET /state answers what the page polls
to notice one; GET of any other path serves that file from inside the run or
runs directory and nothing outside it; POST /verdicts?run=NAME validates the
posted verdicts and writes that run's verdicts.yaml whole, or writes nothing and
answers 400 with every problem.
"""
import json
import mimetypes
import shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from . import review, runs

HOST = "127.0.0.1"  # never every interface: the server writes into runs and serves their files
MAX_BODY = 10 * 1024 * 1024


def run_file(root, request_path):
    """The file in `root` a request path names, or None when it names no file or one outside it."""
    relative = unquote(urlsplit(request_path).path).lstrip("/")
    if "\x00" in relative:
        return None
    path = (root / relative).resolve()
    return path if path.is_relative_to(root) and path.is_file() else None


def handler(root, providers):
    root = Path(root).resolve()
    single = runs.is_run(root)

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
            request = urlsplit(self.path).path
            if request in ("/", f"/{review.PAGE}"):
                return self.send(200, runs.served_page(root, single, providers).encode(), "text/html; charset=utf-8")
            if request == "/state":
                return self.send_json(200, runs.state(root, single))
            path = run_file(root, self.path)
            if path is None:
                return self.send(404, b"no such file here", "text/plain; charset=utf-8")
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(path.stat().st_size))
            self.end_headers()
            with path.open("rb") as f:
                shutil.copyfileobj(f, self.wfile)

        def do_POST(self):
            if not self.from_this_host():
                return
            request = urlsplit(self.path)
            if request.path != "/verdicts":
                return self.send_json(404, {"errors": ["verdicts are posted to /verdicts?run=NAME"]})
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
            name = parse_qs(request.query).get("run", [None])[0]
            run = next((r for r in runs.served(root, single) if r.name == name), None)
            if run is None:
                return self.send_json(404, {"errors": [f"no run {name!r} here to save verdicts to"]})
            reply, errors = runs.save_verdicts(run, providers, data)
            if errors:
                return self.send_json(400, {"errors": errors})
            self.send_json(200, reply)

    return Handler


def make_server(root, providers, port=0):
    """A review server on 127.0.0.1 for a run, or for every run in a runs directory; port 0 takes any
    free port. Call serve_forever to serve."""
    return ThreadingHTTPServer((HOST, port), handler(root, providers))


def url(server):
    host, port = server.server_address[:2]
    return f"http://{host}:{port}/"
