"""
Shared logic for file-bridged hook handlers.

Claude Code and GitHub Copilot's "VS Code compatible" hook payload format
use identical field names for the events we care about (session_id,
transcript_path, cwd, hook_event_name, prompt) - confirmed against both
products' docs, not assumed. That's why this logic is shared rather than
duplicated per agent: the actual difference between agents is which
directory their hook config lives in and what event-name casing they're
registered with, not the payload shape itself.

ONE THING NOT YET VERIFIED: both agents expose a transcript_path, but
whether Copilot's transcript file uses the exact same JSONL "type":
"assistant"/"user" schema as Claude Code's has not been confirmed against
real output from either product - only inferred from the "VS Code
compatible" framing in Copilot's docs. If real Copilot transcripts turn out
to differ, only _extract_last_assistant_message needs to change - it's
already isolated here for that reason.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


def _pending_dir(cwd: str) -> Path:
    d = Path(cwd) / ".agentguard" / "pending_captures"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _prompt_stash_path(cwd: str, adapter_tag: str, session_id: str) -> Path:
    # adapter_tag prefixed so two different agents' hooks writing into the
    # same pending_captures/ directory never collide or get picked up by
    # the wrong adapter - see hook_adapter_base.py for the read side of this.
    return _pending_dir(cwd) / f"{adapter_tag}__{session_id}__prompt.json"


def handle_user_prompt_submit(payload: dict, adapter_tag: str) -> None:
    session_id = payload["session_id"]
    stash_path = _prompt_stash_path(payload["cwd"], adapter_tag, session_id)
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


def handle_stop(
    payload: dict,
    adapter_tag: str,
    transcript_parser: Callable[[str], str],
) -> None:
    """transcript_parser extracts the final assistant response text from
    whatever transcript_path points to. This is intentionally NOT shared
    logic between agents - confirmed (not assumed) that Claude Code and
    Copilot use genuinely different transcript schemas:

      - Claude Code: {"type": "assistant", "message": {"content": ...}}
      - Copilot:     {"type": "assistant.message", "data": {"content": ...}}

    Each agent's hook_handler.py passes its own parser
    (claude_code_hooks/transcript_parser.py or
    copilot_hooks/transcript_parser.py) - only the stash/pair mechanism
    below is genuinely shared.
    """
    session_id = payload["session_id"]
    cwd = payload["cwd"]

    stash_path = _prompt_stash_path(cwd, adapter_tag, session_id)
    if not stash_path.exists():
        # No matching UserPromptSubmit was captured for this session/agent -
        # nothing to pair the response with, so skip rather than emit a
        # half-event.
        return

    stashed = json.loads(stash_path.read_text())
    response_text = transcript_parser(payload.get("transcript_path", ""))

    completed = {
        "adapter": adapter_tag,
        "session_id": session_id,
        "prompt": stashed["prompt"],
        "response": response_text,
        "cwd": cwd,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }

    out_path = _pending_dir(cwd) / f"{adapter_tag}__{session_id}__{uuid.uuid4()}.json"
    out_path.write_text(json.dumps(completed))

    stash_path.unlink()
