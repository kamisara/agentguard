"""
Sprint 3, Day 2 validation script.

Tests extract_tool_calls() for both agents:
  1. Copilot - against a REAL transcript excerpt (the actual events.jsonl
     content shared during live debugging on 2026-08-04, where Copilot
     called the `view` tool on copilot_hook_adapter.py). Not invented -
     copied directly from real data already seen in this project.
  2. Claude Code - against a synthetic fixture matching the
     documented/assumed content-block shape, CLEARLY marked as unconfirmed
     (same standing caveat as the rest of the Claude Code parsing code -
     no live Claude Code session has been tested in this project).

Run from inside the project root:
    python test_tool_call_extraction.py
"""

import json
import tempfile
from pathlib import Path

from capture.copilot_hooks.transcript_parser import extract_tool_calls as copilot_extract
from capture.claude_code_hooks.transcript_parser import extract_tool_calls as claude_extract


def test_copilot_real_transcript():
    print("=== Copilot: tool call extraction from REAL transcript data ===")

    # This is the actual real events.jsonl content shared during live
    # debugging (2026-08-04) - Copilot calling the `view` tool.
    lines = [
        json.dumps({
            "type": "assistant.message",
            "data": {
                "content": "Reading the target file to determine the exact first line so the insertion can be made precisely.",
                "toolRequests": [{
                    "toolCallId": "call_AmXWZoTT2XylsRy6bljispQx",
                    "name": "view",
                    "arguments": {"path": "D:\\code pfe 2\\agentguard\\capture\\copilot_hook_adapter.py"},
                    "type": "function",
                }],
            },
        }),
        json.dumps({
            "type": "tool.execution_start",
            "data": {"toolCallId": "call_AmXWZoTT2XylsRy6bljispQx", "toolName": "view"},
        }),
        json.dumps({
            "type": "tool.execution_complete",
            "data": {
                "toolCallId": "call_AmXWZoTT2XylsRy6bljispQx",
                "success": True,
                "result": {"content": "\"\"\"\nGitHub Copilot hook adapter...\n\"\"\"\n"},
            },
        }),
        json.dumps({
            "type": "assistant.message",
            "data": {"content": "Done — added the comment.", "toolRequests": []},
        }),
    ]

    transcript_path = Path(tempfile.gettempdir()) / "real_copilot_transcript_test.jsonl"
    transcript_path.write_text("\n".join(lines))

    tool_calls = copilot_extract(str(transcript_path))
    transcript_path.unlink()

    assert len(tool_calls) == 1, f"expected 1 tool call, got {len(tool_calls)}"
    tc = tool_calls[0]
    assert tc.name == "view"
    assert tc.args == {"path": "D:\\code pfe 2\\agentguard\\capture\\copilot_hook_adapter.py"}
    assert tc.output is not None and "GitHub Copilot hook adapter" in tc.output

    print(f"name:   {tc.name}")
    print(f"args:   {tc.args}")
    print(f"output: {tc.output[:60]}...")
    print("PASS: extracted correctly from real transcript data\n")


def test_claude_code_synthetic_fixture():
    print("=== Claude Code: tool call extraction (UNCONFIRMED shape) ===")

    lines = [
        json.dumps({"type": "user", "message": {"role": "user", "content": "Read config.py"}}),
        json.dumps({
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Reading the file now."},
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "config.py"}},
                ],
            },
        }),
    ]

    transcript_path = Path(tempfile.gettempdir()) / "synthetic_claude_transcript_test.jsonl"
    transcript_path.write_text("\n".join(lines))

    tool_calls = claude_extract(str(transcript_path))
    transcript_path.unlink()

    assert len(tool_calls) == 1
    tc = tool_calls[0]
    assert tc.name == "Read"
    assert tc.args == {"file_path": "config.py"}
    assert tc.output is None  # pairing not implemented, documented limitation

    print(f"name:   {tc.name}")
    print(f"args:   {tc.args}")
    print(f"output: {tc.output} (expected None - pairing not implemented, unconfirmed shape)")
    print("PASS (against unconfirmed assumed shape - flag stands until live-tested)\n")


if __name__ == "__main__":
    test_copilot_real_transcript()
    test_claude_code_synthetic_fixture()
    print("Tool call extraction tests passed.")
