"""
Sprint 3, Day 2 - full pipeline proof.

Not just extract_tool_calls() in isolation (test_tool_call_extraction.py
covers that) - this confirms tool call data actually survives the whole
real pipeline: hook_handler.py subprocess -> pending_captures file ->
CopilotHookAdapter.capture() -> CaptureEvent.tool_calls ->
NormalizedEvent.tool_invocations -> ContextualAttestation.tool_invocations.

Uses the same real transcript content as test_tool_call_extraction.py.

Run from inside the project root:
    python test_tool_calls_end_to_end.py
"""

import json
import subprocess
import sys
import uuid
from pathlib import Path

from capture.copilot_hook_adapter import CopilotHookAdapter
from capture.normalizer import normalize
from attestation.generator import generate_attestation

HOOK_HANDLER = str(
    Path(__file__).parent / "capture" / "copilot_hooks" / "hook_handler.py"
)


def _run_hook(payload: dict):
    result = subprocess.run(
        [sys.executable, HOOK_HANDLER],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"hook_handler.py failed: {result.stderr}")


def main():
    repo_path = Path.cwd()
    session_id = str(uuid.uuid4())
    prompt = "Add a comment explaining copilot_hook_adapter.py"

    # Real transcript content (same as test_tool_call_extraction.py's
    # Copilot test), including the real tool call.
    transcript_lines = [
        json.dumps({
            "type": "assistant.message",
            "data": {
                "content": "Reading the target file first.",
                "toolRequests": [{
                    "toolCallId": "call_test123",
                    "name": "view",
                    "arguments": {"path": "capture/copilot_hook_adapter.py"},
                    "type": "function",
                }],
            },
        }),
        json.dumps({
            "type": "tool.execution_complete",
            "data": {"toolCallId": "call_test123", "success": True, "result": "file contents here"},
        }),
        json.dumps({
            "type": "assistant.message",
            "data": {"content": "Done — added the comment.", "toolRequests": []},
        }),
    ]
    transcript_path = repo_path / f"transcript-{session_id}.jsonl"
    transcript_path.write_text("\n".join(transcript_lines))

    print("=== Step 1: real hook subprocess round trip ===")
    _run_hook({
        "session_id": session_id, "cwd": str(repo_path),
        "hook_event_name": "UserPromptSubmit", "prompt": prompt,
    })
    _run_hook({
        "session_id": session_id, "cwd": str(repo_path),
        "hook_event_name": "Stop", "transcript_path": str(transcript_path),
        "stop_hook_active": False,
    })
    transcript_path.unlink()

    print("=== Step 2: CopilotHookAdapter.capture() ===")
    adapter = CopilotHookAdapter(repo_path)
    assert adapter.is_available()
    event = adapter.capture()
    assert len(event.tool_calls) == 1, f"expected 1 tool call on CaptureEvent, got {len(event.tool_calls)}"
    print(f"CaptureEvent.tool_calls: {event.tool_calls}")

    print("\n=== Step 3: normalize -> NormalizedEvent.tool_invocations ===")
    normalized = normalize(event)
    assert len(normalized.tool_invocations) == 1
    print(f"NormalizedEvent.tool_invocations: {normalized.tool_invocations}")

    print("\n=== Step 4: generate_attestation -> retrieved_context / tool_invocations ===")
    attestation = generate_attestation(normalized)
    # Sprint 3, Day 3: tool calls are now classified by name-pattern
    # heuristic. "view" matches the retrieval pattern, so it lands in
    # retrieved_context, not tool_invocations - this is the CORRECT
    # updated behavior, not a regression (see attestation/generator.py
    # _is_retrieval_tool).
    assert len(attestation.tool_invocations) == 0, (
        f"expected 0 (view should be classified as retrieval), got "
        f"{len(attestation.tool_invocations)}"
    )
    assert len(attestation.retrieved_context) == 1, (
        f"expected 1 retrieval entry, got {len(attestation.retrieved_context)}"
    )
    retrieval_entry = attestation.retrieved_context[0]
    assert retrieval_entry["name"] == "view"
    assert retrieval_entry["args"] == {"path": "capture/copilot_hook_adapter.py"}
    print(f"ContextualAttestation.retrieved_context: {attestation.retrieved_context}")
    print(f"ContextualAttestation.tool_invocations:  {attestation.tool_invocations} (empty - correct, 'view' is a read)")

    print("\nPASS: tool call data survives the full real pipeline, end to end,")
    print("      AND is correctly classified as retrieval vs. action.")


if __name__ == "__main__":
    main()
