import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pathlib
import urllib.parse

from arthur_config import get_config, get_path
from arthur_status_dashboard import build_html


SCRATCH = get_path(
    "runtime.scratchpadPath",
    str(pathlib.Path(__file__).resolve().parent),
)
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = int(get_config("dashboard.port", 8765))
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "ArthurDashboard/1.0"

    def send_security_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; "
            "script-src 'unsafe-inline'; frame-ancestors 'none'",
        )
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/healthz":
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_security_headers()
            self.end_headers()
            self.wfile.write(b"ok")
            return
        if parsed.path not in {"/", "/dashboard"}:
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return

        body = build_html().encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_security_headers()
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Serve the Arthur status dashboard on localhost."
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    if args.host.lower() not in LOOPBACK_HOSTS:
        parser.error("Arthur dashboard host must be a loopback address.")

    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(
        f"Arthur dashboard serving at "
        f"http://{args.host}:{args.port}/dashboard",
        flush=True,
    )
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
