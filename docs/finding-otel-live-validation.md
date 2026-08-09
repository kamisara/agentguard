# Finding: OTel receiver validated live against real Copilot traffic — two real bugs found and fixed via live debugging

**Date:** 2026-08-08/09
**Question tested:** Does the OTLP receiver actually work against real Copilot OTel emission, end to end?

## Answer: Yes, after fixing two real bugs neither found by unit testing alone.

Unit tests (`test_otel_telemetry_source.py`) already validated the receiver against hand-built and officially-constructed protobuf payloads. They did **not** catch either bug below — both only surfaced against a real client (VS Code's Node.js extension host) over a real network path.

## Bug 1: Missing `Content-Length`, stuck on HTTP/1.0 → silent hang, no visible error

The receiver never set `Content-Length` on any response and defaulted to `HTTP/1.0`. Node's HTTP/1.1 client (what Copilot's exporter uses) expects an explicit `Content-Length` or chunked encoding to know a response is complete. Without it, the client can hang waiting for a response it believes is incomplete. Because OTel exporters are deliberately built to swallow export failures rather than crash the host application, this produced **zero visible errors anywhere** — not in VS Code's logs, not in the receiver. The only symptom was silence.

**Confirmed via manual test**, not inference: a raw socket check showed the literal wire response was `HTTP/1.0 200 OK` with no `Content-Length` header at all.

**Fix:** `protocol_version = "HTTP/1.1"` on the handler, explicit `Content-Length` on every response path (200/404/415/400) — previously only some paths sent a body, none set the header.

## Bug 2: Doubled `/v1/traces` in the configured endpoint

Standard OTLP HTTP exporters append `/v1/traces` to whatever base endpoint they're given. Copilot's `otlpEndpoint` setting was configured as `http://localhost:4318/v1/traces` (matching what a log line echoed back, which was misleading — the log line just echoes the *setting*, not what the exporter actually does with it). The exporter appended its own suffix, producing requests to `/v1/traces/v1/traces`, which the receiver correctly 404'd.

**Fix:** endpoint setting corrected to the bare base (`http://localhost:4318`), matching every example in Microsoft's own OTel documentation for Copilot Chat.

## Bug 3 (parser-level, found once traffic actually arrived): message content shape assumption was wrong

Once bugs 1–2 were fixed, real traffic arrived — and `gen_ai.input.messages` / `gen_ai.output.messages` turned out to be a **JSON-encoded string**, not an OTLP-native structured value (`arrayValue`/`kvlistValue`) as originally assumed from documentation alone. Same failure category as the earlier Copilot hook transcript-format finding: documentation described the attribute names correctly, but the actual value encoding differed from the reasonable-looking assumption.

Real shape: a JSON string decoding to a list of `{"role": ..., "parts": [{"type": "text", "content": ...}, {"type": "tool_call", ...}, {"type": "tool_call_response", ...}]}` objects.

**Fix:** `otel_genai_parser._parse_messages` now JSON-decodes string values before processing, with the old structured-value handling kept as a fallback (backward compatible, tested in `test_otel_telemetry_source.py`). New: `_extract_tool_calls` pulls real tool-call/response pairs out of the same parsed messages — previously an empty gap (no adapter populated `CaptureEvent.tool_calls` at all), now filled using data that was already present in the payload.

## Consequence for the project

Three confirmed, fixed bugs from one live debugging session, each isolated to a specific function/setting rather than requiring a rewrite — consistent with the project's "isolate assumptions so they're cheap to fix" discipline established with the Copilot hook transcript finding. This is strong evidence for the design-science methodology write-up: real-world validation caught real defects that realistic-but-synthetic unit tests did not, and the architecture's isolation of encoding-specific logic meant each fix was small and contained.

**Also unlocked:** real tool-call data is now flowing into `CaptureEvent.tool_calls` from live Copilot sessions, which directly feeds Sprint 3's `tool_invocations` attestation field with real data, not a placeholder.
