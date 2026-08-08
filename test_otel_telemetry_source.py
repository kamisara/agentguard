"""
Day 6 validation script.

Tests OtelGenAiTelemetrySource end to end: starts a REAL local HTTP
server (not a mock), sends it a realistic OTLP/HTTP+JSON trace export
payload built from the documented gen_ai.* attribute names (confirmed via
search, Aug 2026 - see capture/otel_genai_parser.py for exact sourcing and
caveats), and confirms:

  1. A genuine GenAI span is correctly converted to a CaptureEvent with
     the right prompt/response/model/tokens.
  2. A non-GenAI span (e.g. a plain HTTP client span) in the SAME payload
     is correctly ignored, not accidentally captured.
  3. CaptureManager's telemetry-first branch actually receives the event
     through the real subscribe() callback, not a fake one.

Run from inside the project root:
    python test_otel_telemetry_source.py
"""

import json
import time
import urllib.request
from datetime import datetime, timezone

from capture.otel_telemetry_source import OtelGenAiTelemetrySource
from capture.manager import CaptureManager
from capture.normalizer import normalize

PORT = 14318  # non-default OTLP port, avoids clashing with a real local Collector


def _build_otlp_payload():
    now_ns = int(datetime.now(timezone.utc).timestamp() * 1e9)

    def kv(role, content):
        return {
            "kvlistValue": {
                "values": [
                    {"key": "role", "value": {"stringValue": role}},
                    {"key": "content", "value": {"stringValue": content}},
                ]
            }
        }

    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "test-agent"}}
                    ]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            # Real GenAI span - should be captured
                            {
                                "traceId": "abc123",
                                "spanId": "span001",
                                "name": "chat gpt-4.1",
                                "startTimeUnixNano": str(now_ns),
                                "attributes": [
                                    {"key": "gen_ai.request.model", "value": {"stringValue": "gpt-4.1"}},
                                    {"key": "gen_ai.input.messages", "value": {"arrayValue": {
                                        "values": [kv("user", "Fix the null check in parseConfig")]
                                    }}},
                                    {"key": "gen_ai.output.messages", "value": {"arrayValue": {
                                        "values": [kv("assistant", "Added a null guard before accessing config.env.")]
                                    }}},
                                    {"key": "gen_ai.usage.input_tokens", "value": {"intValue": "42"}},
                                    {"key": "gen_ai.usage.output_tokens", "value": {"intValue": "18"}},
                                    {"key": "gen_ai.response.finish_reasons", "value": {"arrayValue": {
                                        "values": [{"stringValue": "stop"}]
                                    }}},
                                ],
                            },
                            # Non-GenAI span in the SAME payload - must be ignored
                            {
                                "traceId": "abc123",
                                "spanId": "span002",
                                "name": "http.client",
                                "startTimeUnixNano": str(now_ns),
                                "attributes": [
                                    {"key": "http.method", "value": {"stringValue": "GET"}},
                                ],
                            },
                        ]
                    }
                ],
            }
        ]
    }


def _post_otlp(payload: dict):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"http://localhost:{PORT}/v1/traces",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.status


def test_real_http_round_trip():
    print("=== OtelGenAiTelemetrySource: real HTTP server round trip ===")

    received = []
    source = OtelGenAiTelemetrySource(port=PORT)

    manager = CaptureManager(telemetry_sources=[source], native_adapters=[])
    manager.start(on_event=lambda e: received.append(e))

    time.sleep(0.2)  # let the server thread actually bind before posting

    try:
        status = _post_otlp(_build_otlp_payload())
        assert status == 200, f"expected 200, got {status}"

        time.sleep(0.1)  # let the handler finish invoking the callback

        assert len(received) == 1, (
            f"expected exactly 1 CaptureEvent (non-GenAI span should be "
            f"filtered out), got {len(received)}"
        )
        event = received[0]

        assert event.adapter == "otel_genai"
        assert event.model == "gpt-4.1"
        assert event.prompt == "Fix the null check in parseConfig", event.prompt
        assert event.response == "Added a null guard before accessing config.env.", event.response
        assert event.metadata["input_tokens"] == 42
        assert event.metadata["output_tokens"] == 18

        print(f"model:    {event.model}")
        print(f"prompt:   {event.prompt}")
        print(f"response: {event.response}")
        print(f"tokens:   in={event.metadata['input_tokens']} out={event.metadata['output_tokens']}")

        normalized = normalize(event)
        assert normalized.intent_source.value == "explicit"
        print(f"intent_source: {normalized.intent_source.value} (expect 'explicit')")

        print("PASS: real GenAI span captured, non-GenAI span correctly ignored\n")
    finally:
        source.stop()


if __name__ == "__main__":
    test_real_http_round_trip()
    print("OTel GenAI telemetry source test passed.")
