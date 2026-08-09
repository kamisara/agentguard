"""
Day 6 validation script.

Tests OtelGenAiTelemetrySource end to end against BOTH real encodings:

  1. Protobuf (application/x-protobuf) - the actual default encoding
     almost every OTel exporter uses, including VS Code Copilot's native
     emission per OpenTelemetry's docs. The test payload here is built
     using the OFFICIAL opentelemetry-proto classes (ExportTraceServiceRequest),
     the same way a real OTel SDK constructs it - this is the strongest
     verification available: genuine wire-format construction, not a
     hand-rolled guess at what protobuf bytes should look like.

  2. JSON (application/json) - the secondary encoding, hand-parsed,
     tested against a realistic hand-built payload (same as before).

Both confirm: a genuine GenAI span is correctly converted to a
CaptureEvent, and a non-GenAI span in the same payload is correctly
ignored.

Run from inside the project root:
    python test_otel_telemetry_source.py
"""

import json
import time
import urllib.request
from datetime import datetime, timezone

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.proto.trace.v1.trace_pb2 import ResourceSpans, ScopeSpans, Span
from opentelemetry.proto.common.v1.common_pb2 import KeyValue, AnyValue, ArrayValue, KeyValueList

from capture.otel_telemetry_source import OtelGenAiTelemetrySource
from capture.manager import CaptureManager
from capture.normalizer import normalize

PORT = 14318  # non-default OTLP port, avoids clashing with a real local Collector


def _kv(key: str, value: AnyValue) -> KeyValue:
    return KeyValue(key=key, value=value)


def _str_val(s: str) -> AnyValue:
    return AnyValue(string_value=s)


def _int_val(i: int) -> AnyValue:
    return AnyValue(int_value=i)


def _message_kv_val(role: str, content: str) -> AnyValue:
    return AnyValue(kvlist_value=KeyValueList(values=[
        _kv("role", _str_val(role)),
        _kv("content", _str_val(content)),
    ]))


def _build_real_protobuf_request() -> bytes:
    """Constructs a genuine ExportTraceServiceRequest using the official
    protobuf classes - exactly how a real OTel SDK would build one before
    serializing and POSTing it. No hand-rolled byte layout guessing."""
    genai_span = Span(
        trace_id=bytes.fromhex("0123456789abcdef0123456789abcdef"[:32]),
        span_id=bytes.fromhex("0123456789abcdef"),
        name="chat gpt-4.1",
        start_time_unix_nano=int(datetime.now(timezone.utc).timestamp() * 1e9),
        attributes=[
            _kv("gen_ai.request.model", _str_val("gpt-4.1")),
            _kv("gen_ai.input.messages", AnyValue(array_value=ArrayValue(values=[
                _message_kv_val("user", "Explain what EMPTY_TREE_HASH does")
            ]))),
            _kv("gen_ai.output.messages", AnyValue(array_value=ArrayValue(values=[
                _message_kv_val("assistant", "It's git's fixed hash representing an empty tree, used to diff a repo's first commit.")
            ]))),
            _kv("gen_ai.usage.input_tokens", _int_val(31)),
            _kv("gen_ai.usage.output_tokens", _int_val(24)),
        ],
    )

    non_genai_span = Span(
        trace_id=bytes.fromhex("0123456789abcdef0123456789abcdef"[:32]),
        span_id=bytes.fromhex("fedcba9876543210"),
        name="http.client",
        start_time_unix_nano=int(datetime.now(timezone.utc).timestamp() * 1e9),
        attributes=[_kv("http.method", _str_val("GET"))],
    )

    request = ExportTraceServiceRequest(
        resource_spans=[
            ResourceSpans(
                scope_spans=[ScopeSpans(spans=[genai_span, non_genai_span])]
            )
        ]
    )
    return request.SerializeToString()


def _post(body: bytes, content_type: str) -> int:
    req = urllib.request.Request(
        f"http://localhost:{PORT}/v1/traces",
        data=body,
        headers={"Content-Type": content_type},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.status


def test_real_protobuf_round_trip():
    print("=== OtelGenAiTelemetrySource: REAL protobuf encoding (official OTel classes) ===")

    received = []
    source = OtelGenAiTelemetrySource(port=PORT)
    manager = CaptureManager(telemetry_sources=[source], native_adapters=[])
    manager.start(on_event=lambda e: received.append(e))
    time.sleep(0.2)

    try:
        body = _build_real_protobuf_request()
        status = _post(body, "application/x-protobuf")
        assert status == 200, f"expected 200, got {status}"

        time.sleep(0.1)

        assert len(received) == 1, (
            f"expected exactly 1 CaptureEvent (non-GenAI span filtered), got {len(received)}"
        )
        event = received[0]

        assert event.adapter == "otel_genai"
        assert event.model == "gpt-4.1"
        assert event.prompt == "Explain what EMPTY_TREE_HASH does", event.prompt
        assert "empty tree" in event.response, event.response
        assert event.metadata["input_tokens"] == 31
        assert event.metadata["output_tokens"] == 24

        print(f"model:    {event.model}")
        print(f"prompt:   {event.prompt}")
        print(f"response: {event.response}")
        print(f"tokens:   in={event.metadata['input_tokens']} out={event.metadata['output_tokens']}")

        normalized = normalize(event)
        assert normalized.intent_source.value == "explicit"
        print(f"intent_source: {normalized.intent_source.value} (expect 'explicit')")

        print("PASS: real protobuf-encoded GenAI span captured correctly\n")
    finally:
        source.stop()


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


def test_json_encoding_round_trip():
    print("=== OtelGenAiTelemetrySource: JSON encoding (secondary path) ===")

    received = []
    source = OtelGenAiTelemetrySource(port=PORT)

    manager = CaptureManager(telemetry_sources=[source], native_adapters=[])
    manager.start(on_event=lambda e: received.append(e))

    time.sleep(0.2)  # let the server thread actually bind before posting

    try:
        body = json.dumps(_build_otlp_payload()).encode("utf-8")
        status = _post(body, "application/json")
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

        print("PASS: JSON-encoded GenAI span captured, non-GenAI span correctly ignored\n")
    finally:
        source.stop()


if __name__ == "__main__":
    test_real_protobuf_round_trip()
    test_json_encoding_round_trip()
    print("OTel GenAI telemetry source tests passed (both encodings).")
