"""
Decodes REAL OTLP/HTTP protobuf trace export requests using the official
generated protobuf classes from the `opentelemetry-proto` package - the
exact schema real OTel SDKs and Collectors use. This is genuine wire-format
compatibility, not a hand-rolled approximation of the format.

WHY THIS MATTERS: protobuf (content-type application/x-protobuf) is the
DEFAULT binary encoding almost every OTel exporter uses out of the box -
including, per OpenTelemetry's own documentation, VS Code Copilot's native
GenAI telemetry emission. otel_genai_parser.py's JSON path
(application/json) is a real but secondary encoding some exporters support
as an alternative. A receiver that only accepted JSON would silently miss
most real-world traffic, since JSON isn't what ships by default.

REQUIRES: pip install opentelemetry-proto (pulls in `protobuf` as a
dependency). This is the only external dependency in the whole capture
layer - everything else deliberately uses stdlib only.

Converts decoded protobuf spans into the same (span_meta, attrs) shape
otel_genai_parser._span_to_event expects, so GenAI detection/extraction
logic is NOT duplicated between the two encodings - only decoding differs.
"""

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from opentelemetry.proto.common.v1.common_pb2 import AnyValue

from .otel_genai_parser import _is_genai_span, _span_to_event
from .types import CaptureEvent


def _any_value_to_python(value: AnyValue):
    """Mirrors otel_genai_parser._otlp_value_to_python, but for protobuf's
    oneof-typed AnyValue instead of JSON's typed-wrapper dicts."""
    kind = value.WhichOneof("value")
    if kind == "string_value":
        return value.string_value
    if kind == "int_value":
        return value.int_value
    if kind == "double_value":
        return value.double_value
    if kind == "bool_value":
        return value.bool_value
    if kind == "array_value":
        return [_any_value_to_python(v) for v in value.array_value.values]
    if kind == "kvlist_value":
        return {kv.key: _any_value_to_python(kv.value) for kv in value.kvlist_value.values}
    if kind == "bytes_value":
        return value.bytes_value
    return None


def _pb_attrs_to_dict(attributes) -> dict:
    return {kv.key: _any_value_to_python(kv.value) for kv in attributes}


def parse_otlp_protobuf(body: bytes) -> list:
    """Parses a raw OTLP/HTTP protobuf request body - the actual bytes a
    real OTel exporter (including VS Code Copilot's native emission, per
    OpenTelemetry's docs) would POST to /v1/traces by default. Returns a
    list of CaptureEvents, one per span that looks like a GenAI operation -
    identical filtering logic to the JSON path, since both funnel through
    otel_genai_parser._span_to_event.

    trace_id/span_id are raw bytes in the protobuf wire format; converted
    to hex strings here for readability - a formatting choice, not
    something the spec mandates for downstream consumers.
    """
    request = ExportTraceServiceRequest()
    request.ParseFromString(body)  # raises google.protobuf.message.DecodeError on malformed input

    events = []
    for resource_span in request.resource_spans:
        for scope_span in resource_span.scope_spans:
            for span in scope_span.spans:
                attrs = _pb_attrs_to_dict(span.attributes)
                if _is_genai_span(attrs):
                    span_meta = {
                        "traceId": span.trace_id.hex(),
                        "spanId": span.span_id.hex(),
                        "name": span.name,
                        "startTimeUnixNano": str(span.start_time_unix_nano),
                    }
                    events.append(_span_to_event(span_meta, attrs))
    return events
