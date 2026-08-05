"""
Day 5 (part 2) validation script.

Confirms the fix for the real cross-registration issue seen in a live
session: Copilot CLI reading .claude/settings.json as a cross-tool source
and firing BOTH hook handlers for one Copilot prompt, producing one real
capture and one empty stray one from the wrong parser.

Tests both directions:
  1. Active adapter = "copilot_hook" -> simulate BOTH handlers firing for
     the same session (as real cross-registration does) -> only the
     copilot_hook capture should exist, claude_code_hook should have
     written nothing at all (not even an empty one).
  2. No restriction set (marker absent) -> both fire normally, same as
     the existing two-agent isolation test - confirms the gate doesn't
     break the case where BOTH agents are deliberately in use at once.

Run from inside the project root:
    python test_active_adapter_gate.py
"""

import json
import subprocess
import sys
import uuid
from pathlib import Path

from capture.active_adapter import set_active_adapter, get_active_adapter
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


def _clean_pending_dir(repo_path: Path) -> None:
    pending_dir = repo_path / ".agentguard" / "pending_captures"
    if pending_dir.exists():
        for f in pending_dir.glob("*"):
            f.unlink()


def test_gate_suppresses_inactive_adapter():
    print("=== Test 1: active='copilot_hook' -> claude_code_hook writes nothing ===")
    repo_path = Path.cwd()
    _clean_pending_dir(repo_path)
    set_active_adapter(str(repo_path), "copilot_hook")
    assert get_active_adapter(str(repo_path)) == "copilot_hook"

    session_id = str(uuid.uuid4())
    prompt = "Add a comment explaining the retry logic"

    # Simulate BOTH configs firing for the same real session, as Copilot's
    # cross-tool settings.json reading actually does.
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

    pending_dir = repo_path / ".agentguard" / "pending_captures"
    stash_files = sorted(p.name for p in pending_dir.glob("*__prompt.json"))

    assert stash_files == [f"copilot_hook__{session_id}__prompt.json"], (
        f"expected only copilot_hook's stash, got: {stash_files}"
    )
    print(f"Only copilot_hook wrote a stash file: {stash_files}")
    print("claude_code_hook correctly wrote nothing (gated).")
    print("PASS\n")

    set_active_adapter(str(repo_path), None)  # cleanup


def test_no_restriction_both_fire():
    print("=== Test 2: no restriction -> both fire normally ===")
    repo_path = Path.cwd()
    _clean_pending_dir(repo_path)
    assert get_active_adapter(str(repo_path)) is None  # confirm clean state

    session_id = str(uuid.uuid4())
    prompt = "Add error handling to the upload function"

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

    pending_dir = repo_path / ".agentguard" / "pending_captures"
    stash_files = sorted(p.name for p in pending_dir.glob("*__prompt.json"))

    assert stash_files == [
        f"claude_code_hook__{session_id}__prompt.json",
        f"copilot_hook__{session_id}__prompt.json",
    ], f"expected both stashes, got: {stash_files}"
    print(f"Both fired as expected: {stash_files}")
    print("PASS\n")


if __name__ == "__main__":
    test_gate_suppresses_inactive_adapter()
    test_no_restriction_both_fire()
    print("All active-adapter gate tests passed.")
