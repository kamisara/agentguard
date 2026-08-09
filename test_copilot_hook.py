"""
Day 5 validation script.

Two things tested:
  1. CopilotHookAdapter works, using Copilot's "VS Code compatible" payload
     shape (PascalCase event names, snake_case fields) - same simulation
     approach as test_claude_code_hook.py.
  2. Two-agent isolation: simulate a Claude Code capture AND a Copilot
     capture landing in the same .agentguard/pending_captures/ directory
     at the same time, and confirm each adapter only ever picks up its
     own - this is the bug that existed before hook_adapter_base.py's
     tag-scoped glob was introduced.

Run from inside the project root:
    python test_copilot_hook.py
"""

import json
import subprocess
import sys
import uuid
from pathlib import Path

from capture.claude_code_hook_adapter import ClaudeCodeHookAdapter
from capture.copilot_hook_adapter import CopilotHookAdapter
from capture.normalizer import normalize

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


def _write_copilot_transcript(path: Path, prompt: str, response: str):
    """Uses the CONFIRMED real Copilot events.jsonl format (from a real
    session, 2026-08-04), not Claude Code's format. These are genuinely
    different schemas - see capture/copilot_hooks/transcript_parser.py.
    Includes an intermediate assistant.message (as Copilot emits per-turn
    narration like "Reading the file...") to confirm the parser correctly
    picks the LAST one, not the first."""
    lines = [
        {"type": "session.start", "data": {"sessionId": "fake"}},
        {"type": "user.message", "data": {"content": prompt}},
        {
            "type": "assistant.message",
            "data": {
                "content": "Reading the target file first.",
                "toolRequests": [{"name": "view"}],
            },
        },
        {"type": "tool.execution_complete", "data": {"result": "file contents"}},
        {
            "type": "assistant.message",
            "data": {"content": response, "toolRequests": []},
        },
    ]
    with path.open("w", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")


def _write_claude_code_transcript(path: Path, prompt: str, response: str):
    """Claude Code's assumed format ({"type": "assistant", "message": {...}}) -
    used here specifically so test_two_agent_isolation gives each handler a
    transcript that actually matches its own schema_matcher. Using the
    Copilot-shaped transcript for both (as an earlier version of this test
    did) meant ClaudeCodeHookAdapter's automatic detection correctly
    rejected it once schema_matcher was added - that was the fix working,
    not a bug, but it meant this test needed two writers, not one."""
    lines = [
        {"type": "user", "message": {"role": "user", "content": prompt}},
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


def _simulate_session(
    handler_path: str,
    repo_path: Path,
    prompt: str,
    response: str,
    transcript_writer=_write_copilot_transcript,
) -> str:
    """Runs UserPromptSubmit then Stop against the given handler, returns
    the session_id used, so the caller can correlate results."""
    session_id = str(uuid.uuid4())
    transcript_path = repo_path / f"transcript-{session_id}.jsonl"
    transcript_writer(transcript_path, prompt, response)

    _run_hook(
        handler_path,
        {
            "session_id": session_id,
            "cwd": str(repo_path),
            "hook_event_name": "UserPromptSubmit",
            "prompt": prompt,
        },
    )
    _run_hook(
        handler_path,
        {
            "session_id": session_id,
            "cwd": str(repo_path),
            "hook_event_name": "Stop",
            "transcript_path": str(transcript_path),
            "stop_hook_active": False,
        },
    )
    transcript_path.unlink()
    return session_id


def _clear_pending_captures(repo_path: Path):
    """Tests should not depend on the directory being empty beforehand -
    a leftover real capture (e.g. from restoring a real fixture to
    demonstrate other functionality) would otherwise get picked up
    instead of the one this test just created, since capture() takes the
    OLDEST matching file. Found this exact fragility in practice, not
    hypothetically - worth fixing here rather than just remembering to
    clean up externally every time."""
    pending_dir = repo_path / ".agentguard" / "pending_captures"
    if pending_dir.exists():
        for f in pending_dir.glob("copilot_hook__*.json"):
            f.unlink()


def test_copilot_adapter_basic():
    print("=== Test 1: CopilotHookAdapter basic round trip ===")
    repo_path = Path.cwd()
    _clear_pending_captures(repo_path)
    prompt = "Add input validation to the signup form"
    response = "Added email format and password length checks to SignupForm.validate()."

    _simulate_session(COPILOT_HOOK_HANDLER, repo_path, prompt, response)

    adapter = CopilotHookAdapter(repo_path)
    assert adapter.is_available()
    event = adapter.capture()

    assert event.adapter == "copilot_hook"
    assert event.prompt == prompt
    assert event.response == response
    print(f"CaptureEvent.prompt:   {event.prompt}")
    print(f"CaptureEvent.response: {event.response}")

    normalized = normalize(event)
    assert normalized.intent_source.value == "explicit"
    print(f"intent_source: {normalized.intent_source.value} (expect 'explicit')")
    print("PASS\n")


def test_two_agent_isolation():
    print("=== Test 2: two agents, same directory, no cross-contamination ===")
    repo_path = Path.cwd()
    _clear_pending_captures(repo_path)

    claude_prompt = "Refactor the auth module to use dependency injection"
    claude_response = "Refactored AuthService to accept its dependencies via constructor."
    copilot_prompt = "Write unit tests for the payment processor"
    copilot_response = "Added 6 unit tests covering success, decline, and timeout paths."

    _simulate_session(
        CLAUDE_HOOK_HANDLER, repo_path, claude_prompt, claude_response,
        transcript_writer=_write_claude_code_transcript,
    )
    _simulate_session(
        COPILOT_HOOK_HANDLER, repo_path, copilot_prompt, copilot_response,
        transcript_writer=_write_copilot_transcript,
    )

    claude_adapter = ClaudeCodeHookAdapter(repo_path)
    copilot_adapter = CopilotHookAdapter(repo_path)

    assert claude_adapter.is_available()
    assert copilot_adapter.is_available()

    claude_event = claude_adapter.capture()
    copilot_event = copilot_adapter.capture()

    assert claude_event.adapter == "claude_code_hook"
    assert claude_event.prompt == claude_prompt, (
        f"Claude adapter picked up wrong prompt: {claude_event.prompt!r}"
    )
    print(f"ClaudeCodeHookAdapter captured its own event: {claude_event.prompt!r}")

    assert copilot_event.adapter == "copilot_hook"
    assert copilot_event.prompt == copilot_prompt, (
        f"Copilot adapter picked up wrong prompt: {copilot_event.prompt!r}"
    )
    print(f"CopilotHookAdapter captured its own event:    {copilot_event.prompt!r}")

    # Both should now report nothing left pending - proves neither adapter
    # left the other's file untouched by accident, nor consumed it.
    assert not claude_adapter.is_available()
    assert not copilot_adapter.is_available()
    print("Both adapters now report empty - no leftover or cross-picked files.")
    print("PASS: no cross-contamination between agents\n")


if __name__ == "__main__":
    test_copilot_adapter_basic()
    test_two_agent_isolation()
    print("All Copilot hook adapter tests passed.")
