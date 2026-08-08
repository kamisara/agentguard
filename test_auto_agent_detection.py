"""
Day 5 (part 3) validation script.

This is the actual test for the real requirement: a developer using
AgentGuard as a VS Code extension never runs a setup command per agent.
Detection has to be fully automatic.

Simulates the EXACT real bug: a single Copilot session, with a genuinely
Copilot-shaped transcript, fires BOTH hook handlers at once (because
Copilot CLI reads .claude/settings.json as a cross-tool source) - with NO
active_adapter marker set, i.e. the default, out-of-the-box state.

Expected: ClaudeCodeHookAdapter's handler automatically recognizes the
transcript isn't its own shape and produces nothing. CopilotHookAdapter's
handler produces the real capture. Zero developer action anywhere in this
test - that's the point.

Run from inside the project root:
    python test_auto_agent_detection.py
"""

import json
import subprocess
import sys
import uuid
from pathlib import Path

from capture.active_adapter import get_active_adapter
from capture.claude_code_hook_adapter import ClaudeCodeHookAdapter
from capture.copilot_hook_adapter import CopilotHookAdapter

CLAUDE_HOOK_HANDLER = str(
    Path(__file__).parent / "capture" / "claude_code_hooks" / "hook_handler.py"
)
COPILOT_HOOK_HANDLER = str(
    Path(__file__).parent / "capture" / "copilot_hooks" / "hook_handler.py"
)


def _run_hook(handler_path: str, payload: dict) -> None:
    result = subprocess.run(
        [sys.executable, handler_path],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"{handler_path} failed: {result.stderr}")


def _write_real_copilot_shaped_transcript(path: Path, prompt: str, response: str):
    """The confirmed real shape from a live Copilot session (2026-08-04) -
    same as copilot_hooks/transcript_parser.py is built against."""
    lines = [
        {
            "type": "session.start",
            "data": {"sessionId": "fake", "producer": "copilot-agent"},
        },
        {"type": "user.message", "data": {"content": prompt}},
        {
            "type": "assistant.message",
            "data": {"content": response, "toolRequests": []},
        },
    ]
    with path.open("w", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")


def test_automatic_detection_no_manual_config():
    print("=== Automatic detection, zero manual configuration ===")
    repo_path = Path.cwd()

    # Confirm the precondition: no manual override is set. This is the
    # actual default state a fresh AgentGuard install would be in - the
    # test would be meaningless if a leftover marker from an earlier test
    # were still forcing the outcome.
    assert get_active_adapter(str(repo_path)) is None, (
        "test precondition failed: an active_adapter marker is set. "
        "This test specifically needs the unconfigured default state."
    )

    session_id = str(uuid.uuid4())
    prompt = "Add a comment explaining the retry logic"
    response = "Added a comment above the retry loop explaining the backoff strategy."
    transcript_path = repo_path / f"transcript-{session_id}.jsonl"
    _write_real_copilot_shaped_transcript(transcript_path, prompt, response)

    # Real cross-registration: ONE Copilot session, but BOTH hook configs
    # exist in the repo, so Copilot invokes both handlers for the same
    # UserPromptSubmit and Stop events - exactly what happened live.
    for handler in (CLAUDE_HOOK_HANDLER, COPILOT_HOOK_HANDLER):
        _run_hook(
            handler,
            {
                "session_id": session_id,
                "cwd": str(repo_path),
                "hook_event_name": "UserPromptSubmit",
                "prompt": prompt,
            },
        )
    for handler in (CLAUDE_HOOK_HANDLER, COPILOT_HOOK_HANDLER):
        _run_hook(
            handler,
            {
                "session_id": session_id,
                "cwd": str(repo_path),
                "hook_event_name": "Stop",
                "transcript_path": str(transcript_path),
                "stop_hook_active": False,
            },
        )

    transcript_path.unlink()

    claude_adapter = ClaudeCodeHookAdapter(repo_path)
    copilot_adapter = CopilotHookAdapter(repo_path)

    assert not claude_adapter.is_available(), (
        "ClaudeCodeHookAdapter should have automatically self-excluded - "
        "the transcript doesn't match its schema, no marker was set, and "
        "no developer action told it to stay quiet."
    )
    print("ClaudeCodeHookAdapter correctly produced nothing (automatic).")

    assert copilot_adapter.is_available()
    event = copilot_adapter.capture()
    assert event.prompt == prompt
    assert event.response == response
    print(f"CopilotHookAdapter correctly captured: {event.response!r}")

    print("PASS: correct agent detected automatically, no config required.\n")


if __name__ == "__main__":
    test_automatic_detection_no_manual_config()
    print("Automatic agent detection test passed.")
