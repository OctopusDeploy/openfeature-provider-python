"""A fake Octopus feature flags service for tests that drive the provider.

It serves the evaluations and check endpoints, records every request, and
lets each test set the status, body, ContentHash header and delay of each
endpoint's response.
"""

import base64
import json
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from octopus_openfeature_provider import OctopusFeatureConfiguration, ProductMetadata

EVALUATIONS_PATH = "/api/feature-flags/evaluations/v4/"
CHECK_PATH = "/api/feature-flags/check/v4/"

DEFAULT_CONTENT_HASH = base64.b64encode(b"\x01").decode()


def check_body(content_hash: str) -> str:
    """The body the check endpoint returns for a base64 content hash."""
    return json.dumps({"contentHash": content_hash})


@dataclass
class FakeResponse:
    status: int = 200
    body: str | bytes = "[]"
    # Sent as the ContentHash header when not None.
    content_hash: str | None = DEFAULT_CONTENT_HASH
    # Seconds to wait before responding.
    delay: float = 0


@dataclass(frozen=True)
class RecordedRequest:
    path: str
    # Keyed by lower-case header name.
    headers: dict[str, str]

    def header(self, name: str) -> str | None:
        return self.headers.get(name.lower())


@dataclass
class FakeFeatureFlagsServer:
    url: str
    evaluations: FakeResponse = field(default_factory=FakeResponse)
    check: FakeResponse = field(
        default_factory=lambda: FakeResponse(
            body=check_body(DEFAULT_CONTENT_HASH), content_hash=None
        )
    )
    _requests: list[RecordedRequest] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    # Set on close, so a delayed response doesn't outlive the test.
    _closed: threading.Event = field(default_factory=threading.Event)

    @property
    def requests(self) -> list[RecordedRequest]:
        with self._lock:
            return list(self._requests)

    def requests_to(self, path: str) -> list[RecordedRequest]:
        return [request for request in self.requests if request.path == path]

    def _record(self, request: RecordedRequest) -> None:
        with self._lock:
            self._requests.append(request)

    def _response_for(self, path: str) -> FakeResponse | None:
        if path == EVALUATIONS_PATH:
            return self.evaluations
        if path == CHECK_PATH:
            return self.check
        return None


def _handler_for(server: FakeFeatureFlagsServer) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            server._record(
                RecordedRequest(
                    path=self.path,
                    headers={
                        name.lower(): value for name, value in self.headers.items()
                    },
                )
            )

            response = server._response_for(self.path)
            if response is None:
                self.send_error(404)
                return

            if response.delay and server._closed.wait(response.delay):
                return

            body = (
                response.body.encode()
                if isinstance(response.body, str)
                else response.body
            )
            self.send_response(response.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            if response.content_hash is not None:
                self.send_header("ContentHash", response.content_hash)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            # Keep test output quiet.
            pass

    return Handler


def configuration_for(
    server: FakeFeatureFlagsServer, **options: Any
) -> OctopusFeatureConfiguration:
    configuration = OctopusFeatureConfiguration(
        "client-identifier", ProductMetadata("test-product"), **options
    )
    configuration._server_url = server.url
    return configuration


def run_fake_feature_flags_server() -> Iterator[FakeFeatureFlagsServer]:
    """Start a server on a free local port, and stop it afterwards."""
    fake = FakeFeatureFlagsServer(url="")
    http_server = ThreadingHTTPServer(("127.0.0.1", 0), _handler_for(fake))
    http_server.daemon_threads = True
    http_server.block_on_close = False
    fake.url = f"http://127.0.0.1:{http_server.server_address[1]}"

    # shutdown() waits for the next poll, so keep it short.
    thread = threading.Thread(
        target=http_server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    try:
        yield fake
    finally:
        fake._closed.set()
        http_server.shutdown()
        http_server.server_close()
        thread.join()
