"""
Parses OTLP/HTTP+JSON trace export payloads for GenAI semantic-convention
spans, converting matching spans into CaptureEvents.

SCOPE AND HONESTY NOTES:

- Grounded in documented gen_ai.* attribute names (confirmed via search,
  Aug 2026): gen_ai.request.model, gen_ai.input.messages,
  gen_ai.output.messages, gen_ai.system_instructions,
  gen_ai.response.finish_reasons, gen_ai.usage.input_tokens/output_tokens.
- These conventions are explicitly Development-status as of this writing -
  no 1.0 release, names can still change (unlike the hook hook_shared
  format findings, this was confirmed from documentation, NOT from a real
  emitted payload - no live GenAI-instrumented app was available to test
  against). Treat this parser the same way the original Copilot transcript
  assumption should have been treated: correct on paper, unverified in
  practice, isolated so it's easy to fix if wrong.
- The exact nested JSON shape of gen_ai.input.messages / .output.messages
  content is not fully confirmed - handles the two most plausible OTLP
  representations defensively: a list of kvlistValue objects (structured
  {"role": ..., "content": ...} per OTLP's native nested-object type,
  which is what a spec-compliant exporter would emit for chat messages),
  and a flat list of strings (a simpler fallback some exporters might use).
  If a real exporter's payload differs, only _messages_to_text needs
  adjusting.

OTLP/HTTP+JSON structure (per the OTLP spec): a trace export payload is
{"resourceSpans": [{"resource": {...}, "scopeSpans": [{"spans": [...]}]}]}.
Each span has "name", "attributes" (list of {"key", "value": {typed
wrapper}}), "startTimeUnixNano", "traceId", "spanId".
"""

from datetime import datetime, timezone
from typing import List

from .types import CaptureEvent


def _otlp_value_to_python(value: dict):
    """OTLP JSON values are typed wrappers, e.g. {"stringValue": "..."}.
    Unwraps to a plain Python value. kvlistValue (nested key-value object)
    and arrayValue (list) recurse."""
    if "stringValue" in value:
        return value["stringValue"]
    if "intValue" in value:
        return int(value["intValue"])
    if "doubleValue" in value:
        return value["doubleValue"]
    if "boolValue" in value:
        return value["boolValue"]
    if "arrayValue" in value:
        return [_otlp_value_to_python(v) for v in value["arrayValue"].get("values", [])]
    if "kvlistValue" in value:
        return _attrs_to_dict(value["kvlistValue"].get("values", []))
    return None


def _attrs_to_dict(attributes: list) -> dict:
    result = {}
    for attr in attributes or []:
        key = attr.get("key")
        value = attr.get("value", {})
        if key:
            result[key] = _otlp_value_to_python(value)
    return result


def _is_genai_span(attrs: dict) -> bool:
    """A span is treated as a GenAI operation if it carries the one
    attribute every gen_ai.* span is required to have: the request model
    name. Deliberately conservative - spans from unrelated instrumentation
    (HTTP client spans, DB spans, etc.) in the same OTLP payload are
    ignored rather than guessed at."""
    return "gen_ai.request.model" in attrs


def _messages_to_text(messages) -> str:
    """See module docstring for the shape uncertainty this handles."""
    if not messages:
        return ""
    if isinstance(messages, str):
        return messages
    if not isinstance(messages, list):
        return str(messages)

    parts = []
    for msg in messages:
        if isinstance(msg, dict):
            content = msg.get("content", "")
            if isinstance(content, str) and content:
                parts.append(content)
        elif isinstance(msg, str) and msg:
            parts.append(msg)
    return "\n".join(parts)


def _span_to_event(span_meta: dict, attrs: dict) -> CaptureEvent:
    """span_meta: {"traceId", "spanId", "name", "startTimeUnixNano"}.
    Takes pre-extracted metadata and attributes rather than a raw
    encoding-specific span object, so this one function is shared between
    the JSON path (parse_otlp_json_spans) and the protobuf path
    (otlp_protobuf_parser.parse_otlp_protobuf) - only decoding differs
    between encodings, not GenAI extraction logic."""
    start_time_ns = span_meta.get("startTimeUnixNano")
    if start_time_ns:
        timestamp = datetime.fromtimestamp(int(start_time_ns) / 1e9, tz=timezone.utc)
    else:
        timestamp = datetime.now(timezone.utc)

    return CaptureEvent(
        adapter="otel_genai",
        timestamp=timestamp,
        prompt=_messages_to_text(attrs.get("gen_ai.input.messages")),
        response=_messages_to_text(attrs.get("gen_ai.output.messages")),
        model=attrs.get("gen_ai.request.model"),
        session_id=span_meta.get("traceId"),
        metadata={
            "span_id": span_meta.get("spanId"),
            "span_name": span_meta.get("name"),
            "finish_reasons": attrs.get("gen_ai.response.finish_reasons"),
            "system_instructions": attrs.get("gen_ai.system_instructions"),
            "input_tokens": attrs.get("gen_ai.usage.input_tokens"),
            "output_tokens": attrs.get("gen_ai.usage.output_tokens"),
        },
    )


def parse_otlp_json_spans(payload: dict) -> List[CaptureEvent]:
    """Walks the full resourceSpans -> scopeSpans -> spans hierarchy,
    returns a CaptureEvent for every span that looks like a GenAI
    operation. Non-GenAI spans in the same payload are silently skipped."""
    events = []
    for resource_span in payload.get("resourceSpans", []):
        for scope_span in resource_span.get("scopeSpans", []):
            for span in scope_span.get("spans", []):
                attrs = _attrs_to_dict(span.get("attributes", []))
                if _is_genai_span(attrs):
                    span_meta = {
                        "traceId": span.get("traceId"),
                        "spanId": span.get("spanId"),
                        "name": span.get("name"),
                        "startTimeUnixNano": span.get("startTimeUnixNano"),
                    }
                    events.append(_span_to_event(span_meta, attrs))
    return events
