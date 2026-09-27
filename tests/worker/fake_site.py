import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


@dataclass
class FakeSite:
    """Local HTTP server standing in for monitored sites."""

    base_url: str
    port: int
    requests: list[str] = field(default_factory=list)

    def url(self, path: str) -> str:
        return f"{self.base_url}{path}"


def _handler(site: FakeSite) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            site.requests.append(self.path)
            parts = urlsplit(self.path)
            match parts.path:
                case "/ok":
                    self._reply(200)
                case "/error":
                    self._reply(500)
                case "/slow":
                    time.sleep(2)
                    self._reply(200)
                case "/redirect":
                    self._reply(302, location=parse_qs(parts.query)["to"][0])
                case "/loop":
                    self._reply(302, location="/loop")
                case _:
                    self._reply(404)

        def _reply(self, status: int, location: str | None = None) -> None:
            self.send_response(status)
            if location:
                self.send_header("Location", location)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:
            pass

    return Handler


@contextmanager
def serve_fake_site() -> Iterator[FakeSite]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    server.daemon_threads = True
    server.block_on_close = False
    port = server.server_address[1]
    site = FakeSite(base_url=f"http://127.0.0.1:{port}", port=port)
    server.RequestHandlerClass = _handler(site)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield site
    finally:
        server.shutdown()
        server.server_close()
