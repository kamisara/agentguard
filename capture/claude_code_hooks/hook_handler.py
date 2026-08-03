"""
The actual script Claude Code invokes via .claude/settings.json.

Registered against TWO events, branching on hook_event_name from stdin:

  - UserPromptSubmit: fires when the developer submits a prompt. The JSON
    payload carries the prompt text directly - no transcript parsing
    needed for this half. We stash it to disk, keyed by session_id,
    because we don't have anywhere to hold state between separate hook
    invocations (each one is a fresh process).

  - Stop: fires when Claude finishes responding. At this point we read
    transcript_path (a JSONL file - one JSON object per line: user turns,
    assistant turns, tool calls/results, system events) to recover the
    final assistant message, pair it with the stashed prompt from the
    matching session_id, and write a completed pending capture.

This two-step design exists because a single hook invocation only sees one
side of the exchange. Trying to get both prompt and response from one event
would mean guessing at transcript structure we haven't confirmed is
guaranteed to be complete at that point.

Pending captures land in <cwd>/.agentguard/pending_captures/ - the adapter
(claude_code_hook_adapter.py) is a separate consumer of that directory, so
this script has no dependency on the rest of the capture package.
"""

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _pending_dir(cwd: str) -> Path:
    d = Path(cwd) / ".agentguard" / "pending_captures"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _prompt_stash_path(cwd: str, session_id: str) -> Path:
    return _pending_dir(cwd) / f"{session_id}__prompt.json"


def _handle_user_prompt_submit(payload: dict) -> None:
    session_id = payload["session_id"]
    stash_path = _prompt_stash_path(payload["cwd"], session_id)
    stash_path.write_text(
        json.dumps(
            {
                "session_id": session_id,
                "prompt": payload.get("prompt", ""),
                "cwd": payload["cwd"],
                "captured_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    )


def _extract_last_assistant_message(transcript_path: str) -> str:
    """Reads a Claude Code JSONL transcript and returns the text of the
    last assistant turn. Returns "" if the file is missing or no
    assistant turn is found, rather than raising - a missing transcript
    shouldn't crash the hook and block the developer's session."""
    path = Path(transcript_path)
    if not path.exists():
        return ""

    last_text = ""
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if entry.get("type") != "assistant":
                continue

            message = entry.get("message", {})
            content = message.get("content", "")

            # content can be a plain string, or a list of content blocks
            # (e.g. [{"type": "text", "text": "..."}]) depending on
            # whether the turn included tool use alongside text.
            if isinstance(content, str):
                last_text = content
            elif isinstance(content, list):
                text_parts = [
                    block.get("text", "")
                    for block in content
                    if isinstance(block, dict) and block.get("type") == "text"
                ]
                if text_parts:
                    last_text = "\n".join(text_parts)

    return last_text


def _handle_stop(payload: dict) -> None:
    session_id = payload["session_id"]
    cwd = payload["cwd"]

    stash_path = _prompt_stash_path(cwd, session_id)
    if not stash_path.exists():
        # No matching UserPromptSubmit was captured for this session - can
        # happen if hooks were only just enabled mid-session. Nothing to
        # pair the response with, so skip rather than emit a half-event.
        return

    stashed = json.loads(stash_path.read_text())
    response_text = _extract_last_assistant_message(payload.get("transcript_path", ""))

    completed = {
        "adapter": "claude_code_hook",
        "session_id": session_id,
        "prompt": stashed["prompt"],
        "response": response_text,
        "cwd": cwd,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }

    out_path = _pending_dir(cwd) / f"{session_id}__{uuid.uuid4()}.json"
    out_path.write_text(json.dumps(completed))

    stash_path.unlink()  # done with the stashed prompt


def main() -> None:
    payload = json.load(sys.stdin)
    event = payload.get("hook_event_name")

    if event == "UserPromptSubmit":
        _handle_user_prompt_submit(payload)
    elif event == "Stop":
        _handle_stop(payload)
    # Silently ignore any other event - this script should only be
    # registered against these two, but being defensive costs nothing.


if __name__ == "__main__":
    main()
