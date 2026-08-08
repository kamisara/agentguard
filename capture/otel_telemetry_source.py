"""
OpenTelemetry GenAI semantic-convention telemetry source.

This is the OTHER branch of CaptureManager - push-based, external
instrumentation - actually implemented for real, not just the generic
FakeTelemetrySource used to test CaptureManager's branching logic.

SCOPE, stated honestly (see otel_genai_parser.py / otlp_protobuf_parser.py
for the attribute-level caveats):

  - Implements OTLP/HTTP with BOTH real encodings: protobuf
    (application/x-protobuf, the actual default almost every OTel
    exporter uses - decoded via the official `opentelemetry-proto`
    generated classes, genuine wire-format compatibility) and JSON
    (application/json, a real but secondary encoding, hand-parsed).
    Does NOT implement gRPC (port 4317, the OTHER common default) -
    that would require the grpcio dependency and a full gRPC service
    implementation, out of scope for now. A Collector or exporter can be
    pointed at this HTTP endpoint instead.
  - Single-process, in-memory only - no persistence, no retry handling,
    no auth. Fine for a local dev capture tool, not for a multi-tenant
    or production deployment.
  - Bonus finding worth noting for the proposal: VS Code Copilot itself
    emits OTel GenAI telemetry natively (per OpenTelemetry's own
    documentation, 2026), using the protobuf encoding by default - meaning
    the protobuf path here is what actually matters for capturing real
    Copilot traffic through this route, not the JSON path.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional

from .interfaces import TelemetrySource
from .types import CaptureEvent
from .otel_genai_parser import parse_otlp_json_spans
from .otlp_protobuf_parser import parse_otlp_protobuf


def _make_handler(on_event: Callable[[CaptureEvent], None]):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            content_type = self.headers.get("Content-Type", "").split(";")[0].strip()

            # DEBUG: print every incoming request unconditionally, before
            # any parsing/filtering - this is the only way to tell "nothing
            # arrived" apart from "something arrived but didn't parse".
            print(
                f"[otel-receiver] POST {self.path} "
                f"content-type={content_type!r} bytes={length}"
            )

            if self.path.rstrip("/") != "/v1/traces":
                print(f"[otel-receiver]   -> 404, unexpected path")
                self.send_response(404)
                self.end_headers()
                return

            body = self.rfile.read(length)

            try:
                if content_type == "application/x-protobuf":
                    events = parse_otlp_protobuf(body)
                elif content_type == "application/json":
                    payload = json.loads(body)
                    events = parse_otlp_json_spans(payload)
                else:
                    print(f"[otel-receiver]   -> 415, unsupported content-type")
                    self.send_response(415)
                    self.end_headers()
                    return
            except Exception as e:
                print(f"[otel-receiver]   -> 400, parse failed: {e!r}")
                self.send_response(400)
                self.end_headers()
                return

            print(f"[otel-receiver]   -> parsed {len(events)} GenAI span(s)")
            for event in events:
                on_event(event)

            self.send_response(200)
            self.send_header("Content-Type", "application/x-protobuf" if content_type == "application/x-protobuf" else "application/json")
            self.end_headers()
            self.wfile.write(b"")

        def log_message(self, format, *args):
            pass  # suppress default stderr access logging (we print our own above)

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
