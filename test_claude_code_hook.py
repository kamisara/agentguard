"""
Day 4 validation script.

Simulates a full Claude Code session round trip WITHOUT a real Claude Code
instance:
  1. Fake a UserPromptSubmit stdin payload, pipe it into hook_handler.py
     as a real subprocess (not calling the function directly - this tests
     the actual entrypoint, including stdin JSON parsing).
  2. Write a realistic JSONL transcript file matching the documented
     format (one JSON object per line, "type": "user" / "assistant" /
     tool events).
  3. Fake a Stop stdin payload pointing at that transcript, pipe it into
     hook_handler.py.
  4. Instantiate ClaudeCodeHookAdapter for real, confirm is_available()
     and capture() produce a correct CaptureEvent.
  5. Normalize it, confirm intent_source == "explicit" (this adapter
     captures a real prompt, unlike git's inferred intent).

Run from inside the project root:
    python test_claude_code_hook.py
"""

import json
import subprocess
import sys
import uuid
from pathlib import Path

from capture.claude_code_hook_adapter import ClaudeCodeHookAdapter
from capture.normalizer import normalize

HOOK_HANDLER = str(
    Path(__file__).parent / "capture" / "claude_code_hooks" / "hook_handler.py"
)


def _run_hook(payload: dict) -> None:
    """Invokes hook_handler.py exactly as Claude Code would: JSON on
    stdin, nothing on argv."""
    result = subprocess.run(
        [sys.executable, HOOK_HANDLER],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"hook_handler.py failed: {result.stderr}")


def _write_fake_transcript(path: Path, session_id: str, prompt: str, response: str):
    """Realistic shape per Claude Code's documented JSONL transcript
    format: one JSON object per line, "type" field distinguishing user/
    assistant/tool entries. Includes a tool-call line in between to
    confirm the parser correctly skips non-assistant-text entries rather
    than grabbing the wrong line."""
    lines = [
        {"type": "user", "message": {"role": "user", "content": prompt}},
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "name": "Read", "input": {}}],
            },
        },
        {"type": "tool_result", "content": "file contents here"},
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": response}],
            },
        },
    ]
    with path.open("w", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")


def main():
    repo_path = Path.cwd()
    session_id = str(uuid.uuid4())
    prompt_text = "Refactor the login handler to use async/await"
    response_text = "Done - converted loginHandler to async and awaited the DB call."

    transcript_path = repo_path / f"transcript-{session_id}.jsonl"
    _write_fake_transcript(transcript_path, session_id, prompt_text, response_text)

    print("=== Step 1: simulate UserPromptSubmit ===")
    _run_hook(
        {
            "session_id": session_id,
            "cwd": str(repo_path),
            "hook_event_name": "UserPromptSubmit",
            "prompt": prompt_text,
        }
    )
    stash_path = repo_path / ".agentguard" / "pending_captures" / f"claude_code_hook__{session_id}__prompt.json"
    assert stash_path.exists(), "expected prompt stash file after UserPromptSubmit"
    print(f"Prompt stashed: {stash_path.name}\n")

    print("=== Step 2: simulate Stop (with realistic transcript) ===")
    _run_hook(
        {
            "session_id": session_id,
            "cwd": str(repo_path),
            "hook_event_name": "Stop",
            "transcript_path": str(transcript_path),
            "stop_hook_active": False,
        }
    )
    assert not stash_path.exists(), "prompt stash should be consumed after Stop"
    print("Prompt stash consumed, completed capture should now exist\n")

    print("=== Step 3: ClaudeCodeHookAdapter picks it up ===")
    adapter = ClaudeCodeHookAdapter(repo_path)
    assert adapter.is_available(), "adapter should report available"
    event = adapter.capture()

    assert event.adapter == "claude_code_hook"
    assert event.prompt == prompt_text, f"prompt mismatch: {event.prompt!r}"
    assert event.response == response_text, f"response mismatch: {event.response!r}"
    assert event.session_id == session_id
    print(f"CaptureEvent.prompt:   {event.prompt}")
    print(f"CaptureEvent.response: {event.response}")
    print("PASS: prompt and response correctly paired and extracted\n")

    print("=== Step 4: normalize ===")
    normalized = normalize(event)
    assert normalized.intent_source.value == "explicit", (
        f"expected explicit, got {normalized.intent_source.value}"
    )
    print(f"intent_source: {normalized.intent_source.value} (expect 'explicit')")
    print("PASS\n")

    assert not adapter.is_available(), "capture() should have consumed the file"
    print("Confirmed: capture() consumed the file, adapter no longer available.\n")

    transcript_path.unlink()
    print("All Claude Code hook adapter tests passed.")


if __name__ == "__main__":
    main()
