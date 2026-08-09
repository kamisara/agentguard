"""
Parses OTLP/HTTP+JSON trace export payloads for GenAI semantic-convention
spans, converting matching spans into CaptureEvents.

SCOPE AND HONESTY NOTES:

- Grounded in documented gen_ai.* attribute names (confirmed via search,
  Aug 2026): gen_ai.request.model, gen_ai.input.messages,
  gen_ai.output.messages, gen_ai.system_instructions,
  gen_ai.response.finish_reasons, gen_ai.usage.input_tokens/output_tokens.
- These conventions are explicitly Development-status - no 1.0 release,
  names can still change.
- CONFIRMED against a real live Copilot payload (2026-08-09, see
  docs/finding-otel-live-validation.md): gen_ai.input.messages /
  gen_ai.output.messages arrive as a STRING containing serialized JSON,
  NOT as an OTLP-native arrayValue/kvlistValue structure - the earlier
  assumption in this file was wrong, same failure mode as the Copilot
  hook transcript finding. Fixed here against the real shape:
  a JSON string decoding to a list of message objects, each shaped
  {"role": "user"|"assistant"|"tool", "parts": [{"type": "text",
  "content": "..."}, {"type": "tool_call", "id":..., "name":...,
  "arguments":{...}}, {"type": "tool_call_response", "id":...,
  "response":...}]}.

OTLP/HTTP+JSON structure (per the OTLP spec): a trace export payload is
{"resourceSpans": [{"resource": {...}, "scopeSpans": [{"spans": [...]}]}]}.
Each span has "name", "attributes" (list of {"key", "value": {typed
wrapper}}), "startTimeUnixNano", "traceId", "spanId".
"""

import json as _json
from datetime import datetime, timezone
from typing import List

from .types import CaptureEvent, ToolCall


def _otlp_value_to_python(value: dict):
    """OTLP JSON values are typed wrappers, e.g. {"stringValue": "..."}.
    Unwraps to a plain Python value. kvlistValue (nested key-value object)
    and arrayValue (list) recurse. Still correct for model name, token
    counts, etc. - only the messages fields needed special handling, see
    _parse_messages below."""
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


def _parse_messages(value) -> list:
    """Confirmed real shape (2026-08-09): value is a JSON-encoded STRING,
    not a structured OTLP value. Parses it into a list of message dicts.
    Falls back gracefully for a plain (non-JSON) string or an already-list
    value, in case a different exporter genuinely does send structured
    OTLP values as originally assumed - isolated here so either shape
    keeps working."""
    if isinstance(value, str):
        try:
            parsed = _json.loads(value)
        except (_json.JSONDecodeError, TypeError):
            # Not JSON - treat the whole string as one plain-text message.
            return [{"role": None, "parts": [{"type": "text", "content": value}]}]
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return [parsed]
        return []
    if isinstance(value, list):
        return value
    return []


def _messages_to_text(messages) -> str:
    """Extracts just the human-readable text parts from a parsed message
    list. Tool call parts are deliberately skipped here (they're
    structured data, not prose) but nothing is lost - see
    _extract_tool_calls, which reads the same parsed messages."""
    parsed = _parse_messages(messages)
    parts = []
    for msg in parsed:
        if not isinstance(msg, dict):
            continue
        msg_parts = msg.get("parts")
        if isinstance(msg_parts, list):
            for part in msg_parts:
                if isinstance(part, dict) and part.get("type") == "text":
                    content = part.get("content", "")
                    if isinstance(content, str) and content:
                        parts.append(content)
        else:
            # Fallback for a simpler {"content": "..."} shape some
            # exporters might use instead of the parts-array structure.
            content = msg.get("content", "")
            if isinstance(content, str) and content:
                parts.append(content)
    return "\n".join(parts)


def _extract_tool_calls(messages: list) -> List[ToolCall]:
    """Builds ToolCall objects from tool_call / tool_call_response parts,
    pairing them by call id. Confirmed real shape (2026-08-09): a
    tool_call part is {"type": "tool_call", "id":..., "name":...,
    "arguments": {...}}; the matching tool_call_response part (in a
    later message) is {"type": "tool_call_response", "id":...,
    "response":...}. This was previously an empty gap - no adapter
    populated CaptureEvent.tool_calls - filled in here using the real
    data that was sitting in the OTel payload the whole time."""
    calls_by_id: dict = {}
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        for part in msg.get("parts") or []:
            if not isinstance(part, dict):
                continue
            call_id = part.get("id")
            if part.get("type") == "tool_call":
                entry = calls_by_id.setdefault(call_id, {})
                entry["name"] = part.get("name", "unknown")
                entry["args"] = part.get("arguments") or {}
            elif part.get("type") == "tool_call_response":
                entry = calls_by_id.setdefault(call_id, {})
                entry["output"] = part.get("response")

    return [
        ToolCall(
            name=c.get("name", "unknown"),
            args=c.get("args", {}),
            output=str(c["output"]) if c.get("output") is not None else None,
        )
        for c in calls_by_id.values()
    ]


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

    input_messages = _parse_messages(attrs.get("gen_ai.input.messages"))
    output_messages = _parse_messages(attrs.get("gen_ai.output.messages"))

    return CaptureEvent(
        adapter="otel_genai",
        timestamp=timestamp,
        prompt=_messages_to_text(attrs.get("gen_ai.input.messages")),
        response=_messages_to_text(attrs.get("gen_ai.output.messages")),
        model=attrs.get("gen_ai.request.model"),
        session_id=span_meta.get("traceId"),
        tool_calls=_extract_tool_calls(output_messages) or _extract_tool_calls(input_messages),
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
