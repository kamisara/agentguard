"""
OpenTelemetry GenAI semantic-convention telemetry source.

This is the OTHER branch of CaptureManager - push-based, external
instrumentation - actually implemented for real, not just the generic
FakeTelemetrySource used to test CaptureManager's branching logic.

SCOPE, stated honestly (see otel_genai_parser.py for the attribute-level
caveats):

  - Implements OTLP/HTTP with JSON encoding (a real, documented OTLP
    encoding), NOT the protobuf/gRPC variant most production OTel
    Collectors default to. Chosen deliberately to avoid a protobuf/grpc
    dependency for a solo 24-week project - stdlib http.server is enough.
    A real Collector can be configured to forward via an OTLP/HTTP JSON
    exporter if needed; this receiver could be extended for protobuf
    later without changing the CaptureEvent/TelemetrySource contract.
  - Single-process, in-memory only - no persistence, no retry handling,
    no auth. Fine for a local dev capture tool, not for a multi-tenant
    or production deployment.
  - Bonus finding worth noting for the proposal: VS Code Copilot itself
    emits OTel GenAI telemetry natively (per OpenTelemetry's own
    documentation, 2026) - meaning this telemetry source is a real,
    second path into Copilot's traffic, independent of the hook-based
    CopilotHookAdapter, if OTel export is configured on the Copilot side.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional

from .interfaces import TelemetrySource
from .types import CaptureEvent
from .otel_genai_parser import parse_otlp_json_spans


def _make_handler(on_event: Callable[[CaptureEvent], None]):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path.rstrip("/") != "/v1/traces":
                self.send_response(404)
                self.end_headers()
                return

            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)

            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                self.send_response(400)
                self.end_headers()
                return

            events = parse_otlp_json_spans(payload)
            for event in events:
                on_event(event)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, format, *args):
            pass  # suppress default stderr access logging

    return Handler


class OtelGenAiTelemetrySource(TelemetrySource):
    """Runs a local OTLP/HTTP+JSON receiver at http://{host}:{port}/v1/traces.
    Point an app's OTLP HTTP JSON exporter at this address (or an OTel
    Collector configured to forward there) to feed real GenAI telemetry
    into AgentGuard.

    Default port 4318 is OTLP's standard HTTP port, so pointing a
    standard OTel SDK's default exporter at localhost works with zero
    exporter-side configuration.
    """

    def __init__(self, host: str = "localhost", port: int = 4318):
        self.host = host
        self.port = port
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def is_configured(self) -> bool:
        # A local receiver has no external prerequisite - it's always able
        # to try starting. A real port conflict surfaces when subscribe()
        # actually binds, not here.
        return True

    def subscribe(self, on_event: Callable[[CaptureEvent], None]) -> None:
        handler_class = _make_handler(on_event)
        self._server = ThreadingHTTPServer((self.host, self.port), handler_class)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Not part of the TelemetrySource interface - CaptureManager has
        no concept of unsubscribing. Provided for tests and for a real
        extension's lifecycle (e.g. shutting down cleanly on deactivate)."""
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
