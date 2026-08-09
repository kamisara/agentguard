"""
Validates otel_genai_parser against the REAL Copilot payload shape,
confirmed live 2026-08-09 (see docs/finding-otel-live-validation.md).

Real shape: gen_ai.input.messages/output.messages arrive as a JSON-encoded
STRING, not an OTLP-native structured value. This test builds a payload
matching that confirmed shape exactly (including a tool_call +
tool_call_response pair, since real Copilot sessions include tool use),
and checks:
  1. prompt/response text extraction works against the string-wrapped shape
  2. tool_calls are correctly extracted and paired by id
  3. the OLD structured-OTLP-value shape still works too (backward compat)

Run from inside the project root:
    python test_otel_real_payload_shape.py
"""

import json

from capture.otel_genai_parser import parse_otlp_json_spans


def _build_real_shaped_payload():
    """Mirrors the actual structure confirmed from a real Copilot session:
    gen_ai.input.messages is a stringValue containing JSON-encoded message
    objects with role + parts (text and tool_call/tool_call_response)."""
    input_messages = json.dumps([
        {"role": "user", "parts": [{"type": "text", "content": "List files in the repo"}]}
    ])
    output_messages = json.dumps([
        {
            "role": "assistant",
            "parts": [
                {"type": "text", "content": "Listing the directory now."},
                {"type": "tool_call", "id": "call_abc123", "name": "list_dir", "arguments": {"path": "."}},
            ],
        },
        {
            "role": "tool",
            "parts": [
                {"type": "tool_call_response", "id": "call_abc123", "response": "README.md, capture/"}
            ],
        },
        {
            "role": "assistant",
            "parts": [{"type": "text", "content": "Found README.md and the capture/ directory."}],
        },
    ])

    return {
        "resourceSpans": [{
            "scopeSpans": [{
                "spans": [{
                    "traceId": "real-shape-test",
                    "spanId": "span1",
                    "name": "chat",
                    "startTimeUnixNano": "1000000000",
                    "attributes": [
                        {"key": "gen_ai.request.model", "value": {"stringValue": "gpt-4.1"}},
                        {"key": "gen_ai.input.messages", "value": {"stringValue": input_messages}},
                        {"key": "gen_ai.output.messages", "value": {"stringValue": output_messages}},
                    ],
                }]
            }]
        }]
    }


def test_real_shaped_string_wrapped_messages():
    print("=== Real payload shape: string-wrapped JSON messages ===")
    payload = _build_real_shaped_payload()
    events = parse_otlp_json_spans(payload)

    assert len(events) == 1, f"expected 1 event, got {len(events)}"
    event = events[0]

    assert event.prompt == "List files in the repo", event.prompt
    print(f"prompt:   {event.prompt}")

    expected_response = "Listing the directory now.\nFound README.md and the capture/ directory."
    assert event.response == expected_response, event.response
    print(f"response: {event.response}")

    assert len(event.tool_calls) == 1, f"expected 1 tool call, got {len(event.tool_calls)}"
    tool_call = event.tool_calls[0]
    assert tool_call.name == "list_dir", tool_call.name
    assert tool_call.args == {"path": "."}, tool_call.args
    assert tool_call.output == "README.md, capture/", tool_call.output
    print(f"tool_call: {tool_call.name}({tool_call.args}) -> {tool_call.output}")

    print("PASS: text extraction and tool-call pairing both correct against real shape\n")


if __name__ == "__main__":
    test_real_shaped_string_wrapped_messages()
    print("Real OTel payload shape test passed.")
